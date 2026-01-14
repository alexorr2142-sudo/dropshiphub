# schemas.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


# -----------------------------
# Core schema objects
# -----------------------------
@dataclass(frozen=True)
class TableSchema:
    """Defines canonical columns for a table."""
    name: str
    required: List[str]
    optional: List[str]

    @property
    def all_columns(self) -> List[str]:
        return self.required + self.optional


# -----------------------------
# Canonical tables
# -----------------------------
ORDERS = TableSchema(
    name="orders",
    required=[
        "account_id",
        "store_id",
        "platform",
        "order_id",
        "order_datetime_utc",
        "sku",
        "quantity_ordered",
        "customer_country",
        "promised_ship_days",
    ],
    optional=[
        "customer_state",
        "order_revenue",
        "currency",
        "shipping_method",
    ],
)

SHIPMENTS = TableSchema(
    name="shipments",
    required=[
        "account_id",
        "store_id",
        "supplier_name",
        "supplier_order_id",
        "sku",
        "quantity_shipped",
        "ship_datetime_utc",
    ],
    optional=[
        "order_id",  # some suppliers include Shopify order id; some don't
        "carrier",
        "tracking_number",
        "ship_from_country",
        "ship_to_country",
    ],
)

TRACKING = TableSchema(
    name="tracking",
    required=[
        "account_id",
        "store_id",
        "tracking_number",
    ],
    optional=[
        "carrier",
        "order_id",
        "supplier_order_id",
        "tracking_status_raw",
        "tracking_status_normalized",
        "last_update_utc",
        "delivery_date_utc",
        "delivery_exception",
    ],
)

# This is the line-level “truth table” after reconciliation
LINE_STATUS = TableSchema(
    name="line_status",
    required=[
        "account_id",
        "store_id",
        "platform",
        "order_id",
        "order_datetime_utc",
        "sku",
        "quantity_ordered",
        "quantity_shipped",
        "line_status",  # UNSHIPPED / PARTIALLY_SHIPPED / SHIPPED / DELIVERED
        "is_late",
        "days_since_order",
        "promised_ship_days",
    ],
    optional=[
        "customer_country",
        "customer_state",
        "supplier_name",
        "supplier_order_id",
        "carrier",
        "tracking_number",
        "tracking_missing",
        "tracking_status",
    ],
)

# Exceptions is what you show first in the UI
EXCEPTIONS = TableSchema(
    name="exceptions",
    required=[
        "order_id",
        "sku",
        "issue_type",  # e.g., LATE_UNSHIPPED, MISSING_TRACKING...
    ],
    optional=[
        "account_id",
        "store_id",
        "platform",
        "order_datetime_utc",
        "customer_country",
        "supplier_name",
        "supplier_order_id",
        "carrier",
        "tracking_number",
        "quantity_ordered",
        "quantity_shipped",
        "line_status",
        "days_since_order",
        "promised_ship_days",
        # explain.py adds these:
        "explanation",
        "next_action",
        "customer_risk",
        "llm_used",
        "llm_confidence",
    ],
)

# Supplier follow-ups is the grouped output (one row per supplier)
FOLLOWUPS = TableSchema(
    name="followups",
    required=[
        "supplier_name",
        "body",  # email-ready message
    ],
    optional=[
        "supplier_email",
        "urgency",
        "item_count",
        "order_ids",
        "subject",
    ],
)

# Order rollup is the one-row-per-order view
ORDER_ROLLUP = TableSchema(
    name="order_rollup",
    required=[
        "order_id",
        "internal_status",
        "customer_facing_status",
        "top_issue",
        "risk_score",
        "risk_band",
    ],
    optional=[
        "account_id",
        "store_id",
        "platform",
        "order_datetime_utc",
        "customer_country",
        "customer_state",
        "supplier_blocking",
        "recommended_action",
        "action_owner",
        "top_carrier",
        "top_tracking_number",
        "total_lines",
        "total_qty_ordered",
        "total_qty_shipped",
        "eta_next_update_utc",
        "at_fault_party",
    ],
)


# -----------------------------
# Enums / controlled values
# -----------------------------
LINE_STATUS_VALUES = ["UNSHIPPED", "PARTIALLY_SHIPPED", "SHIPPED", "DELIVERED"]

ISSUE_TYPES = [
    "LATE_UNSHIPPED",
    "MISSING_TRACKING",
    "PARTIAL_SHIPMENT",
    "CARRIER_EXCEPTION",
    "UNSHIPPED",
    "OVER_SHIPPED",
]

RISK_BANDS = ["Low", "Medium", "High"]


# -----------------------------
# Simple validation helpers
# -----------------------------
def missing_required_columns(columns: List[str], schema: TableSchema) -> List[str]:
    colset = set(columns)
    return [c for c in schema.required if c not in colset]


def schema_summary() -> Dict[str, Dict[str, List[str]]]:
    """
    Convenience function if you want to show schema info in the UI or logs.
    """
    tables = [ORDERS, SHIPMENTS, TRACKING, LINE_STATUS, EXCEPTIONS, FOLLOWUPS, ORDER_ROLLUP]
    return {t.name: {"required": t.required, "optional": t.optional} for t in tables}
