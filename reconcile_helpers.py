# reconcile.py
from __future__ import annotations

from typing import Dict, Tuple
import pandas as pd
from datetime import datetime, timezone


# -----------------------------
# Helpers
# -----------------------------
def _now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


def _to_dt(series) -> pd.Series:
    try:
        return pd.to_datetime(series, errors="coerce", utc=True)
    except Exception:
        return pd.Series([pd.NaT] * len(series))


def _canonicalize_keys(df: pd.DataFrame, *, df_name: str) -> pd.DataFrame:
    """
    Ensures df has canonical keys: order_id, sku (required by downstream groupby/merge).
    Tries to rename common aliases from uploads/exports.
    Raises a clear error if still missing.
    """
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    # Common aliases across exports
    alias_map = {
        "order_id": ["order_id", "Order ID", "OrderID", "order", "Order", "Order Number", "order_number", "name", "Name"],
        "sku": ["sku", "SKU", "Sku", "Variant SKU", "variant_sku", "line_item_sku", "Lineitem sku", "Line Item SKU"],
        "quantity_ordered": ["quantity_ordered", "Quantity Ordered", "qty_ordered", "qty", "Qty", "Quantity"],
        "quantity_shipped": ["quantity_shipped", "Quantity Shipped", "qty_shipped", "Shipped Quantity", "Quantity"],
        "supplier_name": ["supplier_name", "Supplier", "Supplier Name"],
        "supplier_order_id": ["supplier_order_id", "Supplier Order ID", "SupplierOrderID"],
        "carrier": ["carrier", "Carrier"],
        "tracking_number": ["tracking_number", "Tracking", "Tracking Number", "tracking", "tracking_no", "TrackingNo"],
        "ship_datetime_utc": ["ship_datetime_utc", "Ship Date", "ship_date", "Ship Datetime", "shipped_at", "Shipped At"],
        "customer_country": ["customer_country", "To Country", "Ship To Country", "country", "Country"],
        "order_datetime_utc": ["order_datetime_utc", "Order Date", "order_date", "Created At", "created_at", "Order Created At"],
        "promised_ship_days": ["promised_ship_days", "Promised Ship Days", "sla_days", "SLA Days"],
    }

    rename_map: dict[str, str] = {}

    # Only rename when canonical missing
    for canon, candidates in alias_map.items():
        if canon in df.columns:
            continue
        for c in candidates:
            if c in df.columns:
                rename_map[c] = canon
                break

    if rename_map:
        df = df.rename(columns=rename_map)

    # Hard requirements for reconciliation logic
    required = ["order_id", "sku"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{df_name} missing required columns {missing}. "
            f"Columns present: {list(df.columns)}"
        )

    # Normalize types to keep groupby/merge stable
    df["order_id"] = df["order_id"].astype(str)
    df["sku"] = df["sku"].astype(str)

    return df


# -----------------------------
