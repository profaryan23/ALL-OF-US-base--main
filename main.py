from __future__ import annotations

import csv
import hmac
import io
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated
from urllib.parse import quote, unquote, urlencode

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, create_engine, func, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from starlette.middleware.sessions import SessionMiddleware
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

if os.environ.get("APP_ENV", "development").lower() != "production":
    load_dotenv()

IS_PRODUCTION = os.environ.get("APP_ENV", "development").lower() == "production"
SECRET_KEY = os.environ.get("SECRET_KEY", "local-development-key-change-me")
if IS_PRODUCTION:
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
else:
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@allofus.com").strip().lower()
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
DEFAULT_ADMIN_EMAIL = ADMIN_EMAIL
DEFAULT_ADMIN_PASSWORD = ADMIN_PASSWORD
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///allofus.db")
if IS_PRODUCTION:
    if not DATABASE_URL.startswith(("postgres://", "postgresql://", "postgresql+psycopg2://")):
        raise RuntimeError("Production requires a PostgreSQL DATABASE_URL.")
    if SECRET_KEY == "local-development-key-change-me" or len(SECRET_KEY) < 32:
        raise RuntimeError("Set SECRET_KEY to a random value of at least 32 characters.")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    # Match the installed psycopg2-binary driver, independent of SQLAlchemy defaults.
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
if DATABASE_URL.startswith("sqlite"):
    engine_options = {"connect_args": {"check_same_thread": False}}
else:
    engine_options = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 0,
        "connect_args": {"connect_timeout": 10},
    }
if DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}:
    from sqlalchemy.pool import StaticPool

    engine_options["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
PRODUCT_IMAGE_DIR = Path(os.environ.get("PRODUCT_IMAGE_DIR", "static/product-images"))
MAX_PRODUCT_IMAGE_SIZE = 10 * 1024 * 1024


def initialize_product_image_directory():
    global PRODUCT_IMAGE_DIR

    try:
        PRODUCT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        # An existing directory may still be unwritable (for example, without a disk).
        with tempfile.TemporaryFile(dir=PRODUCT_IMAGE_DIR) as probe:
            probe.write(b"storage-check")
            probe.flush()
    except (PermissionError, FileNotFoundError):
        fallback = Path.cwd() / "product-images"
        logger.warning(
            "Product image storage at %s is unavailable; falling back to %s. "
            "Local uploads are ephemeral and may be lost on redeploy or restart.",
            PRODUCT_IMAGE_DIR, fallback,
        )
        fallback.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=fallback) as probe:
            probe.write(b"storage-check")
            probe.flush()
        PRODUCT_IMAGE_DIR = fallback

    # StaticFiles was mounted before lifespan startup; serve the selected directory.
    product_image_files.directory = str(PRODUCT_IMAGE_DIR)
    product_image_files.all_directories = [str(PRODUCT_IMAGE_DIR)]
    product_image_files.config_checked = False


def product_sizes(product: Product) -> list[str]:
    return [value.strip() for value in product.size_variations.split(",") if value.strip()]


SIZE_CHOICES = [(str(size), str(size)) for size in range(28, 35)] + [
    ("M", "Medium (M)"), ("L", "Large (L)"), ("XL", "Extra Large (XL)"),
]


def product_colors(product) -> list[dict]:
    return json.loads(product.color_variations or "[]")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def percentage(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or not 0 <= result <= 100:
        raise ValueError("Percentages must be between 0 and 100.")
    return money(result)


def filter_agent_orders(query, request):
    selected = request.query_params.get("agent_id", "")
    if selected == "direct":
        return query.filter(Order.agent_id.is_(None))
    if selected:
        if not selected.isdigit():
            raise HTTPException(status_code=400, detail="Invalid agent filter")
        return query.filter(Order.agent_id == int(selected))
    return query


async def read_product_colors(form, product=None):
    names = form.getlist("color_name")
    if len(names) > 20:
        raise ValueError("Use no more than 20 colors per product.")
    existing = {c["name"]: c for c in product_colors(product)} if product else {}
    hex_values = form.getlist("color_hex")
    colors, seen = [], set()
    images = []
    for index, raw_name in enumerate(names):
        name = str(raw_name).strip()
        if not name:
            continue
        if len(name) > 60 or name.casefold() in seen:
            raise ValueError("Color names must be unique and at most 60 characters.")
        seen.add(name.casefold())
        photo = await read_product_image({"photo": form.get(f"color_photo_{index}")})

        hex_code = ""
        if form.get(f"color_hex_{index}"):
            hex_code = str(form.get(f"color_hex_{index}")).strip()
        elif index < len(hex_values) and hex_values[index]:
            hex_code = str(hex_values[index]).strip()

        existing_c = existing.get(name, {})
        if not hex_code:
            hex_code = existing_c.get("hex") or existing_c.get("swatch") or "#222222"

        photo_path = form.get(f"color_existing_photo_{index}") or existing_c.get("photo_path", "")
        if form.get(f"remove_color_photo_{index}") == "on":
            photo_path = ""

        colors.append({
            "name": name,
            "hex": hex_code,
            "photo_path": photo_path,
            "filter": existing_c.get("filter", "none")
        })
        images.append(photo)
    for color, image in zip(colors, images):
        if image:
            color["photo_path"] = save_product_image(image)
    return json.dumps(colors)


def cart_product_and_size(line_key: str) -> tuple[int, str]:
    product_id, separator, size = line_key.partition(":")
    return int(product_id), unquote(size.split(":", 1)[0]) if separator else ""


def cart_line_key(product_id: int, size: str, color: str = "") -> str:
    key = f"{product_id}:{quote(size, safe='')}"
    return f"{key}:{quote(color, safe='')}" if color else key


def cart_color(line_key):
    parts = line_key.split(":", 2)
    return unquote(parts[2]) if len(parts) == 3 else ""


async def read_product_image(form) -> tuple[str, bytes] | None:
    photo = form.get("photo")
    if not photo or not getattr(photo, "filename", ""):
        return None
    content = await photo.read(MAX_PRODUCT_IMAGE_SIZE + 1)
    if len(content) > MAX_PRODUCT_IMAGE_SIZE:
        raise ValueError("Product photos must be 10 MB or smaller.")
    if content.startswith(b"\xff\xd8\xff"):
        extension = ".jpg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = ".png"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        extension = ".webp"
    else:
        raise ValueError("Upload a valid JPEG, PNG, or WebP product photo.")
    return extension, content


def save_product_image(image: tuple[str, bytes]) -> str:
    extension, content = image
    PRODUCT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_hex(16)}{extension}"
    (PRODUCT_IMAGE_DIR / filename).write_bytes(content)
    return f"product-images/{filename}"


def parse_product_fields(form) -> dict:
    name = str(form.get("name", "")).strip()
    category = str(form.get("category", "")).strip()
    shop_category = str(form.get("shop_category", "")).strip()
    description = str(form.get("description", "")).strip()
    raw_sizes = str(form.get("size_variations", "")).replace("\n", ",")
    sizes = list(dict.fromkeys(value.strip() for value in raw_sizes.split(",") if value.strip()))
    if form.get("size_choices_present"):
        sizes = list(dict.fromkeys(form.getlist("sizes") + sizes))
    if (
        not name or len(name) > 140
        or not category or len(category) > 100
        or not shop_category or len(shop_category) > 100
        or len(description) > 3000
        or len(sizes) > 12 or any(len(size) > 80 for size in sizes)
    ):
        raise ValueError("Check the product name, categories, description, and size variations.")
    price = Decimal(str(form.get("price", "")))
    stock = int(str(form.get("stock_quantity", "")))
    raw_cogs = form.get("cogs")
    cogs = Decimal("0.00")
    if raw_cogs:
        try:
            cogs = Decimal(str(raw_cogs))
            if cogs < 0:
                cogs = Decimal("0.00")
        except (InvalidOperation, ValueError):
            cogs = Decimal("0.00")
    if not price.is_finite() or price <= 0 or stock < 0:
        raise ValueError("Enter a positive price and a non-negative stock quantity.")
    return {
        "name": name,
        "category": category,
        "shop_category": shop_category,
        "description": description,
        "size_variations": ", ".join(sizes),
        "price": price,
        "cogs": cogs,
        "stock_quantity": stock,
        "is_active": form.get("is_active") == "on",
    }


