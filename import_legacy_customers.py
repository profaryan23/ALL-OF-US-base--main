"""
Historical Customer Data Import Utility for All of Us Platform.

Parses legacy customer CSV files and backfills historical records into the CRM.
Supports standalone CLI execution, programmatic function calls, and Django management commands.

Usage:
    python import_legacy_customers.py <path_to_csv>
    python manage.py import_legacy_customers <path_to_csv>
"""
import argparse
import csv
import io
import os
import secrets
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from werkzeug.security import generate_password_hash

import main
from main import Customer, CustomerInteraction, Order, SessionLocal, User, create_activity_log
from sqlalchemy import func
from sqlalchemy.orm import Session


def parse_date(date_str: Any) -> datetime:
    """Parse various historical date formats into UTC datetime."""
    if isinstance(date_str, datetime):
        return date_str
    if not date_str or not str(date_str).strip():
        return datetime.utcnow()

    raw = str(date_str).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def parse_currency(spend_str: Any) -> Decimal:
    """Safely parse currency string (e.g. '$150.00', 'Rs 250.50', '300') into Decimal."""
    if isinstance(spend_str, (int, float, Decimal)):
        return Decimal(str(spend_str)).quantize(Decimal("0.01"))
    if not spend_str or not str(spend_str).strip():
        return Decimal("0.00")
    clean = (
        str(spend_str)
        .replace("$", "")
        .replace("Rs", "")
        .replace("NPR", "")
        .replace(",", "")
        .strip()
    )
    try:
        return Decimal(clean).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def get_or_create(
    db: Session,
    model: type = Customer,
    defaults: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Tuple[Any, bool]:
    """
    Django-style get_or_create implementation using SQLAlchemy.
    Checks for record matching kwargs (case-insensitive for email);
    if found, returns (instance, False). If not found, creates and returns (instance, True).
    """
    defaults = defaults or {}
    query = db.query(model)

    for field, val in kwargs.items():
        column = getattr(model, field, None)
        if column is not None:
            if field == "email" and isinstance(val, str):
                query = query.filter(func.lower(column) == val.lower().strip())
            else:
                query = query.filter(column == val)

    instance = query.first()
    if instance is not None:
        return instance, False

    params = dict(kwargs)
    params.update(defaults)
    # Ensure role is set to customer if creating a user/customer
    if model in (User, Customer) and "role" not in params:
        params["role"] = "customer"

    instance = model(**params)
    db.add(instance)
    db.flush()
    return instance, True


def import_legacy_customers(
    file_or_path: Any,
    db: Optional[Session] = None,
    batch_name: str = "Legacy CSV Migration",
) -> Dict[str, Any]:
    """
    Imports historical customer data from a CSV file path or file-like object.
    Maps CSV columns:
        email, first_name, last_name, phone, joined_date, total_spend, orders
    Uses get_or_create(email=...) to avoid duplicate customer records.
    Backfills historical orders to preserve customer lifetime spend and order metrics.
    """
    should_close_db = False
    if db is None:
        db = SessionLocal()
        should_close_db = True

    results = {
        "total_rows": 0,
        "created_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "errors": [],
        "created_emails": [],
    }

    try:
        # Determine whether input is file path or file-like stream
        if isinstance(file_or_path, (str, os.PathLike)):
            if not os.path.exists(file_or_path):
                raise FileNotFoundError(f"CSV file not found at: {file_or_path}")
            csv_file = open(file_or_path, mode="r", encoding="utf-8-sig")
            should_close_file = True
        else:
            csv_file = file_or_path
            should_close_file = False

        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            results["errors"].append("CSV file is empty or missing headers.")
            return results

        # Create header lookup mapping (lowercased without spaces/underscores)
        header_map = {}
        for h in reader.fieldnames:
            normalized = h.strip().lower().replace("_", "").replace(" ", "").replace("-", "")
            header_map[normalized] = h

        def get_val(row: dict, *aliases: str, default: str = "") -> str:
            for alias in aliases:
                norm = alias.strip().lower().replace("_", "").replace(" ", "").replace("-", "")
                if norm in header_map:
                    raw_val = row.get(header_map[norm])
                    if raw_val is not None and str(raw_val).strip():
                        return str(raw_val).strip()
            return default

        for row_idx, row in enumerate(reader, start=1):
            results["total_rows"] += 1

            raw_email = get_val(row, "email", "customer_email", "mail")
            if not raw_email or "@" not in raw_email or "." not in raw_email:
                results["skipped_count"] += 1
                results["errors"].append(f"Row {row_idx}: Skipped due to invalid/missing email '{raw_email}'.")
                continue

            email = raw_email.strip().lower()
            first_name = get_val(row, "first_name", "firstname", "first", "fname", default="")
            last_name = get_val(row, "last_name", "lastname", "last", "lname", default="")
            phone = get_val(row, "phone", "telephone", "mobile", "phone_number", default="")
            joined_str = get_val(row, "joined_date", "joined", "date_joined", "created_at", "date")
            spend_str = get_val(row, "total_spend", "spend", "totalspend", "lifetime_spend", default="0")
            orders_str = get_val(row, "orders", "total_orders", "order_count", default="0")
            channel_str = get_val(row, "channel", "acquisition_channel", "source", default="Direct Web")
            consent_str = get_val(row, "marketing_consent", "marketing_opt_in", "opt_in", default="no")

            joined_date = parse_date(joined_str)
            total_spend = parse_currency(spend_str)
            try:
                order_count = int(float(orders_str or 0))
            except ValueError:
                order_count = 1 if total_spend > Decimal("0.00") else 0

            is_opted_in = consent_str.lower() in ("yes", "true", "1", "on", "checked", "subscribed")
            if channel_str not in {"Direct Web", "Guest Checkout", "Store Agent Portal"}:
                channel_str = "Direct Web"

            # Prepare default attributes for Customer model
            defaults = {
                "first_name": first_name or "Valued",
                "last_name": last_name or "Customer",
                "phone": phone,
                "password_hash": generate_password_hash(secrets.token_urlsafe(32)),
                "created_at": joined_date,
                "acquisition_channel": channel_str,
                "acquisition_type": "New sign-up" if order_count <= 1 else "Repeat buyer",
                "marketing_opt_in": is_opted_in,
                "marketing_status": "subscribed" if is_opted_in else "not_opted_in",
                "role": "customer",
                "is_active": True,
            }

            customer, created = get_or_create(
                db,
                model=Customer,
                defaults=defaults,
                email=email,
            )

            if created:
                results["created_count"] += 1
                results["created_emails"].append(email)

                # Log creation interaction
                db.add(CustomerInteraction(
                    customer_id=customer.id,
                    type="system",
                    title="Historical Customer Record Imported",
                    content=f"Migrated via {batch_name}. Initial joined date set to {joined_date.strftime('%Y-%m-%d')}.",
                    author_name="System Migration",
                    created_at=datetime.utcnow(),
                ))
            else:
                results["updated_count"] += 1
                # Seamlessly backfill empty fields for existing record
                if not customer.phone and phone:
                    customer.phone = phone
                if not customer.first_name and first_name:
                    customer.first_name = first_name
                if not customer.last_name and last_name:
                    customer.last_name = last_name

            # Seamlessly backfill historical spend & order records if present
            existing_orders = [o for o in customer.orders if o.status != "Cancelled"]
            if (total_spend > Decimal("0.00") or order_count > 0) and not existing_orders:
                orders_to_create = max(1, order_count) if total_spend > Decimal("0.00") or order_count > 0 else 0
                if orders_to_create == 1:
                    db.add(Order(
                        user_id=customer.id,
                        total_amount=total_spend,
                        customer_name=f"{customer.first_name} {customer.last_name}",
                        customer_phone=customer.phone or "",
                        status="Completed",
                        channel=channel_str,
                        created_at=joined_date,
                    ))
                elif orders_to_create > 1:
                    slice_amount = (total_spend / Decimal(orders_to_create)).quantize(Decimal("0.01"))
                    remainder = total_spend - (slice_amount * (orders_to_create - 1))
                    for i in range(orders_to_create):
                        amt = remainder if i == (orders_to_create - 1) else slice_amount
                        db.add(Order(
                            user_id=customer.id,
                            total_amount=amt,
                            customer_name=f"{customer.first_name} {customer.last_name}",
                            customer_phone=customer.phone or "",
                            status="Completed",
                            channel=channel_str,
                            created_at=joined_date,
                        ))

        db.commit()
        if should_close_file:
            csv_file.close()

    except Exception as exc:
        db.rollback()
        results["errors"].append(f"Fatal migration error: {exc}")
    finally:
        if should_close_db:
            db.close()

    return results


# ============================================================================
# Django BaseCommand Compatibility Class
# ============================================================================
class Command:
    """Django management command interface for import_legacy_customers."""
    help = "Import legacy customer data from CSV file with column mapping and deduplication."

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the legacy customer CSV file.")
        parser.add_argument("--batch", type=str, default="Legacy CSV Migration", help="Batch migration name tag.")

    def handle(self, *args, **options):
        csv_file = options.get("csv_file")
        batch = options.get("batch", "Legacy CSV Migration")
        if not csv_file and args:
            csv_file = args[0]
        if not csv_file:
            print("Error: Missing required argument 'csv_file'.")
            return

        res = import_legacy_customers(csv_file, batch_name=batch)
        print("=" * 60)
        print("HISTORICAL CUSTOMER IMPORT REPORT")
        print("=" * 60)
        print(f"Total Rows Processed : {res['total_rows']}")
        print(f"New Customers Added  : {res['created_count']}")
        print(f"Existing / Updated   : {res['updated_count']}")
        print(f"Skipped Rows         : {res['skipped_count']}")
        if res["errors"]:
            print(f"Warnings / Errors    : {len(res['errors'])}")
            for err in res["errors"][:5]:
                print(f"  - {err}")
        print("=" * 60)
        return res


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import legacy customers from CSV into All of Us CRM.")
    parser.add_argument("csv_file", nargs="?", default="", help="Path to legacy customer CSV file.")
    parser.add_argument("--batch", default="Legacy CSV Migration", help="Batch name label.")
    parsed_args = parser.parse_args()

    if not parsed_args.csv_file:
        print("Usage: python import_legacy_customers.py <path_to_customers.csv>")
        sys.exit(1)

    cmd = Command()
    cmd.handle(parsed_args.csv_file, batch=parsed_args.batch)
