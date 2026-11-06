import io
import csv
import json
import logging
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# In-memory undo action store (expires after 120s)
_UNDO_STORE: Dict[str, Dict[str, Any]] = {}

DEFAULT_SMART_SEGMENTS = [
    {
        "name": "High Value (LTV Rs 200+)",
        "color": "#8b5cf6",  # Violet
        "match_type": "all",
        "rules": {"min_spend": 200},
        "is_pinned": True,
        "daily_digest": True,
        "digest_time": "09:00 NPT",
    },
    {
        "name": "Store Agent Clients",
        "color": "#059669",  # Emerald
        "match_type": "all",
        "rules": {"channel": ["Store Agent Portal"]},
        "is_pinned": True,
        "daily_digest": False,
        "digest_time": "09:00 NPT",
    },
    {
        "name": "Marketing Consented",
        "color": "#2563eb",  # Royal Blue
        "match_type": "all",
        "rules": {"marketing_consent": ["subscribed"]},
        "is_pinned": True,
        "daily_digest": True,
        "digest_time": "09:00 NPT",
    },
    {
        "name": "Recent Sign-ups (30D)",
        "color": "#0891b2",  # Cyan
        "match_type": "all",
        "rules": {"max_days_joined": 30},
        "is_pinned": True,
        "daily_digest": False,
        "digest_time": "09:00 NPT",
    },
    {
        "name": "At-Risk / No Orders",
        "color": "#d97706",  # Amber
        "match_type": "all",
        "rules": {"max_orders": 0, "min_days_joined": 14},
        "is_pinned": False,
        "daily_digest": False,
        "digest_time": "09:00 NPT",
    },
]


def compute_customer_rank(spend: Decimal) -> str:
    if spend >= Decimal("500.00"):
        return "VIP Platinum"
    elif spend >= Decimal("200.00"):
        return "VIP Gold"
    elif spend >= Decimal("50.00"):
        return "Silver"
    return "Standard"


def customer_matches_segment(
    customer: Any,
    rules: Dict[str, Any],
    match_type: str = "all",
    customer_orders: Optional[List[Any]] = None,
    customer_spend: Optional[Decimal] = None,
) -> bool:
    if not rules:
        return True

    orders = customer.orders if customer_orders is None else customer_orders
    spend = sum((o.total_amount for o in orders if getattr(o, "status", "") != "Cancelled"), Decimal("0.00")) if customer_spend is None else customer_spend
    order_count = len([o for o in orders if getattr(o, "status", "") != "Cancelled"])
    days_joined = (datetime.utcnow() - customer.created_at).days if customer.created_at else 0
    m_status = getattr(customer, "resolved_marketing_status", "subscribed" if customer.marketing_opt_in else "not_opted_in")

    checks: List[bool] = []

    # Channel check
    if "channel" in rules and rules["channel"]:
        allowed = rules["channel"]
        if isinstance(allowed, str):
            allowed = [allowed]
        checks.append(customer.acquisition_channel in allowed)

    # Acquisition type check
    if "acquisition_type" in rules and rules["acquisition_type"]:
        allowed = rules["acquisition_type"]
        if isinstance(allowed, str):
            allowed = [allowed]
        checks.append(customer.acquisition_type in allowed)

    # Marketing consent check
    if "marketing_consent" in rules and rules["marketing_consent"]:
        allowed = rules["marketing_consent"]
        if isinstance(allowed, str):
            allowed = [allowed]
        if "any" not in allowed:
            checks.append(m_status in allowed)

    # Assigned Agent check
    if "agent_id" in rules and rules["agent_id"] not in (None, "", "any"):
        agent_val = str(rules["agent_id"])
        if agent_val == "direct":
            checks.append(not any(o.agent_id for o in orders))
        else:
            try:
                aid = int(agent_val)
                checks.append(any(o.agent_id == aid for o in orders))
            except ValueError:
                pass

    # Spend checks
    if "min_spend" in rules and rules["min_spend"] not in (None, ""):
        try:
            checks.append(spend >= Decimal(str(rules["min_spend"])))
        except Exception:
            pass
    if "max_spend" in rules and rules["max_spend"] not in (None, ""):
        try:
            checks.append(spend <= Decimal(str(rules["max_spend"])))
        except Exception:
            pass

    # Order count checks
    if "min_orders" in rules and rules["min_orders"] not in (None, ""):
        try:
            checks.append(order_count >= int(rules["min_orders"]))
        except Exception:
            pass
    if "max_orders" in rules and rules["max_orders"] not in (None, ""):
        try:
            checks.append(order_count <= int(rules["max_orders"]))
        except Exception:
            pass

    # Days joined checks
    if "min_days_joined" in rules and rules["min_days_joined"] not in (None, ""):
        try:
            checks.append(days_joined >= int(rules["min_days_joined"]))
        except Exception:
            pass
    if "max_days_joined" in rules and rules["max_days_joined"] not in (None, ""):
        try:
            checks.append(days_joined <= int(rules["max_days_joined"]))
        except Exception:
            pass

    # Tag check
    if "tag" in rules and rules["tag"]:
        req_tag = str(rules["tag"]).strip().lower()
        checks.append(any(t.lower() == req_tag for t in customer.tag_list))

    if not checks:
        return True

    if match_type == "any":
        return any(checks)
    return all(checks)