def migrate_catalog_schema():
    migrations = {
        "products": {
            "color_variations": "TEXT NOT NULL DEFAULT '[]'",
            "category": "VARCHAR(100) NOT NULL DEFAULT ''",
            "shop_category": "VARCHAR(100) NOT NULL DEFAULT ''",
            "photo_path": "VARCHAR(255) NOT NULL DEFAULT ''",
            "size_variations": "TEXT NOT NULL DEFAULT ''",
            "cogs": "NUMERIC(10, 2) NOT NULL DEFAULT 0.00",
            "display_order": "INTEGER NOT NULL DEFAULT 0",
        },
        "order_items": {
            "color_variation": "VARCHAR(60) NOT NULL DEFAULT ''",
            "allocation_id": "INTEGER REFERENCES agent_allocations(id)",
            "agent_unit_cost": "NUMERIC(10, 2) NOT NULL DEFAULT 0.00",
            "company_discount_percent": "NUMERIC(5, 2) NOT NULL DEFAULT 0.00",
            "commission_percent": "NUMERIC(5, 2) NOT NULL DEFAULT 0.00",
            "commission_amount": "NUMERIC(10, 2) NOT NULL DEFAULT 0.00",
            "size_variation": "VARCHAR(80) NOT NULL DEFAULT ''",
        },
        "orders": {
            "agent_id": "INTEGER REFERENCES agents(id)",
            "channel": "VARCHAR(40) NOT NULL DEFAULT 'Online delivery'",
            "carrier": "VARCHAR(100) NOT NULL DEFAULT ''",
            "tracking_number": "VARCHAR(120) NOT NULL DEFAULT ''",
            "vendor_batch_id": "VARCHAR(100) NOT NULL DEFAULT ''",
            "shipping_address": "VARCHAR(300) NOT NULL DEFAULT ''",
            "promo_code": "VARCHAR(50) NOT NULL DEFAULT ''",
            "gateway_ref": "VARCHAR(100) NOT NULL DEFAULT ''",
            "tax_amount": "NUMERIC(10, 2) NOT NULL DEFAULT 0.00",
            "discount_amount": "NUMERIC(10, 2) NOT NULL DEFAULT 0.00",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in migrations.items():
            if table_name not in inspector.get_table_names():
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    try:
                        connection.execute(text(
                            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                        ))
                    except Exception as exc:
                        logger.warning(f"Skipping alter table {table_name} add {column_name}: {exc}")
        try:
            connection.execute(text(
                "UPDATE products SET category = 'General' WHERE category = ''"
            ))
            connection.execute(text(
                "UPDATE products SET shop_category = 'Everyday' WHERE shop_category = ''"
            ))
        except Exception as exc:
            logger.warning(f"Skipping category updates: {exc}")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(40), default="")
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(30), default="customer")
    profile_image: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    orders: Mapped[list["Order"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin_like(self) -> bool:
        return self.role in {"admin", "super_admin", "developer"}


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[str] = mapped_column(String(24), default="ASSET")
    normal_balance: Mapped[str] = mapped_column(String(8), default="DEBIT")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    journal_lines: Mapped[list["JournalLine"]] = relationship(back_populates="account")


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reference_type: Mapped[str] = mapped_column(String(30), default="ORDER")
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    lines: Mapped[list["JournalLine"]] = relationship(back_populates="journal_entry", cascade="all, delete-orphan")

    @property
    def total_debit(self) -> Decimal:
        return sum((line.debit for line in self.lines), Decimal("0.00"))

    @property
    def total_credit(self) -> Decimal:
        return sum((line.credit for line in self.lines), Decimal("0.00"))


class JournalLine(Base):
    __tablename__ = "journal_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    journal_entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    debit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    credit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    journal_entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship(back_populates="journal_lines")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140))
    category: Mapped[str] = mapped_column(String(100), default="General")
    shop_category: Mapped[str] = mapped_column(String(100), default="Everyday")
    photo_path: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    size_variations: Mapped[str] = mapped_column(Text, default="")
    color_variations: Mapped[str] = mapped_column(Text, default="[]")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    cogs: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140))
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    profile_image: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentAllocation(Base):
    __tablename__ = "agent_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    remaining: Mapped[int] = mapped_column(Integer)
    size_variation: Mapped[str] = mapped_column(String(80), default="")
    color_variation: Mapped[str] = mapped_column(String(60), default="")
    list_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    company_discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    agent: Mapped[Agent] = relationship()
    product: Mapped[Product] = relationship()


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    agent: Mapped[Agent | None] = relationship()
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(24), default="Pending")
    channel: Mapped[str] = mapped_column(String(40), default="Online delivery")
    carrier: Mapped[str] = mapped_column(String(100), default="")
    tracking_number: Mapped[str] = mapped_column(String(120), default="")
    vendor_batch_id: Mapped[str] = mapped_column(String(100), default="")
    shipping_address: Mapped[str] = mapped_column(String(300), default="")
    promo_code: Mapped[str] = mapped_column(String(50), default="")
    gateway_ref: Mapped[str] = mapped_column(String(100), default="")
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    service_requests: Mapped[list["OrderServiceRequest"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    size_variation: Mapped[str] = mapped_column(String(80), default="")
    color_variation: Mapped[str] = mapped_column(String(60), default="")
    allocation_id: Mapped[int | None] = mapped_column(ForeignKey("agent_allocations.id"), nullable=True)
    agent_unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    company_discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    commission_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    price_at_purchase: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class OrderServiceRequest(Base):
    __tablename__ = "order_service_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="Requested")
    notes: Mapped[str] = mapped_column(String(500), default="")
    admin_note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    order: Mapped[Order] = relationship(back_populates="service_requests")


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    page_path: Mapped[str] = mapped_column(String(255))
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PageContent(Base):
    __tablename__ = "page_content"
    id: Mapped[int] = mapped_column(primary_key=True)
    page_key: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    hero_eyebrow: Mapped[str] = mapped_column(String(100), default="")
    hero_heading: Mapped[str] = mapped_column(String(240), default="")
    hero_intro: Mapped[str] = mapped_column(Text, default="")
    hero_cta_label: Mapped[str] = mapped_column(String(80), default="")
    hero_cta_url: Mapped[str] = mapped_column(String(200), default="")
    site_announcement: Mapped[str] = mapped_column(String(240), default="")
    hero_video_caption: Mapped[str] = mapped_column(String(120), default="")
    footer_tagline: Mapped[str] = mapped_column(String(240), default="")
    section_eyebrow: Mapped[str] = mapped_column(String(100), default="")
    section_heading: Mapped[str] = mapped_column(String(240), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    closing_heading: Mapped[str] = mapped_column(String(240), default="")
    closing_copy: Mapped[str] = mapped_column(Text, default="")
    meta_description: Mapped[str] = mapped_column(String(320), default="")
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    hero_image_path: Mapped[str] = mapped_column(String(255), default="images/home-hero.png")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContactMessage(Base):
    __tablename__ = "contact_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(160), default="")
    module: Mapped[str] = mapped_column(String(60), default="system")
    action: Mapped[str] = mapped_column(String(120), default="updated")
    entity_type: Mapped[str] = mapped_column(String(60), default="record")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


PAGE_DEFAULTS = {
    "shop": {
        "hero_eyebrow": "THE COLLECTION",
        "hero_heading": "Shop Essentials",
        "hero_intro": "Thoughtful, relaxed-fit pieces for your everyday wardrobe, slow mornings, and timeless styling.",
        "hero_cta_label": "Explore collection",
        "hero_cta_url": "/shop",
        "hero_image_path": "images/home-hero.png",
        "site_announcement": "A little more room for the good things in life · Free delivery over $75",
        "hero_video_caption": "ALL OF US / THE COLLECTION",
        "footer_tagline": "Good things are better together.",
        "section_eyebrow": "All essentials",
        "section_heading": "Designed for everyday life.",
        "body": "Explore our circular essentials orbit: wide-leg denims, twill sets, henley tops, and hoodies.",
        "closing_heading": "Made for being together.",
        "closing_copy": "Thoughtful pieces for slow mornings, relaxed days, and every moment between.",
        "meta_description": "Shop the All of Us collection — animated stitched-circle apparel selector with product details, size/color/quantity selection, and a multi-item demo shopping bag.",
        "published": True,
    },

    "home": {
        "hero_eyebrow": "MADE FOR EVERYDAY TOGETHER",
        "hero_heading": "Good things have a way of bringing us in.",
        "hero_intro": "Thoughtful pieces for the rituals, rooms, and people that make a life feel like yours.",
        "hero_cta_label": "Find your something",
        "hero_cta_url": "/shop",
        "hero_image_path": "images/campaign-duo.png",
        "site_announcement": "A little more room for the good things in life · Free delivery over $75",
        "hero_video_caption": "ALL OF US / THE COLLECTION",
        "footer_tagline": "Good things are better together.",
        "section_eyebrow": "OUR STORY",
        "section_heading": "Made by friends, for all of us.",
        "body": "Heavyweight fleece, honest denim and soft ribbed cotton — pieces cut roomy, built to last, and made to be shared.",
        "closing_heading": "Shop the collection",
        "closing_copy": "All of Us · 2026",
        "meta_description": "Thoughtful everyday pieces for the rituals, rooms, and people that make a life feel like yours.",
        "published": True,
    },
    "about": {
        "hero_eyebrow": "A little more like home",
        "hero_heading": "Good things are better together.",
        "hero_intro": "We believe the everyday feels more meaningful when it brings people together.",
        "hero_cta_label": "Explore the shop",
        "hero_cta_url": "/#shop",
        "site_announcement": "A little more room for the good things in life · Free delivery over $75",
        "hero_video_caption": "ALL OF US / A SHORT FILM",
        "footer_tagline": "Good things are better together.",
        "section_eyebrow": "Our story",
        "section_heading": "Made for being together.",
        "body": "All of Us is a collection of thoughtful pieces for the rituals, rooms, and people that make a life feel like yours.\n\nWe choose useful, considered objects that find their way into everyday moments: a shared meal, a slow morning, or a small kindness.",
        "closing_heading": "",
        "closing_copy": "",
        "meta_description": "Get to know All of Us and our thoughtful pieces for everyday life and being together.",
        "published": True,
    },
    "contact": {
        "hero_eyebrow": "We'd love to hear from you",
        "hero_heading": "Let's make a connection.",
        "hero_intro": "Questions about an order, a product, or anything else? Send us a note.",
        "hero_cta_label": "",
        "hero_cta_url": "",
        "site_announcement": "A little more room for the good things in life · Free delivery over $75",
        "hero_video_caption": "ALL OF US / A SHORT FILM",
        "footer_tagline": "Good things are better together.",
        "section_eyebrow": "Get in touch",
        "section_heading": "Write us a note.",
        "body": "Use the form below and our team will be in touch.",
        "closing_heading": "",
        "closing_copy": "",
        "meta_description": "Contact All of Us with questions about products, orders, or anything else.",
        "published": True,
    },
}


def track_event(db: Session, request: Request, event_type: str, product_id: int | None = None):
    session_id = request.session.get("visitor_id")
    if not session_id:
        session_id = secrets.token_urlsafe(16)
        request.session["visitor_id"] = session_id
    db.add(AnalyticsEvent(
        event_type=event_type,
        page_path=request.url.path,
        session_id=session_id,
        user_id=request.session.get("user_id"),
        product_id=product_id,
    ))
    db.commit()


def seed_database():
    resolve_admin_credentials_from_environment()
    admin_credentials_valid = bool(ADMIN_EMAIL and ADMIN_PASSWORD)
    if IS_PRODUCTION:
        admin_credentials_valid = admin_credentials_valid and ADMIN_PASSWORD != "admin123" and len(ADMIN_PASSWORD) >= 16
    if not admin_credentials_valid:
        logger.warning(
            "Skipping admin seeding: set ADMIN_EMAIL and a unique ADMIN_PASSWORD "
            "of at least 16 characters in production. Existing accounts are unchanged."
        )
    with SessionLocal.begin() as db:
        if admin_credentials_valid:
            configured_admin = db.query(User).filter_by(email=ADMIN_EMAIL).first()
            existing_admins = db.query(User).filter_by(role="admin").all()
            if configured_admin is None:
                if existing_admins:
                    primary_admin = existing_admins[0]
                    primary_admin.first_name = "All of Us"
                    primary_admin.last_name = "Admin"
                    primary_admin.email = ADMIN_EMAIL
                    primary_admin.password_hash = generate_password_hash(ADMIN_PASSWORD)
                    primary_admin.role = "admin"
                    for duplicate in existing_admins[1:]:
                        db.delete(duplicate)
                else:
                    db.add(User(
                        first_name="All of Us", last_name="Admin", email=ADMIN_EMAIL,
                        password_hash=generate_password_hash(ADMIN_PASSWORD), role="admin",
                    ))
            else:
                configured_admin.first_name = "All of Us"
                configured_admin.last_name = "Admin"
                configured_admin.password_hash = generate_password_hash(ADMIN_PASSWORD)
                configured_admin.role = "admin"
                for duplicate in [admin for admin in existing_admins if admin.id != configured_admin.id]:
                    db.delete(duplicate)
        existing_account_codes = {row[0] for row in db.query(Account.code).all()}
        for account in [
            Account(code="1000", name="Cash and Cash Equivalents", type="ASSET", normal_balance="DEBIT"),
            Account(code="1100", name="Inventory", type="ASSET", normal_balance="DEBIT"),
            Account(code="2000", name="Accounts Payable", type="LIABILITY", normal_balance="CREDIT"),
            Account(code="3000", name="Owner Equity", type="EQUITY", normal_balance="CREDIT"),
            Account(code="4000", name="Sales Revenue", type="REVENUE", normal_balance="CREDIT"),
            Account(code="5000", name="Cost of Goods Sold", type="EXPENSE", normal_balance="DEBIT"),
            Account(code="5100", name="Merchant Fees and Bank Charges", type="EXPENSE", normal_balance="DEBIT"),
            Account(code="5200", name="Operating Expense", type="EXPENSE", normal_balance="DEBIT"),
        ]:
            if account.code not in existing_account_codes:
                db.add(account)
                existing_account_codes.add(account.code)
        if db.query(Product).count() == 0:
            db.add_all([
                Product(name="Everyday Tote", description="A sturdy carryall made for everyday errands.", price=Decimal("28.00"), stock_quantity=18),
                Product(name="Sunday Ceramic Set", description="Hand-finished mugs for slow mornings.", price=Decimal("42.00"), stock_quantity=12),
                Product(name="Gathering Candle", description="A clean-burning candle with warm cedar and citrus notes.", price=Decimal("24.00"), stock_quantity=25),
                Product(name="Together Journal", description="A clothbound journal for plans, lists, and little ideas.", price=Decimal("19.00"), stock_quantity=30),
            ])
        for page_key, content in PAGE_DEFAULTS.items():
            existing_page = db.query(PageContent).filter_by(page_key=page_key).first()
            if not existing_page:
                db.add(PageContent(page_key=page_key, **content))
            else:
                for field in ("site_announcement", "hero_video_caption", "footer_tagline"):
                    if not getattr(existing_page, field):
                        setattr(existing_page, field, content[field])
                if page_key == "home" and existing_page.hero_cta_url in {"#shop", "/#shop"}:
                    existing_page.hero_cta_url = "/shop"
        for idx, prod in enumerate(db.query(Product).order_by(Product.id).all(), start=1):
            if prod.display_order == 0 or prod.display_order is None:
                prod.display_order = idx
        db.commit()


def migrate_page_content():
    columns_to_add = {
        "site_announcement": "VARCHAR(240) NOT NULL DEFAULT ''",
        "hero_video_caption": "VARCHAR(120) NOT NULL DEFAULT ''",
        "footer_tagline": "VARCHAR(240) NOT NULL DEFAULT ''",
        "hero_image_path": "VARCHAR(255) NOT NULL DEFAULT 'images/campaign-duo.png'",
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "page_content" not in inspector.get_table_names():
            return
        existing_columns = {column["name"] for column in inspector.get_columns("page_content")}
        for column_name, column_type in columns_to_add.items():
            if column_name not in existing_columns:
                try:
                    connection.execute(text(
                        f"ALTER TABLE page_content ADD COLUMN {column_name} {column_type}"
                    ))
                except Exception as exc:
                    logger.warning(f"Skipping alter table page_content add {column_name}: {exc}")


def migrate_accounting_schema():
    is_postgres = engine.dialect.name == "postgresql"
    bool_def = "BOOLEAN NOT NULL DEFAULT TRUE"
    time_def = "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP" if is_postgres else "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
    table_columns = {
        "users": {
            "profile_image": "VARCHAR(255) NOT NULL DEFAULT ''",
            "is_active": bool_def,
        },
        "agents": {
            "profile_image": "VARCHAR(255) NOT NULL DEFAULT ''",
        },
        "accounts": {
            "code": "VARCHAR(32) NOT NULL DEFAULT ''",
            "name": "VARCHAR(160) NOT NULL DEFAULT ''",
            "type": "VARCHAR(24) NOT NULL DEFAULT 'ASSET'",
            "normal_balance": "VARCHAR(8) NOT NULL DEFAULT 'DEBIT'",
            "is_active": bool_def,
        },
        "journal_entries": {
            "date": time_def,
            "reference_type": "VARCHAR(30) NOT NULL DEFAULT 'ORDER'",
            "reference_id": "INTEGER",
            "description": "VARCHAR(500) NOT NULL DEFAULT ''",
            "created_at": time_def,
        },
        "journal_lines": {
            "journal_entry_id": "INTEGER NOT NULL DEFAULT 0",
            "account_id": "INTEGER NOT NULL DEFAULT 0",
            "debit": "NUMERIC(14, 2) NOT NULL DEFAULT 0.00",
            "credit": "NUMERIC(14, 2) NOT NULL DEFAULT 0.00",
        },
        "activity_logs": {
            "actor_id": "INTEGER",
            "actor_name": "VARCHAR(160) NOT NULL DEFAULT ''",
            "module": "VARCHAR(60) NOT NULL DEFAULT 'system'",
            "action": "VARCHAR(120) NOT NULL DEFAULT 'updated'",
            "entity_type": "VARCHAR(60) NOT NULL DEFAULT 'record'",
            "entity_id": "INTEGER",
            "details": "TEXT NOT NULL DEFAULT ''",
            "created_at": time_def,
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in table_columns.items():
            if table_name not in inspector.get_table_names():
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    try:
                        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
                    except Exception as exc:
                        logger.warning(f"Skipping alter table {table_name} add {column_name}: {exc}")


def create_activity_log(db: Session, *, actor: User | None, module: str, action: str, entity_type: str, entity_id: int | None = None, details: str = "") -> ActivityLog | None:
    if actor is None:
        return None
    log = ActivityLog(
        actor_id=actor.id,
        actor_name=f"{actor.first_name} {actor.last_name}".strip() or actor.email,
        module=module,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(log)
    return log


def get_account_balance(db: Session, account_id: int, as_of: datetime | None = None) -> Decimal:
    statement = (
        db.query(
            func.coalesce(func.sum(JournalLine.debit), Decimal("0.00")) -
            func.coalesce(func.sum(JournalLine.credit), Decimal("0.00"))
        )
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .filter(JournalLine.account_id == account_id)
    )
    if as_of is not None:
        statement = statement.filter(JournalEntry.date <= as_of)
    total = statement.scalar() or Decimal("0.00")
    return Decimal(str(total))


def post_journal_entry(db: Session, *, date: datetime, reference_type: str, reference_id: int | None, description: str, lines: list[dict]) -> JournalEntry:
    if not lines:
        raise ValueError("A journal entry requires at least one line item.")

    normalized_lines = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    for line in lines:
        account = db.get(Account, int(line["account_id"]))
        if account is None or not account.is_active:
            raise ValueError("Every journal line must reference an active account.")
        debit = money(line.get("debit", 0) or Decimal("0.00"))
        credit = money(line.get("credit", 0) or Decimal("0.00"))
        if debit < 0 or credit < 0:
            raise ValueError("Journal line amounts cannot be negative.")
        if debit and credit:
            raise ValueError("Journal lines must be either debit or credit, not both.")
        total_debit += debit
        total_credit += credit
        normalized_lines.append({
            "account_id": account.id,
            "debit": debit,
            "credit": credit,
        })

    if total_debit == Decimal("0.00") and total_credit == Decimal("0.00"):
        raise ValueError("Journal entry totals cannot be zero.")
    if total_debit != total_credit:
        raise ValueError("Journal entry failed validation: debits must equal credits.")

    entry = JournalEntry(
        date=date,
        reference_type=str(reference_type or "ORDER").upper(),
        reference_id=reference_id,
        description=str(description or "")[:500],
    )
    with db.begin():
        db.add(entry)
        db.flush()
        db.add_all([
            JournalLine(
                journal_entry_id=entry.id,
                account_id=item["account_id"],
                debit=item["debit"],
                credit=item["credit"],
            )
            for item in normalized_lines
        ])
        db.flush()
    return entry


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_product_image_directory()
    bundled_images = Path("static/product-images")
    if bundled_images.exists() and bundled_images.resolve() != PRODUCT_IMAGE_DIR.resolve():
        for source in bundled_images.iterdir():
            destination = PRODUCT_IMAGE_DIR / source.name
            if source.is_file() and not destination.exists():
                shutil.copy2(source, destination)
    Base.metadata.create_all(engine)
    migrate_catalog_schema()
    migrate_page_content()
    migrate_accounting_schema()
    seed_database()
    yield


app = FastAPI(title="All of Us", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=IS_PRODUCTION or os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)
product_image_files = StaticFiles(directory=str(PRODUCT_IMAGE_DIR), check_dir=False)
app.mount("/static/product-images", product_image_files, name="product_images")
app.mount("/static", StaticFiles(directory="static"), name="static")


def template_context(request: Request):
    user_id = request.session.get("user_id")
    admin_pending_orders_count = 0
    admin_order_notifications = []
    with SessionLocal() as db:
        user = db.get(User, user_id) if user_id else None
        page_contents = {
            item.page_key: item
            for item in db.query(PageContent).filter(
                PageContent.page_key.in_(("home", "about", "contact", "shop"))
            ).all()
        }
        if user and user.is_admin_like:
            admin_pending_orders_count = db.query(Order).filter(Order.status == "Pending").count()
            recent_orders = (
                db.query(Order)
                .order_by(Order.created_at.desc())
                .limit(8)
                .all()
            )
            for o in recent_orders:
                cust_name = f"{o.user.first_name} {o.user.last_name}" if o.user else "Customer"
                admin_order_notifications.append({
                    "id": o.id,
                    "order_number": f"#{o.id:04d}",
                    "customer_name": cust_name,
                    "customer_email": o.user.email if o.user else "",
                    "total_amount": float(o.total_amount),
                    "status": o.status,
                    "created_at": o.created_at,
                    "items_count": sum(it.quantity for it in o.items),
                })
        agents_list = db.query(Agent).order_by(Agent.name).all()
    cart = request.session.get("cart", {})
    message = request.session.pop("flash", None)

    def csrf_token():
        if "csrf_token" not in request.session:
            request.session["csrf_token"] = secrets.token_urlsafe(32)
        return request.session["csrf_token"]

    def get_flashed_messages(with_categories=False):
        if not message:
            return []
        return [message] if with_categories else [message[1]]

    def template_url_for(endpoint, **values):
        if endpoint == "static" and "filename" in values:
            values["path"] = values.pop("filename")
        route = next((item for item in request.app.routes if getattr(item, "name", None) == endpoint), None)
        path_names = set(getattr(route, "param_convertors", {}))
        path_params = {key: values.pop(key) for key in list(values) if key in path_names}
        result = str(request.url_for(endpoint, **path_params))
        if values:
            result += ("&" if "?" in result else "?") + urlencode(values, doseq=True)
        return result

    return {
        "current_user": user,
        "site_content": page_contents.get("home"),
        "about_content": page_contents.get("about"),
        "contact_content": page_contents.get("contact"),
        "shop_content": page_contents.get("shop"),
        "cart_count": sum(int(quantity) for quantity in cart.values()),
        "csrf_token": csrf_token,
        "get_flashed_messages": get_flashed_messages,
        "url_for": template_url_for,
        "size_choices": SIZE_CHOICES,
        "product_colors": product_colors,
        "agents": agents_list,
        "selected_agent": request.query_params.get("agent_id", ""),
        "admin_pending_orders_count": admin_pending_orders_count,
        "admin_order_notifications": admin_order_notifications,
    }


templates = Jinja2Templates(directory="templates", context_processors=[template_context])

ADMIN_MODULES = {
    "overview": ("Overview", "admin_dashboard"),
    "content": ("Content", "admin_content"),
    "crm": ("CRM", "admin_crm"),
    "rbac": ("RBAC", "admin_rbac"),
    "users": ("Users", "admin_users"),
    "inventory": ("Inventory", "admin_inventory"),
    "agents": ("Agents", "admin_agents"),
    "sales": ("Sales", "admin_sales"),
    "orders": ("Orders", "admin_orders"),
    "accounts": ("Accounts", "admin_accounts"),
    "analytics": ("Website analytics", "admin_analytics"),
    "activities": ("Activities", "admin_activities"),
    "reports": ("Reports", "admin_reports"),
}

ROLE_LABELS = {
    "customer": "Customer",
    "agent": "Agent",
    "admin": "Admin",
    "super_admin": "Super admin",
    "developer": "Developer",
}

RBAC_ROLE_PERMISSIONS = {
    "admin": [
        "Create and manage user accounts for agents and customers",
        "Approve and monitor CRM records",
        "Edit products, inventory, content, and orders",
        "Review financial accounts and activity logs",
    ],
    "agent": [
        "View assigned product allocations and sales records",
        "Track commissions and agent-specific performance",
        "Submit sales updates tied to customer orders",
        "Access only their operational data",
    ],
    "customer": [
        "View own profile and purchase history",
        "Manage orders and shipping/exchange requests",
        "Self-service account maintenance",
        "Customer actions are logged into CRM and Activities",
    ],
    "super_admin": [
        "Full platform access and role overrides",
        "Manage all admin, agent, and customer accounts",
        "Review activities and audit trail across CRM",
    ],
    "developer": [
        "Technical system access and schema changes",
        "Monitor platform operations and diagnostics",
        "Extended permissions with full operational review",
    ],
}


def get_db():
    with SessionLocal() as db:
        yield db


@app.get("/healthz", include_in_schema=False)
def health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ok"}


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]):
    user_id = request.session.get("user_id")
    admin_pending_orders_count = 0
    admin_order_notifications = []
    return db.get(User, user_id) if user_id else None


def require_user(user: Annotated[User | None, Depends(get_current_user)]):
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def resolve_admin_credentials_from_environment():
    global ADMIN_EMAIL, ADMIN_PASSWORD
    if IS_PRODUCTION:
        ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
        return
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@allofus.com").strip().lower()
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def normalize_role(role: str | None) -> str:
    value = str(role or "customer").strip().lower()
    return value if value in ROLE_LABELS else "customer"


def user_has_any_role(user: User | None, *roles: str) -> bool:
    if not user:
        return False
    normalized = normalize_role(user.role)
    return normalized in {normalize_role(role) for role in roles}


def user_is_admin(user: User | None) -> bool:
    return bool(user) and user.role in {"admin", "super_admin", "developer"}


def user_can_manage_role(user: User | None, target_role: str | None) -> bool:
    if not user or not user.is_active:
        return False
    target = normalize_role(target_role)
    if user.role == "developer":
        return True
    if user.role == "super_admin":
        return target in {"customer", "agent", "admin", "super_admin", "developer"}
    if user.role == "admin":
        return target in {"customer", "agent"}
    return False


def require_admin(user: Annotated[User | None, Depends(get_current_user)]):
    if not user_is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def verify_csrf(request: Request):
    form = await request.form()
    supplied = str(form.get("csrf_token", ""))
    expected = request.session.get("csrf_token", "")
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=400, detail="Invalid form token. Refresh and try again.")


def page(request: Request, template: str, **context):
    context.setdefault("form_data", {})
    if request.url.path.startswith("/admin"):
        module = request.url.path.split("/")[2] if request.url.path.count("/") > 1 else "overview"
        if module == "search":
            module = request.query_params.get("module", "overview")
        if module == "products":
            module = "inventory"
        if module == "all":
            context.setdefault("active_module", "all")
            context.setdefault("module_label", "All modules")
        elif module not in ADMIN_MODULES:
            module = "overview"
            context.setdefault("active_module", module)
            context.setdefault("module_label", ADMIN_MODULES[module][0])
        else:
            context.setdefault("active_module", module)
            context.setdefault("module_label", ADMIN_MODULES[module][0])
    return templates.TemplateResponse(request=request, name=template, context=context)


def safe_redirect(request: Request, endpoint: str):
    return RedirectResponse(str(request.url_for(endpoint)), status_code=303)


def filtered_customers(db: Session, request: Request, default_opt_in=""):
    query = db.query(User).filter_by(role="customer")
    opt_in = request.query_params.get("opt_in", default_opt_in)
    purchased = request.query_params.get("purchased", "")
    minimum = request.query_params.get("min_spend", "").strip()
    if opt_in in {"yes", "no"}:
        query = query.filter(User.marketing_opt_in == (opt_in == "yes"))
    if purchased == "yes":
        query = query.filter(User.orders.any())
    elif purchased == "no":
        query = query.filter(~User.orders.any())
    customers = query.order_by(User.created_at.desc()).all()
    if minimum:
        try:
            threshold = Decimal(minimum)
            customers = [customer for customer in customers if sum((order.total_amount for order in customer.orders), Decimal("0.00")) >= threshold]
        except InvalidOperation:
            pass
    return customers


@app.get("/", name="storefront", response_class=HTMLResponse)
def storefront(request: Request, db: Annotated[Session, Depends(get_db)]):
    home_page = db.query(PageContent).filter_by(page_key="home").first()
    products = db.query(Product).filter_by(is_active=True).order_by(Product.id).all()
    track_event(db, request, "page_view")
    return page(request, "store.html", products=products, home_page=home_page)


@app.get("/shop", name="shop_page", response_class=HTMLResponse)
def shop_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    shop_page_content = db.query(PageContent).filter_by(page_key="shop").first()
    available_products = db.query(Product).filter_by(is_active=True).order_by(Product.display_order.asc(), Product.id.asc()).all()
    shop_categories = sorted({product.shop_category for product in available_products if product.shop_category})
    selected_shop_category = request.query_params.get("shop_category", "").strip()
    products = [
        product for product in available_products
        if not selected_shop_category or product.shop_category == selected_shop_category
    ]
    track_event(db, request, "page_view")
    return page(
        request, "shop.html", products=products,
        shop_page=shop_page_content,
        shop_categories=shop_categories, selected_shop_category=selected_shop_category,
    )


@app.get("/shop/product/{product_id}", name="product_detail", response_class=HTMLResponse)
def product_detail(product_id: int, request: Request, db: Annotated[Session, Depends(get_db)]):
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")
    track_event(db, request, "page_view", product.id)
    return page(
        request, "product_detail.html", product=product,
        meta_description=product.description[:160] or f"Explore {product.name} from All of Us.",
    )


@app.get("/about", name="about_page", response_class=HTMLResponse)
def about_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    content = db.query(PageContent).filter_by(page_key="about", published=True).first()
    if not content:
        raise HTTPException(status_code=404, detail="Page not found")
    track_event(db, request, "page_view")
    return page(request, "content_page.html", content=content)


@app.get("/contact", name="contact_page", response_class=HTMLResponse)
def contact_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    content = db.query(PageContent).filter_by(page_key="contact", published=True).first()
    if not content:
        raise HTTPException(status_code=404, detail="Page not found")
    track_event(db, request, "page_view")
    return page(request, "contact.html", content=content)


@app.post("/contact", name="contact_submit", dependencies=[Depends(verify_csrf)])
async def contact_submit(request: Request, db: Annotated[Session, Depends(get_db)]):
    content = db.query(PageContent).filter_by(page_key="contact", published=True).first()
    if not content:
        raise HTTPException(status_code=404, detail="Page not found")
    form = await request.form()
    name = str(form.get("name", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    subject = str(form.get("subject", "")).strip()
    message = str(form.get("message", "")).strip()
    if (
        not name or len(name) > 100
        or len(email) > 255 or "@" not in email or "." not in email.rsplit("@", 1)[-1]
        or not subject or len(subject) > 160
        or len(message) < 10 or len(message) > 3000
    ):
        request.session["flash"] = ["error", "Add your name, a valid email, a subject, and a message between 10 and 3000 characters."]
        return RedirectResponse("/contact", status_code=303)
    db.add(ContactMessage(name=name, email=email, subject=subject, message=message))
    db.commit()
    track_event(db, request, "contact_submit")
    request.session["flash"] = ["success", "Thanks for reaching out. Your message has been received."]
    return RedirectResponse("/contact", status_code=303)


@app.get("/register", name="register", response_class=HTMLResponse)
def register_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    track_event(db, request, "registration_view")
    return page(request, "auth.html", mode="register")


@app.post("/register", name="register_submit", dependencies=[Depends(verify_csrf)], response_class=HTMLResponse)
async def register_submit(request: Request, db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    first_name = str(form.get("first_name", "")).strip()
    last_name = str(form.get("last_name", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    phone = str(form.get("phone", "")).strip()
    if not first_name or not last_name or "@" not in email or len(password) < 8:
        return page(request, "auth.html", mode="register", error="Add your name, a valid email, and a password with at least 8 characters.", form_data=dict(form))
    if db.query(User).filter_by(email=email).first():
        return page(request, "auth.html", mode="register", error="An account with that email already exists.", form_data=dict(form))
    user = User(
        first_name=first_name, last_name=last_name, email=email, phone=phone,
        password_hash=generate_password_hash(password), marketing_opt_in=form.get("marketing_opt_in") == "on",
    )
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    track_event(db, request, "registration")
    request.session["flash"] = ["success", "Your account is ready. Welcome in."]
    return safe_redirect(request, "storefront")


@app.get("/login", name="login", response_class=HTMLResponse)
def login_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    track_event(db, request, "login_view")
    return page(request, "auth.html", mode="login")


@app.post("/login", name="login_submit", dependencies=[Depends(verify_csrf)], response_class=HTMLResponse)
async def login_submit(request: Request, db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user and check_password_hash(user.password_hash, str(form.get("password", ""))):
        destination = request.query_params.get("next", "")
        if not destination or destination == "/":
            destination = "/admin" if user.is_admin_like else "/"
        elif not destination.startswith("/") or destination.startswith("//"):
            destination = "/"
        request.session.clear()
        request.session["user_id"] = user.id
        return RedirectResponse(destination, status_code=303)
    return page(request, "auth.html", mode="login", error="Email or password was not recognized.", form_data=dict(form))


@app.get("/admin/login", name="admin_login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return page(request, "auth.html", mode="admin")


@app.post("/admin/login", name="admin_login_submit", dependencies=[Depends(verify_csrf)], response_class=HTMLResponse)
async def admin_login_submit(request: Request, db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user and user_is_admin(user) and check_password_hash(user.password_hash, str(form.get("password", ""))):
        request.session.clear()
        request.session["user_id"] = user.id
        return safe_redirect(request, "admin_dashboard")
    return page(request, "auth.html", mode="admin", error="Admin credentials were not recognized.", form_data=dict(form))


@app.get("/account/profile", name="account_profile", response_class=HTMLResponse)
def account_profile(request: Request, user: Annotated[User, Depends(require_user)], db: Annotated[Session, Depends(get_db)]):
    return page(request, "profile.html", user=user, profile_mode="customer")


@app.post("/account/profile", name="account_profile_update", dependencies=[Depends(verify_csrf)])
async def account_profile_update(request: Request, user: Annotated[User, Depends(require_user)], db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    first_name = str(form.get("first_name", user.first_name)).strip()
    last_name = str(form.get("last_name", user.last_name)).strip()
    phone = str(form.get("phone", user.phone)).strip()
    if not first_name or not last_name:
        raise HTTPException(status_code=400, detail="First and last names are required.")
    file = form.get("profile_image")
    if file and getattr(file, "filename", ""):
        image = await read_product_image({"photo": file})
        if image:
            user.profile_image = save_product_image(image)
    user.first_name = first_name
    user.last_name = last_name
    user.phone = phone
    db.commit()
    request.session["flash"] = ["success", "Your profile was updated."]
    return safe_redirect(request, "account_profile")


@app.post("/logout", name="logout", dependencies=[Depends(verify_csrf)])
def logout(request: Request):
    request.session.clear()
    return safe_redirect(request, "storefront")


@app.post("/cart/add/{product_id}", name="add_to_cart", dependencies=[Depends(verify_csrf)])
async def add_to_cart(product_id: int, request: Request, db: Annotated[Session, Depends(get_db)]):
    product = db.get(Product, product_id)
    if not product or not product.is_active or product.stock_quantity < 1:
        raise HTTPException(status_code=404, detail="Product not found")
    form = await request.form()
    selected_size = str(form.get("size_variation", "")).strip()
    selected_color = str(form.get("color_variation", "")).strip()
    colors = [c["name"] for c in product_colors(product)]
    if (colors and selected_color not in colors) or (not colors and selected_color):
        raise HTTPException(status_code=400, detail="Choose an available color.")
    available_sizes = product_sizes(product)
    if available_sizes and selected_size not in available_sizes:
        raise HTTPException(status_code=400, detail="Choose an available size variation.")
    if not available_sizes and selected_size:
        raise HTTPException(status_code=400, detail="This product does not have size variations.")
    cart = request.session.get("cart", {})
    line_key = cart_line_key(product_id, selected_size, selected_color)
    product_quantity = 0
    for existing_key, quantity in cart.items():
        try:
            existing_product_id, _existing_size = cart_product_and_size(existing_key)
        except ValueError:
            continue
        if existing_product_id == product_id:
            product_quantity += int(quantity)
    if product_quantity >= product.stock_quantity:
        request.session["flash"] = ["error", f"Only {product.stock_quantity} {product.name} item(s) are currently in stock."]
        return RedirectResponse("/", status_code=303)
    cart[line_key] = int(cart.get(line_key, 0)) + 1
    request.session["cart"] = cart
    track_event(db, request, "add_to_cart", product.id)
    request.session["flash"] = ["success", f"{product.name} added to your bag."]
    referrer = request.headers.get("referer")
    return RedirectResponse(referrer if referrer and referrer.startswith(str(request.base_url)) else "/", status_code=303)


@app.post("/api/cart/add")
async def api_cart_add(request: Request, db: Annotated[Session, Depends(get_db)]):
    data = await request.json()
    product_name = str(data.get("product", "")).strip()
    color = str(data.get("color", "")).strip()
    size = str(data.get("size", "")).strip()
    try:
        qty = int(data.get("quantity", 1))
    except (ValueError, TypeError):
        qty = 1
    if qty < 1:
        qty = 1

    product = db.query(Product).filter_by(name=product_name, is_active=True).first()
    if not product:
        product = db.query(Product).filter_by(is_active=True).first()

    if product:
        cart = request.session.setdefault("cart", {})
        line_key = cart_line_key(product.id, size, color)
        cart[line_key] = int(cart.get(line_key, 0)) + qty
        request.session["cart"] = cart

    total_count = sum(request.session.get("cart", {}).values())
    return {"success": True, "cart_count": total_count}


@app.post("/api/cart/demo-order")
async def api_cart_demo_order(request: Request, db: Annotated[Session, Depends(get_db)]):
    data = await request.json()
    items = data.get("items", [])
    if not items:
        return {"success": False, "detail": "Empty items"}

    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if not user:
        visitor_email = "visitor@allofus.store"
        user = db.query(User).filter_by(email=visitor_email).first()
        if not user:
            user = User(
                email=visitor_email,
                first_name="Store",
                last_name="Visitor",
                password_hash=hash_password("visitor123"),
                role="customer",
            )
            db.add(user)
            db.flush()

    total_amount = Decimal("0.00")
    order = Order(
        user_id=user.id,
        total_amount=Decimal("0.00"),
        shipping_method="Standard",
        shipping_fee=Decimal("0.00"),
        address_line1="Storefront Visitor",
        city="Storefront",
        postal_code="10001",
        status="Pending",
    )
    db.add(order)
    db.flush()

    for item in items:
        p_name = item.get("product")
        p_price = Decimal(str(item.get("price", 0)))
        p_qty = int(item.get("quantity", 1))
        p_size = str(item.get("size", ""))
        p_color = str(item.get("color", ""))

        prod = db.query(Product).filter_by(name=p_name).first()
        prod_id = prod.id if prod else 1
        unit_price = prod.price if prod else p_price

        order_item = OrderItem(
            order_id=order.id,
            product_id=prod_id,
            quantity=p_qty,
            unit_price=unit_price,
            size_variation=p_size,
            color_variation=p_color,
        )
        db.add(order_item)
        total_amount += unit_price * p_qty

    order.total_amount = total_amount
    request.session["cart"] = {}

    log_entry = ActivityLog(
        action="order_placed",
        user_id=user.id,
        entity_type="order",
        entity_id=order.id,
        details=f"Visitor order #{order.id} placed for Rs {total_amount:.2f}",
    )
    db.add(log_entry)
    db.commit()

    return {"success": True, "order_id": order.id, "total": float(total_amount)}


@app.get("/cart", name="cart_view", response_class=HTMLResponse)
def cart_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    track_event(db, request, "cart_view")
    lines = []
    total = Decimal("0.00")
    for line_key, amount in request.session.get("cart", {}).items():
        try:
            product_id, size = cart_product_and_size(line_key)
        except ValueError:
            continue
        product = db.get(Product, product_id)
        if product and product.is_active:
            quantity = min(int(amount), product.stock_quantity)
            subtotal = product.price * quantity
            lines.append({
                "product": product, "quantity": quantity, "subtotal": subtotal,
                "size_variation": size, "cart_key": line_key,
                "color_variation": cart_color(line_key),
                "photo_path": next((c["photo_path"] for c in product_colors(product) if c["name"] == cart_color(line_key)), "") or product.photo_path,
            })
            total += subtotal
    return page(request, "cart.html", lines=lines, total=total)


@app.post("/cart", name="cart_update", dependencies=[Depends(verify_csrf)])
async def update_cart(request: Request, db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    updated = {}
    product_quantities = {}
    for line_key, quantity in request.session.get("cart", {}).items():
        try:
            product_id, _size = cart_product_and_size(line_key)
        except ValueError:
            continue
        try:
            amount = int(form.get(f"quantity_{line_key}", quantity))
        except (TypeError, ValueError):
            amount = 0
        product = db.get(Product, product_id)
        if product and product.is_active and amount > 0:
            remaining = product.stock_quantity - product_quantities.get(product_id, 0)
            if remaining > 0:
                updated[line_key] = min(amount, remaining)
                product_quantities[product_id] = product_quantities.get(product_id, 0) + updated[line_key]
    request.session["cart"] = updated
    request.session["flash"] = ["success", "Your bag has been updated."]
    return safe_redirect(request, "cart_view")


@app.post("/checkout", name="checkout", dependencies=[Depends(verify_csrf)])
def checkout(request: Request, user: Annotated[User, Depends(require_user)], db: Annotated[Session, Depends(get_db)]):
    cart = request.session.get("cart", {})
    if not cart:
        request.session["flash"] = ["error", "Your bag is empty."]
        return safe_redirect(request, "cart_view")
    validated = []
    product_quantities = {}
    total = Decimal("0.00")
    for line_key, amount in cart.items():
        try:
            product_id, size = cart_product_and_size(line_key)
        except ValueError:
            request.session["flash"] = ["error", "Your bag contains an invalid item. Please review your bag."]
            return safe_redirect(request, "cart_view")
        product = db.get(Product, product_id)
        quantity = int(amount)
        if not product or not product.is_active:
            request.session["flash"] = ["error", "Inventory changed while you were shopping. Please review your bag."]
            return safe_redirect(request, "cart_view")
        product_quantities[product_id] = product_quantities.get(product_id, 0) + quantity
        if product.stock_quantity < product_quantities[product_id]:
            request.session["flash"] = ["error", "Inventory changed while you were shopping. Please review your bag."]
            return safe_redirect(request, "cart_view")
        if (product_sizes(product) and size not in product_sizes(product)) or (size and not product_sizes(product)):
            request.session["flash"] = ["error", "A selected product size is no longer available."]
            return safe_redirect(request, "cart_view")
        color = cart_color(line_key)
        colors = [c["name"] for c in product_colors(product)]
        if (colors and color not in colors) or (not colors and color):
            request.session["flash"] = ["error", "A selected product color is no longer available."]
            return safe_redirect(request, "cart_view")
        validated.append((product, quantity, size, color))
        total += product.price * quantity
    order = Order(user_id=user.id, total_amount=total, status="Pending")
    db.add(order)
    for product, quantity, size, color in validated:
        order.items.append(OrderItem(
            product=product, quantity=quantity,
            size_variation=size, price_at_purchase=product.price,
            color_variation=color,
        ))
        product.stock_quantity -= quantity
    db.flush()
    create_activity_log(
        db,
        actor=user,
        module="orders",
        action="order_placed",
        entity_type="order",
        entity_id=order.id,
        details=f"New order #{order.id:04d} placed by visitor {user.first_name} {user.last_name} ({user.email}) for Rs {total:.2f}.",
    )
    db.commit()
    track_event(db, request, "purchase")
    request.session.pop("cart", None)
    request.session["flash"] = ["success", "Order placed. Thanks for gathering with us."]
    return safe_redirect(request, "order_history")


@app.get("/account/orders", name="order_history", response_class=HTMLResponse)
def order_history_page(request: Request, user: Annotated[User, Depends(require_user)], db: Annotated[Session, Depends(get_db)]):
    if user.is_admin_like:
        return safe_redirect(request, "admin_orders")
    orders = db.query(Order).filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    return page(request, "orders.html", orders=orders)


@app.post("/account/orders/{order_id}/requests", name="create_order_request", dependencies=[Depends(verify_csrf)])
async def create_order_request(
    order_id: int,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
):
    order = db.query(Order).filter_by(id=order_id, user_id=user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    form = await request.form()
    kind = str(form.get("kind", ""))
    notes = str(form.get("notes", "")).strip()
    if kind not in {"Shipment", "Exchange"} or len(notes) > 500:
        raise HTTPException(status_code=400, detail="Choose a valid request type and keep notes under 500 characters.")
    db.add(OrderServiceRequest(order_id=order.id, kind=kind, notes=notes))
    db.commit()
    request.session["flash"] = ["success", f"{kind} request submitted for order #{order.id}."]
    return safe_redirect(request, "order_history")


@app.get("/admin/activities", name="admin_activities", response_class=HTMLResponse)
def admin_activities(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    logs = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(100).all()
    return page(request, "admin_activities.html", activity_logs=logs)


@app.get("/admin", name="admin_dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    all_customers = db.query(User).filter_by(role="customer").all()
    revenue = db.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(Order.status != "Cancelled").scalar()
    order_status_counts = {
        status: db.query(Order).filter_by(status=status).count()
        for status in ("Pending", "Processing", "Completed", "Cancelled")
    }
    low_stock_count = db.query(Product).filter(Product.stock_quantity <= 5).count()
    return page(
        request, "admin_home.html", customer_count=len(all_customers),
        product_count=db.query(Product).count(), order_count=db.query(Order).count(),
        revenue=revenue, order_status_counts=order_status_counts,
        low_stock_count=low_stock_count,
    )


@app.get("/admin/content", name="admin_content", response_class=HTMLResponse)
def admin_content(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    pages = db.query(PageContent).order_by(PageContent.id).all()
    pages_by_key = {p.page_key: p for p in pages}
    messages = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(50).all()
    unread_count = db.query(ContactMessage).filter_by(is_read=False).count()
    active_tab = request.query_params.get("tab", "shop").strip().lower()
    if active_tab not in {"shop", "about", "contact", "home", "messages"}:
        active_tab = "shop"
    products = db.query(Product).order_by(Product.display_order.asc(), Product.id.asc()).all()
    return page(
        request, "admin_content.html",
        pages=pages,
        pages_by_key=pages_by_key,
        products=products,
        messages=messages,
        unread_count=unread_count,
        active_tab=active_tab,
        active_module="content",
        module_label="Content Studio",
    )


@app.get("/admin/content/{page_key}", name="admin_content_edit", response_class=HTMLResponse)
def admin_content_edit(
    page_key: str,
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    if page_key not in PAGE_DEFAULTS:
        raise HTTPException(status_code=404, detail="Page not found")
    content = db.query(PageContent).filter_by(page_key=page_key).first()
    if not content:
        raise HTTPException(status_code=404, detail="Page content not found")
    return page(request, "admin_content_edit.html", content=content)


@app.post("/admin/content/{page_key}", name="admin_content_update", dependencies=[Depends(verify_csrf)])
async def admin_content_update(
    page_key: str,
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    if page_key not in PAGE_DEFAULTS:
        raise HTTPException(status_code=404, detail="Page not found")
    content = db.query(PageContent).filter_by(page_key=page_key).first()
    if not content:
        raise HTTPException(status_code=404, detail="Page content not found")
    form = await request.form()
    fields = {
        "hero_eyebrow": (100, False),
        "hero_heading": (240, True),
        "hero_intro": (2000, False),
        "hero_cta_label": (80, False),
        "hero_cta_url": (200, False),
        "site_announcement": (240, False),
        "hero_video_caption": (120, False),
        "footer_tagline": (240, False),
        "section_eyebrow": (100, False),
        "section_heading": (240, False),
        "body": (10000, False),
        "closing_heading": (240, False),
        "closing_copy": (2000, False),
        "meta_description": (320, False),
    }
    values = {name: str(form.get(name, "")).strip() for name in fields}
    for name, (maximum, required) in fields.items():
        if len(values[name]) > maximum or (required and not values[name]):
            request.session["flash"] = ["error", f"Check the {name.replace('_', ' ')} field; required fields must be filled and stay within their character limits."]
            return RedirectResponse(f"/admin/content/{page_key}", status_code=303)
    cta_url = values["hero_cta_url"]
    if cta_url and not (cta_url.startswith("/") or cta_url.startswith("#")):
        request.session["flash"] = ["error", "Use a site path or page anchor for the button link."]
        return RedirectResponse(f"/admin/content/{page_key}", status_code=303)
    if cta_url.startswith("//") or "\\" in cta_url:
        request.session["flash"] = ["error", "The button link must stay within this website."]
        return RedirectResponse(f"/admin/content/{page_key}", status_code=303)
    for name, value in values.items():
        setattr(content, name, value)
    content.published = page_key == "home" or form.get("published") == "on"
    hero_image = form.get("hero_image")
    if hero_image and hasattr(hero_image, "filename") and hero_image.filename:
        try:
            valid_image = validate_product_image(hero_image)
            if valid_image:
                content.hero_image_path = save_product_image(valid_image)
        except ValueError as exc:
            request.session["flash"] = ["error", str(exc)]
            return RedirectResponse(f"/admin/content?tab={page_key}&edit=1", status_code=303)
    db.commit()
    request.session["flash"] = ["success", f"{page_key.title()} page content saved successfully."]
    return RedirectResponse(f"/admin/content?tab={page_key}&edit=1", status_code=303)


@app.post("/admin/content/products/{product_id}/move", name="admin_content_product_move", dependencies=[Depends(verify_csrf)])
async def admin_content_product_move(
    product_id: int,
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    form = await request.form()
    direction = str(form.get("direction", "")).lower()
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    all_prods = db.query(Product).order_by(Product.display_order.asc(), Product.id.asc()).all()
    for idx, p in enumerate(all_prods, start=1):
        p.display_order = idx

    current_idx = next((i for i, p in enumerate(all_prods) if p.id == product_id), None)
    if current_idx is not None:
        if direction == "up" and current_idx > 0:
            target = all_prods[current_idx - 1]
            all_prods[current_idx].display_order, target.display_order = target.display_order, all_prods[current_idx].display_order
            db.commit()
            request.session["flash"] = ["success", f"Moved '{product.name}' up in the shop orbit."]
        elif direction == "down" and current_idx < len(all_prods) - 1:
            target = all_prods[current_idx + 1]
            all_prods[current_idx].display_order, target.display_order = target.display_order, all_prods[current_idx].display_order
            db.commit()
            request.session["flash"] = ["success", f"Moved '{product.name}' down in the shop orbit."]
    return RedirectResponse("/admin/content?tab=shop&edit=1", status_code=303)


@app.post("/admin/content/products/{product_id}/toggle", name="admin_content_product_toggle", dependencies=[Depends(verify_csrf)])
async def admin_content_product_toggle(
    product_id: int,
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = not product.is_active
    db.commit()
    status_str = "active in" if product.is_active else "hidden from"
    request.session["flash"] = ["success", f"'{product.name}' is now {status_str} the shop orbit."]
    return RedirectResponse("/admin/content?tab=shop&edit=1", status_code=303)


@app.post("/admin/content/products/{product_id}/update", name="admin_content_product_update", dependencies=[Depends(verify_csrf)])
async def admin_content_product_update(
    product_id: int,
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    form = await request.form()
    try:
        product_values = parse_product_fields(form)
        image = validate_product_image(form.get("photo"))
    except ValueError as exc:
        request.session["flash"] = ["error", str(exc)]
        return RedirectResponse("/admin/content?tab=shop&edit=1", status_code=303)

    if image:
        product_values["photo_path"] = save_product_image(image)

    product_values["is_active"] = form.get("is_active") == "on"
    for field, value in product_values.items():
        setattr(product, field, value)
    db.commit()
    request.session["flash"] = ["success", f"'{product.name}' details updated."]
    return RedirectResponse("/admin/content?tab=shop&edit=1", status_code=303)


@app.post("/admin/content/products/create", name="admin_content_product_create", dependencies=[Depends(verify_csrf)])
async def admin_content_product_create(
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    form = await request.form()
    try:
        product_values = parse_product_fields(form)
        image = validate_product_image(form.get("photo"))
    except ValueError as exc:
        request.session["flash"] = ["error", str(exc)]
        return RedirectResponse("/admin/content?tab=shop", status_code=303)

    if image:
        product_values["photo_path"] = save_product_image(image)
    else:
        product_values["photo_path"] = "images/henley-grey.png"

    product_values["is_active"] = True
    max_order = db.query(func.coalesce(func.max(Product.display_order), 0)).scalar()
    product_values["display_order"] = (max_order or 0) + 1

    new_prod = Product(**product_values)
    db.add(new_prod)
    db.commit()
    request.session["flash"] = ["success", f"'{new_prod.name}' added directly to the Shop orbit!"]
    return RedirectResponse("/admin/content?tab=shop", status_code=303)


@app.post("/admin/contact-messages/{message_id}", name="update_contact_message", dependencies=[Depends(verify_csrf)])
async def update_contact_message(
    message_id: int,
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    message = db.get(ContactMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Contact message not found")
    form = await request.form()
    status = str(form.get("status", ""))
    if status not in {"read", "unread"}:
        raise HTTPException(status_code=400, detail="Invalid contact message status")
    message.is_read = status == "read"
    db.commit()
    request.session["flash"] = ["success", "Contact message updated."]
    return RedirectResponse("/admin/content", status_code=303)


@app.get("/admin/accounts", name="admin_accounts", response_class=HTMLResponse)
def admin_accounts(request: Request, db: Annotated[Session, Depends(get_db)]):
    user = get_current_user(request, db)
    if not user or not user_is_admin(user):
        return RedirectResponse("/admin/login", status_code=303)

    accounts = db.query(Account).order_by(Account.code).all()
    entries = db.query(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(30).all()
    balances = {account.id: get_account_balance(db, account.id) for account in accounts}
    total_assets = sum((balances.get(account.id, Decimal("0.00")) for account in accounts if account.type == "ASSET"), Decimal("0.00"))
    total_liabilities = sum((balances.get(account.id, Decimal("0.00")) for account in accounts if account.type == "LIABILITY"), Decimal("0.00"))
    total_equity = sum((balances.get(account.id, Decimal("0.00")) for account in accounts if account.type == "EQUITY"), Decimal("0.00"))
    return page(
        request,
        "admin_accounts.html",
        accounts=accounts,
        balances=balances,
        entries=entries,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity,
        active_module="accounts",
    )


@app.post("/admin/accounts/journal", name="create_journal_entry")
async def create_journal_entry(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    user = get_current_user(request, db)
    if not user or not user_is_admin(user):
        return RedirectResponse("/admin/login", status_code=303)

    form = await request.form()
    date_text = str(form.get("date", "")).strip() or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        posting_date = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        posting_date = datetime.utcnow()

    reference_type = str(form.get("reference_type", "ORDER")).strip().upper() or "ORDER"
    reference_id = form.get("reference_id")
    description = str(form.get("description", "")).strip()[:500]
    lines = []
    keys = sorted({key.rsplit("_", 1)[1] for key in form.keys() if key.startswith("account_id_")}, key=lambda value: int(value))
    for key in keys:
        account_id = form.get(f"account_id_{key}")
        if not account_id:
            continue
        debit = Decimal(str(form.get(f"debit_{key}", "0") or "0"))
        credit = Decimal(str(form.get(f"credit_{key}", "0") or "0"))
        if debit == Decimal("0.00") and credit == Decimal("0.00"):
            continue
        lines.append({
            "account_id": int(account_id),
            "debit": debit,
            "credit": credit,
        })

    try:
        entry = post_journal_entry(
            db,
            date=posting_date,
            reference_type=reference_type,
            reference_id=int(reference_id) if reference_id not in (None, "") else None,
            description=description,
            lines=lines,
        )
        create_activity_log(
            db,
            actor=user,
            module="accounts",
            action="posted",
            entity_type="journal_entry",
            entity_id=entry.id,
            details=f"Posted {reference_type} journal entry #{entry.id}.",
        )
        db.commit()
        request.session["flash"] = ["success", "Journal entry posted successfully."]
    except ValueError as exc:
        request.session["flash"] = ["error", str(exc)]
    return RedirectResponse("/admin/accounts", status_code=303)


@app.get("/admin/reports", name="admin_reports", response_class=HTMLResponse)
def admin_reports(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    period = request.query_params.get("period", "30")
    if period not in {"7", "30", "90", "all"}:
        period = "30"
    since = datetime.utcnow() - timedelta(days=int(period)) if period != "all" else None

    orders_query = filter_agent_orders(db.query(Order), request)
    if since:
        orders_query = orders_query.filter(Order.created_at >= since)
    period_orders = orders_query.all()
    sales_orders = [order for order in period_orders if order.status != "Cancelled"]
    revenue = sum((order.total_amount for order in sales_orders), Decimal("0.00"))
    order_status_counts = {
        status: sum(order.status == status for order in period_orders)
        for status in ("Pending", "Processing", "Completed", "Cancelled")
    }

    item_query = filter_agent_orders(db.query(OrderItem).join(Order).filter(Order.status != "Cancelled"), request)
    if since:
        item_query = item_query.filter(Order.created_at >= since)
    product_totals = {}
    daily_totals = {}
    for item in item_query.all():
        product = product_totals.setdefault(
            item.product_id,
            {"name": item.product.name, "units": 0, "revenue": Decimal("0.00")},
        )
        product["units"] += item.quantity
        product["revenue"] += item.price_at_purchase * item.quantity
    for order in sales_orders:
        day = order.created_at.strftime("%Y-%m-%d")
        daily_totals[day] = daily_totals.get(day, Decimal("0.00")) + order.total_amount
    product_sales = sorted(
        product_totals.values(),
        key=lambda item: (item["units"], item["revenue"]),
        reverse=True,
    )

    events_query = db.query(AnalyticsEvent)
    if since:
        events_query = events_query.filter(AnalyticsEvent.created_at >= since)
    events = events_query.all()
    page_views = sum(event.event_type == "page_view" for event in events)
    cart_adds = sum(event.event_type == "add_to_cart" for event in events)
    purchases = sum(event.event_type == "purchase" for event in events)
    visitors = len({event.session_id for event in events})

    customers = db.query(User).filter_by(role="customer").all()
    product_count = db.query(Product).count()
    inventory_units = db.query(func.coalesce(func.sum(Product.stock_quantity), 0)).scalar()
    low_stock_count = db.query(Product).filter(Product.stock_quantity <= 5).count()
    open_request_count = db.query(OrderServiceRequest).filter(
        OrderServiceRequest.status == "Requested"
    ).count()
    best_seller = product_sales[0] if product_sales else None

    return page(
        request,
        "admin_reports.html",
        period=period,
        revenue=revenue,
        order_count=len(period_orders),
        sales_order_count=len(sales_orders),
        average_order=revenue / len(sales_orders) if sales_orders else Decimal("0.00"),
        order_status_counts=order_status_counts,
        product_sales=product_sales,
        best_seller=best_seller,
        daily_sales=[
            {"day": day, "amount": amount}
            for day, amount in sorted(daily_totals.items())
        ],
        customers=len(customers),
        opt_in_customers=sum(customer.marketing_opt_in for customer in customers),
        inventory_products=product_count,
        inventory_units=inventory_units,
        low_stock_count=low_stock_count,
        open_request_count=open_request_count,
        page_views=page_views,
        cart_adds=cart_adds,
        purchases=purchases,
        visitors=visitors,
        conversion=round(purchases * 100 / visitors, 1) if visitors else 0,
        max_daily=max(daily_totals.values(), default=Decimal("0.00")),
        agent_commission=sum((item.commission_amount for order in sales_orders if order.status == "Completed" for item in order.items), Decimal("0.00")),
    )


@app.get("/admin/crm", name="admin_crm", response_class=HTMLResponse)
def admin_crm(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    customers = filtered_customers(db, request)
    if request.query_params.get("agent_id"):
        customer_ids = {row[0] for row in filter_agent_orders(db.query(Order.user_id), request).all()}
        customers = [customer for customer in customers if customer.id in customer_ids]
    all_customers = db.query(User).filter_by(role="customer").all()
    opt_in_count = sum(customer.marketing_opt_in for customer in all_customers)
    customer_spends = [sum((order.total_amount for order in customer.orders), Decimal("0.00")) for customer in all_customers]
    band_counts = [sum(spend == 0 for spend in customer_spends), sum(0 < spend < 50 for spend in customer_spends),
                   sum(50 <= spend < 200 for spend in customer_spends), sum(spend >= 200 for spend in customer_spends)]
    band_labels = ["No spend", "Under Rs 50", "Rs 50–Rs 199", "Rs 200+"]
    clv_distribution = [
        {"label": label, "count": count, "percent": round(count * 100 / len(all_customers)) if all_customers else 0}
        for label, count in zip(band_labels, band_counts)
    ]
    revenue = db.query(func.coalesce(func.sum(Order.total_amount), 0)).scalar()
    customer_rows = [
        {"customer": customer, "order_count": len(customer.orders),
         "spend": sum((order.total_amount for order in customer.orders), Decimal("0.00")),
         "agent_names": ", ".join(sorted({order.agent.name for order in customer.orders if order.agent}))}
        for customer in customers
    ]
    return page(
        request, "admin_crm.html", customer_rows=customer_rows,
        customer_count=len(all_customers), opt_in_count=opt_in_count,
        clv_distribution=clv_distribution,
        opt_in_percent=round(opt_in_count * 100 / len(all_customers)) if all_customers else 0,
        revenue=revenue,
        average_value=Decimal(str(revenue)) / len(all_customers) if all_customers else Decimal("0.00"),
        filters=request.query_params,
    )


@app.get("/admin/inventory", name="admin_inventory", response_class=HTMLResponse)
def admin_inventory(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    products = db.query(Product).order_by(Product.id.desc()).all()
    ordered_product_ids = {row[0] for row in db.query(OrderItem.product_id).distinct().all()}
    ordered_product_ids.update(row[0] for row in db.query(AgentAllocation.product_id).distinct().all())
    return page(request, "admin_inventory.html", products=products, ordered_product_ids=ordered_product_ids)


@app.get("/admin/rbac", name="admin_rbac", response_class=HTMLResponse)
def admin_rbac(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return page(
        request,
        "admin_rbac.html",
        users=users,
        role_labels=ROLE_LABELS,
        role_permissions=RBAC_ROLE_PERMISSIONS,
    )


@app.get("/admin/users", name="admin_users", response_class=HTMLResponse)
def admin_users(request: Request, _admin: Annotated[User, Depends(require_admin)]):
    return RedirectResponse("/admin/rbac", status_code=303)


@app.post("/admin/users", name="create_user_account", dependencies=[Depends(verify_csrf)])
async def create_user_account(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    first_name = str(form.get("first_name", "")).strip()
    last_name = str(form.get("last_name", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    phone = str(form.get("phone", "")).strip()
    password = str(form.get("password", ""))
    role = normalize_role(form.get("role"))
    if not first_name or not last_name or not email or len(password) < 8 or not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Provide a valid first name, last name, email, and a password with at least 8 characters.")
    if not user_can_manage_role(_admin, role):
        raise HTTPException(status_code=403, detail="You do not have permission to create that account type.")
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        password_hash=generate_password_hash(password),
        role=role,
        marketing_opt_in=form.get("marketing_opt_in") == "on",
    )
    db.add(user)
    if role == "agent":
        agent_name = f"{first_name} {last_name}".strip()
        agent = db.query(Agent).filter(func.lower(Agent.email) == email).first()
        if not agent:
            agent = Agent(name=agent_name, phone=phone, email=email)
            db.add(agent)
    db.flush()
    create_activity_log(db, actor=_admin, module="users", action="created", entity_type="user", entity_id=user.id,
                       details=f"Created {ROLE_LABELS.get(role, 'User')} account for {user.email}.")
    db.commit()
    request.session["flash"] = ["success", f"{ROLE_LABELS.get(role, 'User')} account created."]
    return RedirectResponse("/admin/rbac", status_code=303)


@app.get("/admin/agents", name="admin_agents", response_class=HTMLResponse)
def admin_agents(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    agents = db.query(Agent).order_by(Agent.name).all()
    sales = db.query(Order).filter(Order.agent_id.is_not(None), Order.status == "Completed").all()
    rows = []
    for agent in agents:
        orders = [o for o in sales if o.agent_id == agent.id]
        items = [i for o in orders for i in o.items]
        rows.append({"agent": agent, "units": sum(i.quantity for i in items),
                     "revenue": sum((o.total_amount for o in orders), Decimal("0.00")),
                     "commission": sum((i.commission_amount for i in items), Decimal("0.00"))})
    rows.sort(key=lambda row: (row["units"], row["revenue"]), reverse=True)
    return page(request, "admin_agents.html", leaderboard=rows,
                allocations=db.query(AgentAllocation).order_by(AgentAllocation.id.desc()).all(),
                agent_orders=db.query(Order).filter(Order.agent_id.is_not(None)).order_by(Order.id.desc()).all(),
                products=db.query(Product).filter_by(is_active=True).order_by(Product.name).all())


@app.post("/admin/agents", name="create_agent", dependencies=[Depends(verify_csrf)])
async def create_agent(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    name, phone, email = (str(form.get(field, "")).strip() for field in ("name", "phone", "email"))
    if not name or len(name) > 140 or len(phone) > 40 or len(email) > 255:
        raise HTTPException(status_code=400, detail="Enter valid agent contact details.")
    agent = Agent(name=name, phone=phone, email=email)
    db.add(agent)
    db.flush()
    create_activity_log(db, actor=_admin, module="agents", action="created", entity_type="agent", entity_id=agent.id, details=f"Created agent {agent.name}.")
    db.commit()
    request.session["flash"] = ["success", "Agent created separately from customer CRM."]
    return RedirectResponse("/admin/agents", status_code=303)


@app.post("/admin/agents/allocate", name="allocate_agent_stock", dependencies=[Depends(verify_csrf)])
async def allocate_agent_stock(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    try:
        agent = db.get(Agent, int(form.get("agent_id", "0")))
        product = db.query(Product).filter_by(id=int(form.get("product_id", "0"))).with_for_update().first()
        quantity = int(form.get("quantity", "0"))
        discount = percentage(form.get("company_discount_percent", "10"))
        size, color = (str(form.get(field, "")).strip() for field in ("size_variation", "color_variation"))
        if not agent or not agent.is_active or not product or not product.is_active or not 0 < quantity <= product.stock_quantity:
            raise ValueError("Choose an active agent, product and available quantity.")
        sizes, colors = product_sizes(product), [c["name"] for c in product_colors(product)]
        if (sizes and size not in sizes) or (not sizes and size) or (colors and color not in colors) or (not colors and color):
            raise ValueError("Choose an available size and color.")
    except (InvalidOperation, ValueError) as error:
        request.session["flash"] = ["error", str(error)]
        return RedirectResponse("/admin/agents", status_code=303)
    allocation = AgentAllocation(agent_id=agent.id, product_id=product.id, quantity=quantity, remaining=quantity,
                                size_variation=size, color_variation=color, list_price=product.price,
                                company_discount_percent=discount, unit_cost=money(product.price * (1 - discount / 100)))
    db.add(allocation)
    product.stock_quantity -= quantity
    create_activity_log(db, actor=_admin, module="agents", action="allocated", entity_type="allocation", entity_id=allocation.id,
                       details=f"Allocated {quantity} {product.name} units to {agent.name}.")
    db.commit()
    request.session["flash"] = ["success", "Stock issued to agent. Record its eventual selling price in Sales."]
    return RedirectResponse("/admin/agents", status_code=303)


@app.get("/admin/inventory/new", name="admin_product_new", response_class=HTMLResponse)
def admin_product_new(request: Request, _admin: Annotated[User, Depends(require_admin)]):
    return page(request, "admin_product_form.html", form_data={"is_active": "on"})


@app.get("/admin/search", name="admin_search", response_class=HTMLResponse)
def admin_search(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    module = request.query_params.get("module", "overview")
    if module != "all" and module not in ADMIN_MODULES:
        module = "overview"
    query = request.query_params.get("q", "").strip()[:200]
    results = []

    def add_result(title, detail, endpoint, *, anchor="", item_module="", **params):
        if query.casefold() not in f"{title} {detail}".casefold():
            return
        route = request.app.url_path_for(endpoint, **params)
        mod_key = item_module or (module if module in ADMIN_MODULES else "overview")
        mod_label = ADMIN_MODULES.get(mod_key, (mod_key.title(), ""))[0]
        results.append({
            "title": title,
            "detail": detail,
            "url": f"{route}{anchor}",
            "module": mod_key,
            "module_label": mod_label,
        })

    if query:
        # Results link back to their management module, never to a public customer view.
        if module in {"all", "overview"}:
            descriptions = {
                "overview": "Business summary, customers, revenue, orders, low stock",
                "content": "Website pages, publishing, contact messages",
                "crm": "Customers, email, phone, marketing preferences, purchase history",
                "users": "User account creation, access control, roles, and RBAC permissions",
                "inventory": "Products, categories, prices, sizes, stock, add, edit, delete",
                "agents": "Agent leaderboard, allocations, acquisition costs, sales, commission",
                "sales": "Revenue, daily sales, best sellers, units sold",
                "orders": "Order status, fulfillment, shipment and exchange requests",
                "accounts": "Chart of accounts, journals, general ledger, balance sheet and cash movements",
                "analytics": "Website visitors, page views, cart activity, conversion, SEO",
                "activities": "Operational staff actions, agent assignments, content updates, approvals",
                "reports": "Business reports, stock health, product performance",
            }
            for key, (label, endpoint) in ADMIN_MODULES.items():
                add_result(label, descriptions[key], endpoint, item_module="overview")

        if module in {"all", "agents"}:
            for agent in db.query(Agent).all():
                add_result(agent.name, f"{agent.email} {agent.phone}", "admin_agents", item_module="agents", anchor=f"#agent-{agent.id}")

        if module in {"all", "content"}:
            for item in db.query(PageContent).all():
                add_result(f"{item.page_key.title()} page", f"{item.hero_heading} {item.hero_intro} {item.body} {item.meta_description}",
                           "admin_content_edit", item_module="content", page_key=item.page_key)
            for item in db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).all():
                add_result(item.subject, f"{item.name} · {item.email} · {item.message}", "admin_content", item_module="content", anchor="#contact-inbox")

        if module in {"all", "crm"}:
            for item in db.query(User).filter_by(role="customer").all():
                add_result(f"{item.first_name} {item.last_name}", f"{item.email} · {item.phone}", "admin_crm", item_module="crm", anchor=f"#customer-{item.id}")

        if module in {"all", "inventory", "sales", "reports"}:
            products_query = db.query(Product)
            if module in {"sales", "reports"}:
                products_query = products_query.join(OrderItem).join(Order).filter(Order.status != "Cancelled").distinct()
            for item in products_query.order_by(Product.id.desc()).all():
                detail = f"#{item.id} · {item.category} · {item.shop_category} · Rs {item.price:.2f} · {item.stock_quantity} units · {item.size_variations} · {item.description}"
                endpoint = "admin_inventory" if module in {"all", "inventory"} else ADMIN_MODULES[module][1]
                anchor = f"#product-{item.id}" if module in {"all", "inventory"} else ""
                res_mod = "inventory" if module == "all" else module
                add_result(item.name, detail, endpoint, anchor=anchor, item_module=res_mod)

        if module in {"all", "orders"}:
            for item in db.query(Order).order_by(Order.created_at.desc()).all():
                names = ", ".join(line.product.name for line in item.items)
                detail = f"{item.status} · {item.user.first_name} {item.user.last_name} · {item.user.email} · Rs {item.total_amount:.2f} · {names}"
                add_result(f"Order #{item.id}", detail, "admin_orders", anchor=f"#order-{item.id}", item_module="orders")
            for item in db.query(OrderServiceRequest).all():
                add_result(f"{item.kind} request · Order #{item.order_id}", f"{item.status} · {item.notes} · {item.admin_note}", "admin_orders", item_module="orders")

        if module in {"all", "accounts"}:
            for account in db.query(Account).order_by(Account.code).all():
                add_result(account.name, f"{account.code} · {account.type} · {account.normal_balance}", "admin_accounts", item_module="accounts")
            for entry in db.query(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(25).all():
                add_result(f"Journal {entry.reference_type} #{entry.reference_id or 'N/A'}", f"{entry.description or 'General ledger entry'} · {entry.date:%Y-%m-%d}", "admin_accounts", item_module="accounts")

        if module in {"all", "analytics", "reports"}:
            sections = {
                "analytics": ["Page views and unique visitors", "Cart additions and purchases", "Conversion rate", "Website health & SEO", "Daily visits", "Most added products"],
                "reports": ["Net sales and customers", "Order status and pipeline", "Stock health and inventory", "Best sellers and product performance", "Daily net sales", "Storefront activity"],
            }
            sec_keys = ["analytics", "reports"] if module == "all" else [module]
            for sec_key in sec_keys:
                if sec_key in sections:
                    for title in sections[sec_key]:
                        add_result(title, f"Open {ADMIN_MODULES[sec_key][0]}", ADMIN_MODULES[sec_key][1], item_module=sec_key)

        if module in {"all", "analytics"}:
            since = datetime.utcnow() - timedelta(days=30)
            for item in db.query(AnalyticsEvent).filter(AnalyticsEvent.created_at >= since).order_by(AnalyticsEvent.created_at.desc()).all():
                product = db.get(Product, item.product_id) if item.product_id else None
                add_result(item.event_type.replace("_", " ").title(), f"{item.page_path} · {product.name if product else ''} · {item.created_at:%Y-%m-%d}", "admin_analytics", item_module="analytics")

    module_label = "All modules" if module == "all" else ADMIN_MODULES.get(module, ("Overview", ""))[0]
    module_endpoint = "admin_dashboard" if module == "all" else ADMIN_MODULES.get(module, ("", "admin_dashboard"))[1]

    return page(request, "admin_search.html", query=query, results=results, active_module=module,
                module_label=module_label, module_endpoint=module_endpoint, admin_modules=ADMIN_MODULES)


@app.get("/admin/sales", name="admin_sales", response_class=HTMLResponse)
def admin_sales(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    period = request.query_params.get("period", "30")
    if period not in {"today", "7", "30", "90", "all"}:
        period = "30"
    
    now = datetime.utcnow()
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7":
        since = now - timedelta(days=7)
    elif period == "30":
        since = now - timedelta(days=30)
    elif period == "90":
        since = now - timedelta(days=90)
    else:
        since = None

    orders_query = filter_agent_orders(db.query(Order).filter(Order.status != "Cancelled"), request)
    if since:
        orders_query = orders_query.filter(Order.created_at >= since)
    orders = orders_query.order_by(Order.created_at.desc()).all()

    items_query = filter_agent_orders(db.query(OrderItem).join(Order).filter(Order.status != "Cancelled"), request)
    if since:
        items_query = items_query.filter(Order.created_at >= since)
    order_items = items_query.all()

    # Product and Variant performance breakdown
    product_sales = {}
    variant_sales = {}
    total_units_sold = 0
    total_cogs = Decimal("0.00")
    gross_revenue = Decimal("0.00")

    for item in order_items:
        qty = item.quantity
        line_rev = item.price_at_purchase * qty
        prod = item.product
        
        # Product unit manufacturing vendor cost (COGS)
        # If product COGS is set use it, otherwise benchmark at 38% of product standard price for direct manufacturing
        unit_cogs = prod.cogs if (getattr(prod, "cogs", None) and prod.cogs > 0) else (prod.price * Decimal("0.38"))
        line_cogs = unit_cogs * qty
        
        total_units_sold += qty
        gross_revenue += line_rev
        total_cogs += line_cogs

        # Product-level aggregation
        row = product_sales.setdefault(item.product_id, {
            "name": prod.name,
            "units": 0,
            "revenue": Decimal("0.00"),
            "cogs": Decimal("0.00"),
        })
        row["units"] += qty
        row["revenue"] += line_rev
        row["cogs"] += line_cogs

        # Variant-level breakdown (e.g. Grey Henley - Size L)
        variant_key = f"{prod.id}::{item.size_variation or 'Standard'}::{item.color_variation}"
        vrow = variant_sales.setdefault(variant_key, {
            "product_id": prod.id,
            "product_name": prod.name,
            "size": f"{item.size_variation or 'Standard'} / {item.color_variation}" if item.color_variation else item.size_variation or "Standard",
            "category": getattr(prod, "shop_category", prod.category),
            "units": 0,
            "gross_revenue": Decimal("0.00"),
            "unit_price": item.price_at_purchase,
            "unit_cogs": unit_cogs,
            "total_cogs": Decimal("0.00"),
            "gross_profit": Decimal("0.00"),
            "margin_pct": Decimal("0.0"),
        })
        vrow["units"] += qty
        vrow["gross_revenue"] += line_rev
        vrow["total_cogs"] += line_cogs
        vrow["gross_profit"] = vrow["gross_revenue"] - vrow["total_cogs"]
        if vrow["gross_revenue"] > 0:
            vrow["margin_pct"] = (vrow["gross_profit"] / vrow["gross_revenue"]) * Decimal("100.0")

    daily_totals = {}
    for order in orders:
        day = order.created_at.strftime("%b %d")
        daily_totals[day] = daily_totals.get(day, Decimal("0.00")) + order.total_amount
    daily_sales = [{"day": day, "amount": amount} for day, amount in sorted(daily_totals.items())]

    # Executive Financial KPIs
    total_order_amount = sum((order.total_amount for order in orders), Decimal("0.00"))
    total_discounts = sum((getattr(order, "discount_amount", Decimal("0.00")) or Decimal("0.00") for order in orders), Decimal("0.00"))
    # Net revenue post-discounts
    net_revenue = total_order_amount
    if gross_revenue < total_order_amount:
        gross_revenue = total_order_amount
    gross_profit = gross_revenue - total_cogs
    gross_margin_pct = (gross_profit / gross_revenue * Decimal("100.0")) if gross_revenue > 0 else Decimal("0.0")
    aov = (net_revenue / len(orders)) if orders else Decimal("0.00")

    best_seller = max(product_sales.values(), key=lambda item: (item["units"], item["revenue"]), default=None)

    # Sales Channels Breakdown (Store vs Online delivery)
    store_orders = [o for o in orders if getattr(o, "channel", "Online delivery") == "In-store"]
    online_orders = [o for o in orders if getattr(o, "channel", "Online delivery") != "In-store"]
    store_revenue = sum((o.total_amount for o in store_orders), Decimal("0.00"))
    online_revenue = sum((o.total_amount for o in online_orders), Decimal("0.00"))

    # Active catalog items & CRM customers for sales entry
    all_products = db.query(Product).order_by(Product.name).all()
    all_customers = db.query(User).filter_by(role="customer").order_by(User.first_name, User.last_name).all()

    sorted_variants = sorted(
        variant_sales.values(),
        key=lambda v: (v["units"], v["gross_revenue"]),
        reverse=True,
    )

    return page(
        request, "admin_sales.html", period=period, orders=orders, revenue=net_revenue,
        gross_revenue=gross_revenue, net_revenue=net_revenue,
        total_units_sold=total_units_sold, total_cogs=total_cogs,
        gross_profit=gross_profit, gross_margin_pct=gross_margin_pct,
        total_discounts=total_discounts,
        order_count=len(orders), average_order=aov,
        variant_sales=sorted_variants,
        product_sales=sorted(
            product_sales.values(),
            key=lambda item: (item["units"], item["revenue"]),
            reverse=True,
        ),
        best_seller=best_seller,
        daily_sales=daily_sales, max_daily=max((row["amount"] for row in daily_sales), default=Decimal("0.00")),
        store_revenue=store_revenue, online_revenue=online_revenue,
        store_orders_count=len(store_orders), online_orders_count=len(online_orders),
        all_products=all_products, all_customers=all_customers,
        allocations=db.query(AgentAllocation).filter(AgentAllocation.remaining > 0).all(),
        agent_commission=sum((item.commission_amount for item in order_items if item.order.status == "Completed"), Decimal("0.00")),
    )


@app.get("/admin/sales/export", name="export_sales")
def export_sales(
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    period = request.query_params.get("period", "all")
    now = datetime.utcnow()
    since = None
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7":
        since = now - timedelta(days=7)
    elif period == "30":
        since = now - timedelta(days=30)
    elif period == "90":
        since = now - timedelta(days=90)

    orders_query = filter_agent_orders(db.query(Order).order_by(Order.created_at.desc()), request)
    if since:
        orders_query = orders_query.filter(Order.created_at >= since)
    orders = orders_query.all()

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "Transaction ID",
        "Order Date (UTC)",
        "Channel",
        "Customer Name",
        "Customer Email",
        "Status",
        "Items Sold",
        "Gross Subtotal (Rs)",
        "Discounts (Rs)",
        "Tax (Rs)",
        "Total Revenue (Rs)",
        "Estimated COGS (Rs)",
        "Gross Profit (Rs)",
        "Carrier",
        "Tracking Number",
        "Vendor Batch ID",
        "Gateway Ref",
        "Agent", "Agent Acquisition Cost (Rs)", "Company Discount (%)", "Agent Commission (%)", "Agent Commission (Rs)",
    ])

    for o in orders:
        cogs = Decimal("0.00")
        item_descs = []
        for it in o.items:
            unit_c = it.product.cogs if (getattr(it.product, "cogs", None) and it.product.cogs > 0) else (it.product.price * Decimal("0.38"))
            cogs += unit_c * it.quantity
            var_label = f" ({it.size_variation} / {it.color_variation})"
            item_descs.append(f"{it.quantity}x {it.product.name}{var_label}")

        cust_name = f"{o.user.first_name} {o.user.last_name}" if o.user else "Direct Customer"
        cust_email = o.user.email if o.user else ""
        discounts = getattr(o, "discount_amount", Decimal("0.00")) or Decimal("0.00")
        tax = getattr(o, "tax_amount", Decimal("0.00")) or Decimal("0.00")
        subtotal = o.total_amount + discounts - tax
        profit = o.total_amount - cogs

        writer.writerow([
            f"#{o.id:04d}",
            o.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            getattr(o, "channel", "Online delivery"),
            cust_name,
            cust_email,
            o.status,
            "; ".join(item_descs) or "N/A",
            f"{subtotal:.2f}",
            f"{discounts:.2f}",
            f"{tax:.2f}",
            f"{o.total_amount:.2f}",
            f"{cogs:.2f}",
            f"{profit:.2f}",
            getattr(o, "carrier", "") or "",
            getattr(o, "tracking_number", "") or "",
            getattr(o, "vendor_batch_id", "") or "",
            getattr(o, "gateway_ref", "") or "",
            o.agent.name if o.agent else "Direct sale",
            f"{sum((i.agent_unit_cost * i.quantity for i in o.items), Decimal('0.00')):.2f}",
            "; ".join(str(i.company_discount_percent) for i in o.items),
            "; ".join(str(i.commission_percent) for i in o.items),
            f"{sum((i.commission_amount for i in o.items), Decimal('0.00')):.2f}",
        ])

    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=all-of-us-sales-ledger-{period}.csv"},
    )


@app.post("/admin/sales/record", name="record_sale", dependencies=[Depends(verify_csrf)])
async def record_sale(
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    form = await request.form()
    channel = str(form.get("channel", "In-store")).strip()
    if channel not in {"In-store", "Online delivery"}:
        channel = "In-store"

    try:
        product_id = int(form.get("product_id", 0))
        quantity = int(form.get("quantity", 1))
    except (TypeError, ValueError):
        request.session["flash"] = ["error", "Select a valid product and enter a valid quantity."]
        return RedirectResponse("/admin/sales", status_code=303)

    if quantity < 1:
        request.session["flash"] = ["error", "Quantity must be at least 1."]
        return RedirectResponse("/admin/sales", status_code=303)

    product = db.get(Product, product_id)
    if not product:
        request.session["flash"] = ["error", "Product not found."]
        return RedirectResponse("/admin/sales", status_code=303)

    allocation = None
    agent = None
    size_variation = str(form.get("size_variation", "")).strip()
    color_variation = str(form.get("color_variation", "")).strip()
    raw_price = form.get("price")
    try:
        unit_price = money(raw_price or product.price)
        if not unit_price.is_finite() or unit_price <= 0:
            raise ValueError("Enter a positive selling price.")
        company_discount = percentage(form.get("company_discount_percent", "10"))
        commission_percent = percentage(form.get("commission_percent", "10"))
        if form.get("agent_id"):
            agent = db.get(Agent, int(form["agent_id"]))
            if not agent or not agent.is_active:
                raise ValueError("Choose an active agent.")
        if form.get("allocation_id"):
            allocation = db.query(AgentAllocation).filter_by(id=int(form["allocation_id"])).with_for_update().first()
            if not allocation or not agent or allocation.agent_id != agent.id or allocation.product_id != product.id:
                raise ValueError("Choose an allocation belonging to this agent and product.")
            if allocation.remaining < quantity:
                raise ValueError("The agent does not hold enough units in this allocation.")
            size_variation, color_variation = allocation.size_variation, allocation.color_variation
            company_discount = allocation.company_discount_percent
            agent_cost = allocation.unit_cost
        else:
            product = db.query(Product).filter_by(id=product.id).with_for_update().first()
            if not product.is_active or quantity > product.stock_quantity:
                raise ValueError("Not enough active inventory for this sale.")
            agent_cost = money(product.price * (1 - company_discount / 100)) if agent else Decimal("0.00")
            sizes = product_sizes(product)
            colors = [c["name"] for c in product_colors(product)]
            if (sizes and size_variation not in sizes) or (not sizes and size_variation):
                raise ValueError("Choose an available size.")
            if (colors and color_variation not in colors) or (not colors and color_variation):
                raise ValueError("Choose an available color.")
    except (InvalidOperation, ValueError):
        request.session["flash"] = ["error", "Check price, percentages, stock, agent allocation, size and color selections."]
        return RedirectResponse("/admin/sales", status_code=303)

    status = str(form.get("status", "Completed")).strip()
    if status not in {"Completed", "Processing", "Pending"}:
        status = "Completed"

    # Customer verification and CRM registration
    customer_type = str(form.get("customer_type", "new")).strip()
    existing_user_id = form.get("existing_user_id")
    customer = None

    if customer_type == "existing" and existing_user_id:
        try:
            customer = db.get(User, int(existing_user_id))
        except (TypeError, ValueError):
            customer = None

    if not customer:
        email = str(form.get("email", "")).strip().lower()
        first_name = str(form.get("first_name", "")).strip()
        last_name = str(form.get("last_name", "")).strip()
        phone = str(form.get("phone", "")).strip()
        marketing_opt_in = form.get("marketing_opt_in") == "on"

        if email:
            customer = db.query(User).filter(func.lower(User.email) == email).first()

        if customer:
            # Verified existing customer in CRM: update contact info if provided
            if phone and not customer.phone:
                customer.phone = phone
            if first_name and not customer.first_name:
                customer.first_name = first_name
            if last_name and not customer.last_name:
                customer.last_name = last_name
        else:
            # New customer to be permanently stored in CRM!
            if not email:
                email = f"walkin.{secrets.token_hex(4)}@store.allofus"
            customer = User(
                first_name=first_name or "Store",
                last_name=last_name or "Guest",
                email=email,
                phone=phone,
                marketing_opt_in=marketing_opt_in,
                role="customer",
                password_hash=generate_password_hash(secrets.token_hex(16)),
            )
            db.add(customer)
            db.flush()

    total_amount = unit_price * quantity
    order = Order(
        user_id=customer.id,
        total_amount=total_amount,
        status=status,
        channel=channel,
        agent_id=agent.id if agent else None,
    )
    db.add(order)
    db.flush()

    order_item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=quantity,
        size_variation=size_variation,
        price_at_purchase=unit_price,
        color_variation=color_variation,
        allocation_id=allocation.id if allocation else None,
        agent_unit_cost=agent_cost,
        company_discount_percent=company_discount if agent else Decimal("0.00"),
        commission_percent=commission_percent if agent else Decimal("0.00"),
        commission_amount=money(total_amount * commission_percent / 100) if agent else Decimal("0.00"),
    )
    db.add(order_item)

    # Deduct product stock
    if allocation:
        allocation.remaining -= quantity
    else:
        product.stock_quantity -= quantity

    # Track purchase event
    track_event(db, request, "purchase", product_id=product.id)

    db.commit()

    request.session["flash"] = [
        "success",
        f"Sale recorded: {quantity}x {product.name} (Rs {total_amount:.2f}) via {channel}. Customer {customer.first_name} {customer.last_name} ({customer.email}) saved to CRM.",
    ]
    return RedirectResponse(f"/admin/sales#order-{order.id}", status_code=303)


@app.get("/admin/orders", name="admin_orders", response_class=HTMLResponse)
def admin_orders(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    query = filter_agent_orders(db.query(Order).order_by(Order.created_at.desc()), request)
    status = request.query_params.get("status", "")
    if status in {"Pending", "Processing", "Completed", "Cancelled"}:
        query = query.filter_by(status=status)
    service_requests = db.query(OrderServiceRequest).order_by(OrderServiceRequest.created_at.desc()).all()
    return page(
        request, "admin_orders.html", orders=query.all(),
        service_requests=service_requests, selected_status=status,
    )


@app.post("/admin/order-requests/{request_id}", name="update_order_request", dependencies=[Depends(verify_csrf)])
async def update_order_request(
    request_id: int,
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    service_request = db.get(OrderServiceRequest, request_id)
    if not service_request:
        raise HTTPException(status_code=404, detail="Order request not found")
    form = await request.form()
    status = str(form.get("status", ""))
    admin_note = str(form.get("admin_note", "")).strip()
    if status not in {"Requested", "Approved", "Declined", "Completed"} or len(admin_note) > 500:
        raise HTTPException(status_code=400, detail="Choose a valid request status and keep the admin note under 500 characters.")
    service_request.status = status
    service_request.admin_note = admin_note
    db.commit()
    request.session["flash"] = ["success", f"Order request #{service_request.id} updated."]
    return RedirectResponse("/admin/orders", status_code=303)


@app.get("/admin/analytics", name="admin_analytics", response_class=HTMLResponse)
def admin_analytics(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    since = datetime.utcnow() - timedelta(days=30)
    events = db.query(AnalyticsEvent).filter(AnalyticsEvent.created_at >= since).all()
    views = sum(event.event_type == "page_view" for event in events)
    cart_adds = sum(event.event_type == "add_to_cart" for event in events)
    purchases = sum(event.event_type == "purchase" for event in events)
    visitors = len({event.session_id for event in events})
    daily_views = {}
    product_adds = {}
    for event in events:
        if event.event_type == "page_view":
            day = event.created_at.strftime("%b %d")
            daily_views[day] = daily_views.get(day, 0) + 1
        if event.event_type == "add_to_cart" and event.product_id:
            product = db.get(Product, event.product_id)
            if product:
                product_adds[product.name] = product_adds.get(product.name, 0) + 1
    template_root = Path(__file__).resolve().parent / "templates"
    base_template = (template_root / "base.html").read_text(encoding="utf-8")
    store_template = (template_root / "store.html").read_text(encoding="utf-8")
    seo_checks = [
        {
            "label": "Page title",
            "ok": bool(re.search(r"<title>[^<]+", base_template)) and "{% block title %}" in base_template,
            "detail": "The shared layout defines a page title and a page-specific title block.",
        },
        {
            "label": "Meta description",
            "ok": bool(re.search(r'<meta name="description" content="[^"]+"', base_template)),
            "detail": "The shared layout provides a default description and the storefront overrides it.",
        },
        {
            "label": "Mobile viewport",
            "ok": bool(re.search(r'<meta name="viewport"[^>]+width=device-width', base_template)),
            "detail": "The shared layout declares a responsive viewport.",
        },
        {
            "label": "Primary storefront heading",
            "ok": bool(re.search(r"<h1\b", store_template)),
            "detail": "The storefront template includes a primary page heading.",
        },
    ]
    return page(
        request, "admin_analytics.html", page_views=views, visitors=visitors,
        cart_adds=cart_adds, purchases=purchases,
        conversion=round(purchases * 100 / visitors, 1) if visitors else 0,
        daily_views=[{"day": day, "count": count} for day, count in sorted(daily_views.items())],
        max_views=max(daily_views.values(), default=0),
        top_products=sorted(product_adds.items(), key=lambda item: item[1], reverse=True),
        seo_checks=seo_checks,
        seo_score=round(sum(check["ok"] for check in seo_checks) * 100 / len(seo_checks)),
    )


@app.post("/admin/products", name="create_product", dependencies=[Depends(verify_csrf)])
async def create_product(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    form = await request.form()
    try:
        product_values = parse_product_fields(form)
        image = await read_product_image(form)
        product_values["color_variations"] = await read_product_colors(form)
    except (InvalidOperation, ValueError) as error:
        form_data = {key: str(form.get(key, "")) for key in (
            "name", "category", "shop_category", "price", "stock_quantity", "size_variations", "description", "is_active"
        )}
        return page(request, "admin_product_form.html", form_data=form_data,
                    error=str(error) or "Enter valid product details.")
    if image:
        product_values["photo_path"] = save_product_image(image)
    product = Product(**product_values)
    db.add(product)
    db.commit()
    if product_values["is_active"]:
        request.session["flash"] = ["success", "Product added to inventory and published to Shop. Use View in shop to see its product page."]
    else:
        request.session["flash"] = ["success", "Product added to inventory as hidden. Activate it to publish in Shop."]
    return RedirectResponse(f"/admin/inventory#product-{product.id}", status_code=303)


@app.post("/admin/products/{product_id}", name="update_product", dependencies=[Depends(verify_csrf)])
async def update_product(product_id: int, request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    form = await request.form()
    try:
        product_values = parse_product_fields(form)
        image = await read_product_image(form)
        if "colors_present" in form:
            product_values["color_variations"] = await read_product_colors(form, product)
    except (InvalidOperation, ValueError) as error:
        request.session["flash"] = ["error", str(error) or "Enter valid product details."]
        return RedirectResponse("/admin/inventory", status_code=303)
    if image:
        product_values["photo_path"] = save_product_image(image)
    elif form.get("remove_photo") == "on":
        product_values["photo_path"] = ""
    for field, value in product_values.items():
        setattr(product, field, value)
    db.commit()
    request.session["flash"] = ["success", "Product updated."]
    return RedirectResponse(f"/admin/inventory#product-{product.id}", status_code=303)


@app.post("/admin/products/{product_id}/delete", name="delete_product", dependencies=[Depends(verify_csrf)])
async def delete_product(product_id: int, request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if db.query(OrderItem).filter_by(product_id=product_id).first() or db.query(AgentAllocation).filter_by(product_id=product_id).first():
        request.session["flash"] = ["error", "This product belongs to past orders and cannot be deleted. Uncheck Active in shop and save to hide it instead."]
        return RedirectResponse(f"/admin/inventory#product-{product_id}", status_code=303)
    # Keep aggregate event history without leaving dangling product references.
    db.query(AnalyticsEvent).filter_by(product_id=product_id).update({"product_id": None})
    db.delete(product)
    db.commit()
    cart = request.session.get("cart", {})
    request.session["cart"] = {key: quantity for key, quantity in cart.items() if key.split(":", 1)[0] != str(product_id)}
    request.session["flash"] = ["success", "Product deleted from inventory and Shop."]
    return RedirectResponse("/admin/inventory", status_code=303)


@app.post("/admin/orders/{order_id}", name="update_order", dependencies=[Depends(verify_csrf)])
async def update_order(order_id: int, request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    form = await request.form()
    status = str(form.get("status", ""))
    if status not in {"Pending", "Processing", "Completed", "Cancelled"}:
        raise HTTPException(status_code=400, detail="Invalid order status")
    order.status = status
    db.commit()
    request.session["flash"] = ["success", f"Order #{order.id} updated."]
    return RedirectResponse("/admin/orders", status_code=303)


@app.post("/admin/orders/{order_id}/fulfillment", name="update_order_fulfillment", dependencies=[Depends(verify_csrf)])
async def update_order_fulfillment(
    order_id: int,
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    form = await request.form()
    status = str(form.get("status", "")).strip()
    if status and status in {"Pending", "Processing", "Completed", "Cancelled"}:
        order.status = status

    carrier = str(form.get("carrier", "")).strip()[:100]
    tracking_number = str(form.get("tracking_number", "")).strip()[:120]
    vendor_batch_id = str(form.get("vendor_batch_id", "")).strip()[:100]
    shipping_address = str(form.get("shipping_address", "")).strip()[:300]
    promo_code = str(form.get("promo_code", "")).strip()[:50]
    gateway_ref = str(form.get("gateway_ref", "")).strip()[:100]

    order.carrier = carrier
    order.tracking_number = tracking_number
    order.vendor_batch_id = vendor_batch_id
    if shipping_address:
        order.shipping_address = shipping_address
    if promo_code:
        order.promo_code = promo_code
    if gateway_ref:
        order.gateway_ref = gateway_ref

    raw_tax = form.get("tax_amount")
    if raw_tax:
        try:
            order.tax_amount = Decimal(str(raw_tax))
        except (InvalidOperation, ValueError):
            pass

    raw_discount = form.get("discount_amount")
    if raw_discount:
        try:
            order.discount_amount = Decimal(str(raw_discount))
        except (InvalidOperation, ValueError):
            pass

    db.commit()
    request.session["flash"] = [
        "success",
        f"Fulfillment & vendor production batch details saved for Order #{order.id:04d}."
    ]
    return RedirectResponse(f"/admin/orders#order-{order.id}", status_code=303)


@app.get("/admin/crm/export", name="export_customers")
def export_customers(request: Request, _admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["First name", "Last name", "Email", "Phone", "Marketing opt-in", "Orders", "Total spend", "Registered"])
    for customer in filtered_customers(db, request, default_opt_in="yes"):
        spend = sum((order.total_amount for order in customer.orders), Decimal("0.00"))
        writer.writerow([customer.first_name, customer.last_name, customer.email, customer.phone,
                         "yes" if customer.marketing_opt_in else "no", len(customer.orders),
                         f"{spend:.2f}", customer.created_at.isoformat()])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=all-of-us-customers.csv"})


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, error: HTTPException):
    if error.status_code == 403:
        response = page(request, "error.html", code=403, message="This area is reserved for the team.")
        response.status_code = 403
        return response
    if error.status_code == 401:
        return RedirectResponse(f"/login?next={quote(request.url.path)}", status_code=303)
    return HTMLResponse(str(error.detail), status_code=error.status_code)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), reload=False)