# core/demo_schema.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd


@dataclass(frozen=True)
class DemoSchemaReport:
    ok: bool
    level: str  # "ok" | "warn" | "error"
    messages: List[str]


# These are the demo CSV “raw” schemas (pre-normalization).
REQUIRED_ORDERS_COLS = [
    "Name",
    "Created at",
    "Lineitem sku",
    "Lineitem quantity",
    "Shipping country",
    "Total",
    "Currency",
]

OPTIONAL_ORDERS_COLS = [
    "Shipping province",
    "Shipping method",
]

REQUIRED_SHIPMENTS_COLS = [
    "Supplier",
    "Supplier Order ID",
    "Order ID",
    "SKU",
    "Quantity",
    "Ship Date",
    "Carrier",
    "From Country",
    "To Country",
]

OPTIONAL_SHIPMENTS_COLS = [
    "Tracking",
]

REQUIRED_TRACKING_COLS = []  # Tracking is optional for demo


def _missing_cols(df: pd.DataFrame, required: List[str]) -> List[str]:
    cols = set(df.columns.tolist()) if isinstance(df, pd.DataFrame) else set()
    return [c for c in required if c not in cols]


def validate_demo_inputs(
    raw_orders: pd.DataFrame,
    raw_shipments: pd.DataFrame,
    raw_tracking: pd.DataFrame | None = None,
) -> DemoSchemaReport:
    """
    Validates demo CSVs *before* normalization.
    Produces a simple health report suitable for a sidebar badge.
    """
    msgs: List[str] = []

    # Basic empties
    if raw_orders is None or not isinstance(raw_orders, pd.DataFrame) or raw_orders.empty:
        return DemoSchemaReport(
            ok=False,
            level="error",
            messages=["Orders demo CSV is empty or not loaded."],
        )
    if raw_shipments is None or not isinstance(raw_shipments, pd.DataFrame) or raw_shipments.empty:
        return DemoSchemaReport(
            ok=False,
            level="error",
            messages=["Shipments demo CSV is empty or not loaded."],
        )

    # Required columns
    mo = _missing_cols(raw_orders, REQUIRED_ORDERS_COLS)
    ms = _missing_cols(raw_shipments, REQUIRED_SHIPMENTS_COLS)

    if mo:
        msgs.append(f"Orders missing required column(s): {', '.join(mo)}")
    if ms:
        msgs.append(f"Shipments missing required column(s): {', '.join(ms)}")

    # Optional checks that affect feature demos
    # Missing tracking helps trigger exceptions/follow-ups, so it’s fine; but we can warn if *all* tracking missing.
    if isinstance(raw_shipments, pd.DataFrame) and "Tracking" in raw_shipments.columns:
        tracking_series = raw_shipments["Tracking"].fillna("").astype(str).str.strip()
        if tracking_series.eq("").all():
            msgs.append("All shipments have blank Tracking (OK for demo, but tracking-related KPIs may skew).")

    # Quantity sanity
    if "Lineitem quantity" in raw_orders.columns:
        try:
            q = pd.to_numeric(raw_orders["Lineitem quantity"], errors="coerce")
            if q.isna().any():
                msgs.append("Orders has non-numeric Lineitem quantity values.")
        except Exception:
            msgs.append("Orders Lineitem quantity could not be validated as numeric.")

    if "Quantity" in raw_shipments.columns:
        try:
            q = pd.to_numeric(raw_shipments["Quantity"], errors="coerce")
            if q.isna().any():
                msgs.append("Shipments has non-numeric Quantity values.")
        except Exception:
            msgs.append("Shipments Quantity could not be validated as numeric.")

    # Tracking is optional
    if raw_tracking is not None and isinstance(raw_tracking, pd.DataFrame) and not raw_tracking.empty:
        # If you later add a demo tracking CSV schema, enforce it here.
        pass

    if msgs:
        # Missing required cols = error; otherwise warn
        level = "error" if (mo or ms) else "warn"
        return DemoSchemaReport(ok=(level != "error"), level=level, messages=msgs)

    return DemoSchemaReport(ok=True, level="ok", messages=["Demo inputs look good."])