def calculate_crm_analytics(
    db: Session,
    window: str = "30D",
    start_date_str: str = "",
    end_date_str: str = "",
) -> Dict[str, Any]:
    from main import User, Order, SmartSegment

    now = datetime.utcnow()
    window = (window or "30D").upper()

    # Determine date boundaries
    if window == "7D":
        start_date = now - timedelta(days=7)
        prev_start = now - timedelta(days=14)
        prev_end = start_date
    elif window == "30D":
        start_date = now - timedelta(days=30)
        prev_start = now - timedelta(days=60)
        prev_end = start_date
    elif window == "YTD":
        start_date = datetime(now.year, 1, 1)
        days_in_ytd = (now - start_date).days or 1
        prev_end = start_date
        prev_start = prev_end - timedelta(days=days_in_ytd)
    elif window == "CUSTOM" and start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else now
            delta = end_date - start_date
            prev_end = start_date
            prev_start = prev_end - delta
        except Exception:
            start_date = now - timedelta(days=30)
            prev_start = now - timedelta(days=60)
            prev_end = start_date
    else:  # 'ALL'
        start_date = datetime(2020, 1, 1)
        prev_start = datetime(2020, 1, 1)
        prev_end = datetime(2020, 1, 1)

    all_customers = db.query(User).filter_by(role="customer").all()
    total_customers_count = len(all_customers)

    # Net additions in current window
    net_additions = sum(1 for c in all_customers if c.created_at and c.created_at >= start_date)

    # Prior 30 days customer additions for MoM growth calculation
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)
    current_month_additions = sum(1 for c in all_customers if c.created_at and c.created_at >= thirty_days_ago)
    prior_month_additions = sum(1 for c in all_customers if c.created_at and sixty_days_ago <= c.created_at < thirty_days_ago)
    if prior_month_additions > 0:
        mom_growth_pct = round(((current_month_additions - prior_month_additions) / prior_month_additions) * 100, 1)
    elif current_month_additions > 0:
        mom_growth_pct = 100.0
    else:
        mom_growth_pct = 0.0

    # Marketing consent breakdown
    opt_in_subscribed = 0
    opt_in_not_opted = 0
    opt_in_unsubscribed = 0
    for c in all_customers:
        st = c.resolved_marketing_status
        if st == "subscribed":
            opt_in_subscribed += 1
        elif st == "unsubscribed":
            opt_in_unsubscribed += 1
        else:
            opt_in_not_opted += 1

    # Revenue & Order counts in current period vs previous period
    all_orders = db.query(Order).filter(Order.status != "Cancelled").all()
    window_orders = [o for o in all_orders if o.created_at and o.created_at >= start_date]
    prev_window_orders = [o for o in all_orders if o.created_at and prev_start <= o.created_at < prev_end]

    total_revenue = sum((o.total_amount for o in window_orders), Decimal("0.00"))
    prev_revenue = sum((o.total_amount for o in prev_window_orders), Decimal("0.00"))
    total_order_count = len(window_orders)

    if prev_revenue > 0:
        revenue_comparison_pct = round(float((total_revenue - prev_revenue) / prev_revenue * 100), 1)
    elif total_revenue > 0:
        revenue_comparison_pct = 100.0
    else:
        revenue_comparison_pct = 0.0

    # All-time revenue for LTV calculation
    all_time_revenue = sum((o.total_amount for o in all_orders), Decimal("0.00"))
    average_customer_value = (all_time_revenue / total_customers_count) if total_customers_count > 0 else Decimal("0.00")

    # Spend brackets breakdown (Across all customers)
    customer_spends = {
        c.id: sum((o.total_amount for o in c.orders if o.status != "Cancelled"), Decimal("0.00"))
        for c in all_customers
    }

    bracket_counts = {
        "no_spend": 0,
        "under_50": 0,
        "50_199": 0,
        "200_plus": 0,
    }
    bracket_revenues = {
        "no_spend": Decimal("0.00"),
        "under_50": Decimal("0.00"),
        "50_199": Decimal("0.00"),
        "200_plus": Decimal("0.00"),
    }

    for cid, sp in customer_spends.items():
        if sp == 0:
            bracket_counts["no_spend"] += 1
        elif sp < 50:
            bracket_counts["under_50"] += 1
            bracket_revenues["under_50"] += sp
        elif sp < 200:
            bracket_counts["50_199"] += 1
            bracket_revenues["50_199"] += sp
        else:
            bracket_counts["200_plus"] += 1
            bracket_revenues["200_plus"] += sp

    total_c = total_customers_count or 1
    ltv_brackets = [
        {
            "key": "no_spend",
            "label": "No spend",
            "count": bracket_counts["no_spend"],
            "percent": round(bracket_counts["no_spend"] * 100 / total_c, 1),
            "revenue": float(bracket_revenues["no_spend"]),
        },
        {
            "key": "under_50",
            "label": "<Rs 50",
            "count": bracket_counts["under_50"],
            "percent": round(bracket_counts["under_50"] * 100 / total_c, 1),
            "revenue": float(bracket_revenues["under_50"]),
        },
        {
            "key": "50_199",
            "label": "Rs 50–Rs 199",
            "count": bracket_counts["50_199"],
            "percent": round(bracket_counts["50_199"] * 100 / total_c, 1),
            "revenue": float(bracket_revenues["50_199"]),
        },
        {
            "key": "200_plus",
            "label": "Rs 200+",
            "count": bracket_counts["200_plus"],
            "percent": round(bracket_counts["200_plus"] * 100 / total_c, 1),
            "revenue": float(bracket_revenues["200_plus"]),
        },
    ]

    # Retention Rate: Customers with 2 or more orders / Customers with at least 1 order
    customers_with_orders = sum(1 for cid, sp in customer_spends.items() if sp > 0)
    repeat_customers = sum(1 for c in all_customers if len([o for o in c.orders if o.status != "Cancelled"]) >= 2)
    retention_rate = round((repeat_customers / customers_with_orders * 100), 1) if customers_with_orders > 0 else 0.0

    # Donut 1: Acquisition Type Breakdown
    type_counts: Dict[str, int] = {"New sign-up": 0, "Repeat buyer": 0, "Reactivated": 0}
    for c in all_customers:
        atype = c.acquisition_type or "New sign-up"
        if atype not in type_counts:
            type_counts[atype] = 0
        type_counts[atype] += 1

    type_colors = {
        "New sign-up": "#111111",
        "Repeat buyer": "#4b5563",
        "Reactivated": "#9ca3af",
    }
    donut_acquisition_types = [
        {
            "key": k,
            "label": k,
            "count": count,
            "percent": round(count * 100 / total_c, 1),
            "color": type_colors.get(k, "#64748b"),
        }
        for k, count in type_counts.items()
    ]

    # Donut 2: Acquisition Channels Breakdown
    channel_counts: Dict[str, int] = {"Direct Web": 0, "Guest Checkout": 0, "Store Agent Portal": 0}
    for c in all_customers:
        ch = c.acquisition_channel or "Direct Web"
        if ch not in channel_counts:
            channel_counts[ch] = 0
        channel_counts[ch] += 1

    channel_colors = {
        "Direct Web": "#1e293b",
        "Guest Checkout": "#64748b",
        "Store Agent Portal": "#cbd5e1",
    }
    donut_acquisition_channels = [
        {
            "key": k,
            "label": k,
            "count": count,
            "percent": round(count * 100 / total_c, 1),
            "color": channel_colors.get(k, "#94a3b8"),
        }
        for k, count in channel_counts.items()
    ]

    # Timeline Chart: New Sign-ups vs Repeat Purchases over intervals
    # Generate 7-12 intervals based on window
    num_bins = 7 if window == "7D" else (10 if window == "30D" else 12)
    step_days = max(1, (now - start_date).days // num_bins)
    timeline_points = []

    for i in range(num_bins):
        bin_start = start_date + timedelta(days=i * step_days)
        bin_end = bin_start + timedelta(days=step_days)
        if i == num_bins - 1:
            bin_end = now + timedelta(seconds=1)

        bin_signups = sum(1 for c in all_customers if c.created_at and bin_start <= c.created_at < bin_end)
        bin_repeat = 0
        for o in all_orders:
            if o.created_at and bin_start <= o.created_at < bin_end:
                # Repeat if user has an order before this order
                has_prior = any(prior.id != o.id and prior.created_at < o.created_at for prior in o.user.orders if prior.status != "Cancelled")
                if has_prior:
                    bin_repeat += 1

        label_fmt = "%b %d" if step_days <= 7 else "%b %Y"
        timeline_points.append({
            "date": bin_start.strftime("%Y-%m-%d"),
            "label": bin_start.strftime(label_fmt),
            "new_signups": bin_signups,
            "repeat_purchases": bin_repeat,
        })

    return {
        "window": window,
        "kpi": {
            "total_customers": total_customers_count,
            "mom_growth_pct": mom_growth_pct,
            "net_additions": net_additions,
            "opt_in_breakdown": {
                "subscribed": opt_in_subscribed,
                "not_opted_in": opt_in_not_opted,
                "unsubscribed": opt_in_unsubscribed,
                "subscribed_pct": round(opt_in_subscribed * 100 / total_c, 1),
                "not_opted_in_pct": round(opt_in_not_opted * 100 / total_c, 1),
                "unsubscribed_pct": round(opt_in_unsubscribed * 100 / total_c, 1),
            },
            "total_revenue": float(total_revenue),
            "prev_revenue": float(prev_revenue),
            "revenue_comparison_pct": revenue_comparison_pct,
            "total_orders": total_order_count,
            "average_customer_value": float(average_customer_value),
            "ltv_brackets": ltv_brackets,
            "retention_rate": retention_rate,
        },
        "donuts": {
            "acquisition_types": donut_acquisition_types,
            "acquisition_channels": donut_acquisition_channels,
        },
        "timeline": timeline_points,
    }


def get_customer_detail(db: Session, customer_id: int) -> Optional[Dict[str, Any]]:
    from main import User, Order, SmartSegment, CustomerInteraction, ActivityLog

    customer = db.get(User, customer_id)
    if not customer or customer.role != "customer":
        return None

    orders = [o for o in customer.orders if o.status != "Cancelled"]
    total_spend = sum((o.total_amount for o in orders), Decimal("0.00"))
    order_count = len(orders)
    aov = (total_spend / order_count) if order_count > 0 else Decimal("0.00")
    last_order = max(customer.orders, key=lambda x: x.created_at) if customer.orders else None

    # Agent names
    agent_names = sorted({o.agent.name for o in orders if o.agent})

    # Segment memberships
    all_segments = db.query(SmartSegment).all()
    matching_segments = []
    for seg in all_segments:
        if customer_matches_segment(customer, seg.get_rules(), seg.match_type, customer_orders=orders, customer_spend=total_spend):
            matching_segments.append({
                "id": seg.id,
                "name": seg.name,
                "color": seg.color,
            })

    # 6-Month Spend Progression
    now = datetime.utcnow()
    spend_history = []
    for m in range(5, -1, -1):
        target_month_date = now - timedelta(days=m * 30)
        y = target_month_date.year
        mo = target_month_date.month
        month_label = target_month_date.strftime("%b")
        m_orders = [o for o in orders if o.created_at and o.created_at.year == y and o.created_at.month == mo]
        m_spend = sum((o.total_amount for o in m_orders), Decimal("0.00"))
        spend_history.append({
            "label": month_label,
            "spend": float(m_spend),
            "orders": len(m_orders),
        })

    # Interaction Timeline (Newest First)
    timeline_items = []

    # 1. Direct logged interactions
    for item in db.query(CustomerInteraction).filter_by(customer_id=customer.id).all():
        cat = "notes" if item.type == "note" else ("contact" if item.type in {"call", "email", "store_visit"} else "system")
        timeline_items.append({
            "id": f"interaction-{item.id}",
            "type": item.type,
            "category": cat,
            "title": item.title or item.type.replace("_", " ").title(),
            "content": item.content,
            "author": item.author_name or "Staff",
            "created_at": item.created_at,
        })

    # 2. Orders placed
    for o in customer.orders:
        item_names = ", ".join(line.product.name for line in o.items) if o.items else "Items"
        timeline_items.append({
            "id": f"order-{o.id}",
            "type": "order",
            "category": "orders",
            "title": f"Order #{o.id:04d} ({o.status})",
            "content": f"Total: Rs {o.total_amount:.2f} · Channel: {o.channel} · Items: {item_names}",
            "author": o.customer_name or f"{customer.first_name} {customer.last_name}",
            "created_at": o.created_at,
        })

    # 3. System activity log entries relating to customer
    act_logs = db.query(ActivityLog).filter(
        ((ActivityLog.entity_type == "user") & (ActivityLog.entity_id == customer.id))
        | ActivityLog.details.like(f"%{customer.email}%")
    ).all()
    for act in act_logs:
        timeline_items.append({
            "id": f"system-{act.id}",
            "type": "system",
            "category": "system",
            "title": f"System: {act.action.replace('_', ' ').title()}",
            "content": act.details,
            "author": act.actor_name or "System",
            "created_at": act.created_at,
        })

    # Sort newest first
    timeline_items.sort(key=lambda x: x["created_at"], reverse=True)

    # Group into Day Buckets: Today, Yesterday, or formatted date
    today_date = now.date()
    yesterday_date = today_date - timedelta(days=1)

    grouped_timeline = []
    current_group = None

    for item in timeline_items:
        item_date = item["created_at"].date()
        if item_date == today_date:
            group_label = "Today"
        elif item_date == yesterday_date:
            group_label = "Yesterday"
        else:
            group_label = item["created_at"].strftime("%b %d, %Y")

        if not current_group or current_group["date_label"] != group_label:
            current_group = {
                "date_label": group_label,
                "items": [],
            }
            grouped_timeline.append(current_group)

        current_group["items"].append({
            "id": item["id"],
            "type": item["type"],
            "category": item["category"],
            "title": item["title"],
            "content": item["content"],
            "author": item["author"],
            "time_str": item["created_at"].strftime("%I:%M %p"),
            "full_date": item["created_at"].strftime("%b %d, %Y %I:%M %p"),
        })

    category_counts = {
        "all": len(timeline_items),
        "orders": sum(1 for it in timeline_items if it["category"] == "orders"),
        "notes": sum(1 for it in timeline_items if it["category"] == "notes"),
        "contact": sum(1 for it in timeline_items if it["category"] == "contact"),
        "system": sum(1 for it in timeline_items if it["category"] == "system"),
    }

    return {
        "id": customer.id,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "name": f"{customer.first_name} {customer.last_name}",
        "email": customer.email,
        "phone": customer.phone or "",
        "address": customer.address or "",
        "bio": customer.bio or "",
        "tags": customer.tag_list,
        "acquisition_channel": customer.acquisition_channel,
        "acquisition_type": customer.acquisition_type,
        "marketing_status": customer.resolved_marketing_status,
        "rank": compute_customer_rank(total_spend),
        "created_at_fmt": customer.created_at.strftime("%b %d, %Y") if customer.created_at else "",
        "days_since_joined": (now - customer.created_at).days if customer.created_at else 0,
        "metrics": {
            "ltv": float(total_spend),
            "aov": float(aov),
            "order_count": order_count,
            "last_order_date": last_order.created_at.strftime("%b %d, %Y") if last_order else "No orders yet",
            "agents": ", ".join(agent_names) if agent_names else "Direct sales",
        },
        "spend_history": spend_history,
        "segments": matching_segments,
        "timeline_groups": grouped_timeline,
        "category_counts": category_counts,
    }


def calculate_segment_preview(db: Session, rules: Dict[str, Any], match_type: str = "all") -> Dict[str, Any]:
    from main import User

    all_customers = db.query(User).filter_by(role="customer").all()
    total_customers = len(all_customers)

    matching_customers = []
    total_revenue = Decimal("0.00")
    channel_counts: Dict[str, int] = {"Direct Web": 0, "Guest Checkout": 0, "Store Agent Portal": 0}

    for c in all_customers:
        orders = [o for o in c.orders if o.status != "Cancelled"]
        spend = sum((o.total_amount for o in orders), Decimal("0.00"))
        if customer_matches_segment(c, rules, match_type, customer_orders=orders, customer_spend=spend):
            matching_customers.append((c, spend, len(orders)))
            total_revenue += spend
            ch = c.acquisition_channel or "Direct Web"
            channel_counts[ch] = channel_counts.get(ch, 0) + 1

    matching_count = len(matching_customers)
    share_pct = round(matching_count * 100 / (total_customers or 1), 1)

    # Channel mix percentages
    channel_mix = {
        k: round(count * 100 / (matching_count or 1), 1)
        for k, count in channel_counts.items()
    }

    # Sample top 4 customers
    sample_customers = [
        {
            "id": c.id,
            "name": f"{c.first_name} {c.last_name}",
            "email": c.email,
            "spend": float(spend),
            "orders": o_count,
            "channel": c.acquisition_channel,
            "rank": compute_customer_rank(spend),
        }
        for c, spend, o_count in matching_customers[:4]
    ]

    return {
        "matching_count": matching_count,
        "total_customers": total_customers,
        "share_percentage": share_pct,
        "total_revenue": float(total_revenue),
        "channel_mix": channel_mix,
        "sample_customers": sample_customers,
    }


def compare_segments(db: Session, seg_a_id: str, seg_b_id: str) -> Dict[str, Any]:
    from main import User, SmartSegment

    all_customers = db.query(User).filter_by(role="customer").all()
    total_customers = len(all_customers)

    def resolve_segment(sid: str) -> Tuple[str, str, Dict[str, Any], str]:
        if sid.isdigit():
            seg = db.get(SmartSegment, int(sid))
            if seg:
                return seg.name, seg.color, seg.get_rules(), seg.match_type
        # Preset segment fallbacks
        presets = {
            "preset_high_value": ("High Value (Rs 200+)", "#8b5cf6", {"min_spend": 200}, "all"),
            "preset_agent": ("Store Agent Clients", "#059669", {"channel": ["Store Agent Portal"]}, "all"),
            "preset_subscribers": ("Marketing Consented", "#2563eb", {"marketing_consent": ["subscribed"]}, "all"),
            "preset_recent": ("Recent Sign-ups", "#0891b2", {"max_days_joined": 30}, "all"),
            "preset_direct": ("Direct Web Shoppers", "#1e293b", {"channel": ["Direct Web"]}, "all"),
        }
        if sid in presets:
            return presets[sid]
        # Return first smart segment or default
        first_seg = db.query(SmartSegment).first()
        if first_seg:
            return first_seg.name, first_seg.color, first_seg.get_rules(), first_seg.match_type
        return "All Customers", "#111111", {}, "all"

    name_a, color_a, rules_a, match_a = resolve_segment(seg_a_id)
    name_b, color_b, rules_b, match_b = resolve_segment(seg_b_id)

    # Evaluate matches
    ids_a: Set[int] = set()
    ids_b: Set[int] = set()
    customer_map: Dict[int, Any] = {}
    customer_spends: Dict[int, Decimal] = {}
    customer_orders_count: Dict[int, int] = {}

    for c in all_customers:
        customer_map[c.id] = c
        orders = [o for o in c.orders if o.status != "Cancelled"]
        spend = sum((o.total_amount for o in orders), Decimal("0.00"))
        customer_spends[c.id] = spend
        customer_orders_count[c.id] = len(orders)

        if customer_matches_segment(c, rules_a, match_a, customer_orders=orders, customer_spend=spend):
            ids_a.add(c.id)
        if customer_matches_segment(c, rules_b, match_b, customer_orders=orders, customer_spend=spend):
            ids_b.add(c.id)

    only_a = ids_a - ids_b
    overlap = ids_a & ids_b
    only_b = ids_b - ids_a

    count_a = len(ids_a)
    count_b = len(ids_b)
    count_overlap = len(overlap)

    # Overlap metrics
    shared_revenue = sum((customer_spends[cid] for cid in overlap), Decimal("0.00"))
    min_count = min(count_a, count_b) if count_a > 0 and count_b > 0 else 1
    overlap_pct = round((count_overlap / min_count) * 100, 1) if count_a > 0 and count_b > 0 else 0.0

    high_overlap_warning = overlap_pct >= 30.0
    warning_message = ""
    if high_overlap_warning:
        warning_message = f"⚠️ Heavy Overlap Alert: {overlap_pct}% shared membership detected. Cross-marketing between these two segments risks duplicate messaging and customer fatigue."

    # Compute comparative metrics for A and B
    def get_seg_stats(cids: Set[int]) -> Dict[str, Any]:
        count = len(cids)
        if count == 0:
            return {
                "count": 0, "revenue": 0.0, "ltv": 0.0, "aov": 0.0,
                "orders_per_customer": 0.0, "opt_in_rate": 0.0,
                "repeat_rate": 0.0, "channel_mix": {}, "spend_brackets": {},
            }
        tot_rev = sum((customer_spends[cid] for cid in cids), Decimal("0.00"))
        tot_orders = sum((customer_orders_count[cid] for cid in cids))
        ltv = float(tot_rev / count)
        aov = float(tot_rev / tot_orders) if tot_orders > 0 else 0.0
        orders_per_cust = round(tot_orders / count, 1)

        opt_ins = sum(1 for cid in cids if customer_map[cid].resolved_marketing_status == "subscribed")
        opt_in_rate = round(opt_ins * 100 / count, 1)

        repeats = sum(1 for cid in cids if customer_orders_count[cid] >= 2)
        repeat_rate = round(repeats * 100 / count, 1)

        ch_counts: Dict[str, int] = {}
        for cid in cids:
            ch = customer_map[cid].acquisition_channel or "Direct Web"
            ch_counts[ch] = ch_counts.get(ch, 0) + 1
        channel_mix = {k: round(v * 100 / count, 1) for k, v in ch_counts.items()}

        brk_counts = {"<Rs 50": 0, "Rs 50–Rs 199": 0, "Rs 200+": 0, "No spend": 0}
        for cid in cids:
            sp = customer_spends[cid]
            if sp == 0:
                brk_counts["No spend"] += 1
            elif sp < 50:
                brk_counts["<Rs 50"] += 1
            elif sp < 200:
                brk_counts["Rs 50–Rs 199"] += 1
            else:
                brk_counts["Rs 200+"] += 1
        spend_brackets = {k: round(v * 100 / count, 1) for k, v in brk_counts.items()}

        return {
            "count": count,
            "revenue": float(tot_rev),
            "ltv": ltv,
            "aov": aov,
            "orders_per_customer": orders_per_cust,
            "opt_in_rate": opt_in_rate,
            "repeat_rate": repeat_rate,
            "channel_mix": channel_mix,
            "spend_brackets": spend_brackets,
        }

    stats_a = get_seg_stats(ids_a)
    stats_b = get_seg_stats(ids_b)

    # Combined Intersection rules for "Save overlap as segment"
    intersection_rules = {}
    intersection_rules.update(rules_a)
    for k, v in rules_b.items():
        if k not in intersection_rules:
            intersection_rules[k] = v
        elif isinstance(v, list) and isinstance(intersection_rules[k], list):
            intersection_rules[k] = list(set(intersection_rules[k]) & set(v)) or intersection_rules[k]
        elif k == "min_spend":
            intersection_rules[k] = max(intersection_rules[k], v)
        elif k == "max_spend":
            intersection_rules[k] = min(intersection_rules[k], v)

    return {
        "segment_a": {"name": name_a, "color": color_a, "count": count_a, "rules": rules_a},
        "segment_b": {"name": name_b, "color": color_b, "count": count_b, "rules": rules_b},
        "venn": {
            "only_a_count": len(only_a),
            "overlap_count": count_overlap,
            "only_b_count": len(only_b),
            "shared_revenue": float(shared_revenue),
            "overlap_pct": overlap_pct,
            "high_overlap_warning": high_overlap_warning,
            "warning_message": warning_message,
        },
        "stats_a": stats_a,
        "stats_b": stats_b,
        "intersection_rules": intersection_rules,
    }


def record_undo_action(action_type: str, previous_data: Dict[int, Any]) -> str:
    token = secrets.token_urlsafe(16)
    _UNDO_STORE[token] = {
        "action": action_type,
        "previous_data": previous_data,
        "created_at": datetime.utcnow(),
    }
    return token


def perform_undo_action(db: Session, token: str) -> Tuple[bool, str]:
    from main import User, create_activity_log

    record = _UNDO_STORE.get(token)
    if not record:
        return False, "Undo token has expired or is invalid."

    action = record["action"]
    prev_data = record["previous_data"]

    try:
        if action == "tags":
            for cid, old_tags in prev_data.items():
                u = db.get(User, cid)
                if u:
                    u.tags = old_tags
        elif action == "consent":
            for cid, old_status in prev_data.items():
                u = db.get(User, cid)
                if u:
                    u.marketing_status = old_status
                    u.marketing_opt_in = (old_status == "subscribed")
        db.commit()
        del _UNDO_STORE[token]
        return True, "Action successfully reversed."
    except Exception as exc:
        db.rollback()
        return False, f"Failed to undo: {exc}"


def migrate_crm_schema(engine, Base, SessionLocal, is_production: bool = False):
    from main import User, Order, OrderItem, Product, Agent, SmartSegment, CustomerInteraction

    is_postgres = engine.dialect.name == "postgresql"
    table_columns = {
        "users": {
            "tags": "VARCHAR(255) NOT NULL DEFAULT ''",
            "acquisition_channel": "VARCHAR(50) NOT NULL DEFAULT 'Direct Web'",
            "acquisition_type": "VARCHAR(50) NOT NULL DEFAULT 'New sign-up'",
            "marketing_status": "VARCHAR(30) NOT NULL DEFAULT 'not_opted_in'",
        }
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

    # Ensure all tables are created
    Base.metadata.create_all(engine)

    # Seed Default Smart Segments if empty
    with SessionLocal.begin() as db:
        if db.query(SmartSegment).count() == 0:
            for sdata in DEFAULT_SMART_SEGMENTS:
                db.add(SmartSegment(
                    name=sdata["name"],
                    color=sdata["color"],
                    match_type=sdata["match_type"],
                    rules=json.dumps(sdata["rules"]),
                    is_pinned=sdata["is_pinned"],
                    daily_digest=sdata["daily_digest"],
                    digest_time=sdata["digest_time"],
                ))

        # Backward compatibility for existing customers: sync marketing_status & channels
        for c in db.query(User).filter_by(role="customer").all():
            if not c.marketing_status or c.marketing_status == "not_opted_in":
                if c.marketing_opt_in:
                    c.marketing_status = "subscribed"
            if not c.acquisition_channel or c.acquisition_channel == "Direct Web":
                if any(o.agent_id for o in c.orders):
                    c.acquisition_channel = "Store Agent Portal"
            if not c.acquisition_type or c.acquisition_type == "New sign-up":
                if len(c.orders) >= 2:
                    c.acquisition_type = "Repeat buyer"

        # If 0 customers exist and not in production, seed rich demo data
        if not is_production and db.query(User).filter_by(role="customer").count() == 0:
            seed_crm_demo_data(db)


def seed_crm_demo_data(db: Session):
    from main import User, Order, OrderItem, Product, Agent, CustomerInteraction, generate_password_hash

    logger.info("Seeding rich CRM demo customer dataset...")

    # Ensure at least one agent exists
    agent = db.query(Agent).first()
    if not agent:
        agent = Agent(name="Kiran Shrestha", phone="9841234567", email="kiran.agent@allofus.com")
        db.add(agent)
        db.flush()

    products = db.query(Product).all()
    prod_1 = products[0] if len(products) > 0 else None
    prod_2 = products[1] if len(products) > 1 else prod_1
    prod_3 = products[2] if len(products) > 2 else prod_1

    now = datetime.utcnow()

    demo_customers = [
        {
            "first_name": "Aarav", "last_name": "Sharma", "email": "aarav.sharma@example.com",
            "phone": "+977 9851011223", "address": "Jhamsikhel, Lalitpur",
            "tags": "VIP,High-Spend,Loyal", "channel": "Direct Web", "atype": "Repeat buyer",
            "m_opt": True, "m_status": "subscribed", "days_ago": 120,
            "orders": [
                {"days_ago": 90, "amount": Decimal("180.00"), "agent_id": None, "channel": "Online delivery"},
                {"days_ago": 45, "amount": Decimal("220.00"), "agent_id": None, "channel": "Online delivery"},
                {"days_ago": 10, "amount": Decimal("140.00"), "agent_id": None, "channel": "Online delivery"},
            ],
            "notes": [
                {"type": "note", "title": "Prefers slow drip ceramics", "content": "Aarav visited the studio and bought the Sunday Ceramic Set. Inquired about upcoming winter drops."},
                {"type": "call", "title": "VIP Drop Preview Call", "content": "Called to offer early access to new homeware lineup. Confirmed interest in cashmere throws."},
            ]
        },
        {
            "first_name": "Priya", "last_name": "Adhikari", "email": "priya.adhikari@example.com",
            "phone": "+977 9841987654", "address": "Lazimpat, Kathmandu",
            "tags": "VIP,Wholesale", "channel": "Store Agent Portal", "atype": "Repeat buyer",
            "m_opt": True, "m_status": "subscribed", "days_ago": 95,
            "orders": [
                {"days_ago": 60, "amount": Decimal("160.00"), "agent_id": agent.id, "channel": "In-store"},
                {"days_ago": 15, "amount": Decimal("120.00"), "agent_id": agent.id, "channel": "In-store"},
            ],
            "notes": [
                {"type": "store_visit", "title": "Agent Store Consultation", "content": "Purchased through Kiran at studio counter. Requested delivery directly to her studio."},
            ]
        },
        {
            "first_name": "Rohan", "last_name": "Shrestha", "email": "rohan.shrestha@example.com",
            "phone": "+977 9801122334", "address": "New Road, Pokhara",
            "tags": "Apparel,Casual", "channel": "Direct Web", "atype": "New sign-up",
            "m_opt": True, "m_status": "subscribed", "days_ago": 18,
            "orders": [
                {"days_ago": 14, "amount": Decimal("42.00"), "agent_id": None, "channel": "Online delivery"},
            ],
            "notes": [
                {"type": "email", "title": "Welcome Email Opened", "content": "Opened automated welcome digest and clicked tote collection link."},
            ]
        },
        {
            "first_name": "Binod", "last_name": "Thapa", "email": "binod.thapa@example.com",
            "phone": "+977 9813456789", "address": "Baluwatar, Kathmandu",
            "tags": "Repeat,Home", "channel": "Guest Checkout", "atype": "Repeat buyer",
            "m_opt": False, "m_status": "not_opted_in", "days_ago": 75,
            "orders": [
                {"days_ago": 70, "amount": Decimal("45.00"), "agent_id": None, "channel": "Online delivery"},
                {"days_ago": 25, "amount": Decimal("70.00"), "agent_id": None, "channel": "Online delivery"},
            ],
            "notes": [
                {"type": "note", "title": "Address Verification", "content": "Verified delivery route via Baluwatar police checkpoint."},
            ]
        },
        {
            "first_name": "Anjali", "last_name": "Joshi", "email": "anjali.joshi@example.com",
            "phone": "+977 9860123456", "address": "Sanepa, Lalitpur",
            "tags": "Prospect,Newsletter", "channel": "Direct Web", "atype": "New sign-up",
            "m_opt": True, "m_status": "subscribed", "days_ago": 5,
            "orders": [],
            "notes": [
                {"type": "note", "title": "Newsletter Signup", "content": "Joined via footer signup form. Added to welcome email cadence."},
            ]
        },
        {
            "first_name": "Suman", "last_name": "Maharjan", "email": "suman.m@example.com",
            "phone": "+977 9849887766", "address": "Patan Durbar Square",
            "tags": "VIP,Ceramics", "channel": "Store Agent Portal", "atype": "Repeat buyer",
            "m_opt": True, "m_status": "subscribed", "days_ago": 150,
            "orders": [
                {"days_ago": 110, "amount": Decimal("110.00"), "agent_id": agent.id, "channel": "In-store"},
                {"days_ago": 50, "amount": Decimal("115.00"), "agent_id": agent.id, "channel": "In-store"},
                {"days_ago": 8, "amount": Decimal("85.00"), "agent_id": agent.id, "channel": "In-store"},
            ],
            "notes": [
                {"type": "call", "title": "Custom Glaze Order", "content": "Discussed custom glaze finish for dining set. Awaits sample batch."},
            ]
        },
        {
            "first_name": "Sneha", "last_name": "Karki", "email": "sneha.karki@example.com",
            "phone": "+977 9818776655", "address": "Baneshwor, Kathmandu",
            "tags": "Gifts", "channel": "Guest Checkout", "atype": "New sign-up",
            "m_opt": True, "m_status": "subscribed", "days_ago": 22,
            "orders": [
                {"days_ago": 20, "amount": Decimal("28.00"), "agent_id": None, "channel": "Online delivery"},
            ],
            "notes": [
                {"type": "note", "title": "Gift Wrap Requested", "content": "Requested neutral linen gift wrap and handwritten greeting card."},
            ]
        },
        {
            "first_name": "Bikash", "last_name": "Gurung", "email": "bikash.gurung@example.com",
            "phone": "+977 9856012345", "address": "Lakeside, Pokhara",
            "tags": "Reactivated,Loyal", "channel": "Direct Web", "atype": "Reactivated",
            "m_opt": True, "m_status": "subscribed", "days_ago": 180,
            "orders": [
                {"days_ago": 170, "amount": Decimal("90.00"), "agent_id": None, "channel": "Online delivery"},
                {"days_ago": 6, "amount": Decimal("100.00"), "agent_id": None, "channel": "Online delivery"},
            ],
            "notes": [
                {"type": "note", "title": "Reactivation Campaign Response", "content": "Re-engaged via Autumn Studio Digest and placed order after 5 months of inactivity."},
            ]
        },
        {
            "first_name": "Puja", "last_name": "Tamang", "email": "puja.tamang@example.com",
            "phone": "+977 9843221100", "address": "Boudha, Kathmandu",
            "tags": "Candles,Store", "channel": "Store Agent Portal", "atype": "Reactivated",
            "m_opt": False, "m_status": "unsubscribed", "days_ago": 110,
            "orders": [
                {"days_ago": 95, "amount": Decimal("40.00"), "agent_id": agent.id, "channel": "In-store"},
                {"days_ago": 12, "amount": Decimal("45.00"), "agent_id": agent.id, "channel": "In-store"},
            ],
            "notes": [
                {"type": "system", "title": "Consent Unsubscribed", "content": "Customer opted out of marketing emails via footer preference center."},
            ]
        },
        {
            "first_name": "Dipesh", "last_name": "Giri", "email": "dipesh.giri@example.com",
            "phone": "+977 9802233445", "address": "Thamel, Kathmandu",
            "tags": "Prospect", "channel": "Direct Web", "atype": "New sign-up",
            "m_opt": True, "m_status": "subscribed", "days_ago": 8,
            "orders": [],
            "notes": [
                {"type": "note", "title": "Catalog Download", "content": "Downloaded digital homeware lookbook."},
            ]
        },
        {
            "first_name": "Sunita", "last_name": "Poudel", "email": "sunita.poudel@example.com",
            "phone": "+977 9841009988", "address": "Kupondole, Lalitpur",
            "tags": "VIP,High-Spend", "channel": "Direct Web", "atype": "Repeat buyer",
            "m_opt": True, "m_status": "subscribed", "days_ago": 140,
            "orders": [
                {"days_ago": 130, "amount": Decimal("150.00"), "agent_id": None, "channel": "Online delivery"},
                {"days_ago": 80, "amount": Decimal("180.00"), "agent_id": None, "channel": "Online delivery"},
                {"days_ago": 22, "amount": Decimal("120.00"), "agent_id": None, "channel": "Online delivery"},
            ],
            "notes": [
                {"type": "note", "title": "Corporate Gifting", "content": "Ordered customized tote sets for company retreat."},
            ]
        },
        {
            "first_name": "Manish", "last_name": "Basnet", "email": "manish.basnet@example.com",
            "phone": "+977 9810112233", "address": "Dillibazar, Kathmandu",
            "tags": "Stationery", "channel": "Guest Checkout", "atype": "New sign-up",
            "m_opt": False, "m_status": "not_opted_in", "days_ago": 16,
            "orders": [
                {"days_ago": 15, "amount": Decimal("38.00"), "agent_id": None, "channel": "Online delivery"},
            ],
            "notes": [
                {"type": "note", "title": "Express Courier", "content": "Dispatched via Kathmandu local courier."},
            ]
        },
    ]

    for data in demo_customers:
        created_time = now - timedelta(days=data["days_ago"])
        customer = User(
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            phone=data["phone"],
            address=data["address"],
            password_hash=generate_password_hash("Password123!"),
            role="customer",
            tags=data["tags"],
            acquisition_channel=data["channel"],
            acquisition_type=data["atype"],
            marketing_opt_in=data["m_opt"],
            marketing_status=data["m_status"],
            created_at=created_time,
        )
        db.add(customer)
        db.flush()

        # Add orders
        for o_info in data["orders"]:
            order_time = now - timedelta(days=o_info["days_ago"])
            order = Order(
                user_id=customer.id,
                agent_id=o_info["agent_id"],
                total_amount=o_info["amount"],
                status="Completed",
                channel=o_info["channel"],
                payment_method="eSewa / Digital Wallet",
                payment_status="Paid",
                customer_name=f"{customer.first_name} {customer.last_name}",
                customer_phone=customer.phone,
                shipping_address=customer.address,
                created_at=order_time,
            )
            db.add(order)
            db.flush()

            if prod_1:
                db.add(OrderItem(
                    order_id=order.id,
                    product_id=prod_1.id,
                    quantity=1,
                    price_at_purchase=o_info["amount"],
                    size_variation="M",
                ))

        # Add timeline notes
        for note in data["notes"]:
            db.add(CustomerInteraction(
                customer_id=customer.id,
                type=note["type"],
                title=note["title"],
                content=note["content"],
                author_name="Staff",
                created_at=now - timedelta(days=data["days_ago"] // 2),
            ))

    db.commit()
    logger.info("Successfully seeded demo customers.")
