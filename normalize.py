# normalize.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

import pandas as pd
from dateutil import parser


# -------------------------------
# Helpers
# -------------------------------
def _clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def _lower_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    return out


def _to_utc(series: pd.Series) -> pd.Series:
    """Parse mixed datetime strings -> timezone-aware UTC timestamps."""
    def parse_one(x):
        if pd.isna(x) or str(x).strip() == "":
            return pd.NaT
        try:
            dt = parser.parse(str(x))
            if dt.tzinfo is None:
                # assume already UTC if no tz given
                return pd.Timestamp(dt).tz_localize("UTC")
            return pd.Timestamp(dt).tz_convert("UTC")
        except Exception:
            return pd.NaT

    return series.apply(parse_one)


def _to_int(series: pd.Series, default: int = 0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default).astype(int)


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_str(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").astype("string")


def _validation(errors: List[str]) -> Dict[str, Any]:
    return {"validation_errors": errors}


@dataclass(frozen=True)
class ColumnRule:
    name: str
    required: bool = True


def _require_cols(df: pd.DataFrame, rules: List[ColumnRule], table: str) -> List[str]:
    errs: List[str] = []
    cols = set(df.columns)
    for r in rules:
        if r.required and r.name not in cols:
            errs.append(f"[{table}] Missing required column: {r.name}")
    return errs


# -------------------------------
# Shopify detection + mapping
# -------------------------------
def detect_shopify_orders(raw_df: pd.DataFrame) -> bool:
    df = _lower_cols(_clean_cols(raw_df))
    cols = set(df.columns)

    shopify_signals = {
        "name",
        "created at",
        "lineitem sku",
        "lineitem quantity",
        "variant sku",
        "shipping country",
        "shipping province",
        "financial status",
        "fulfillment status",
    }
    score = len(shopify_signals.intersection(cols))
    return score >= 3


SHOPIFY_COLUMN_MAP = {
    # IDs
    "name": "order_id",
    "order id": "order_id",

    # time
    "created at": "order_datetime_utc",

    # sku options
    "lineitem sku": "sku",
    "variant sku": "sku",
    "lineitem name": "sku",  # fallback if no SKU

    # quantity
    "lineitem quantity": "quantity_ordered",
    "quantity": "quantity_ordered",

    # geo
    "shipping country": "customer_country",
    "shipping province": "customer_state",

    # financials
    "total": "order_revenue",
    "subtotal": "order_revenue",
    "currency": "currency",

    # shipping
    "shipping method": "shipping_method",
    "shipping line title": "shipping_method",
}


# -------------------------------
# Public API
# -------------------------------
def normalize_orders(
    raw_orders: pd.DataFrame,
    account_id: str,
    store_id: str,
    platform_hint: str = "shopify",
    default_currency: str = "USD",
    default_promised_ship_days: int = 3,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Canonical Orders output columns (one row per order line / sku):
      account_id, store_id, platform, order_id, order_datetime_utc,
      sku, quantity_ordered, customer_country, customer_state,
      order_revenue, currency, shipping_method, promised_ship_days

    Returns: (df, meta) where meta['validation_errors'] is a list
    """
    errors: List[str] = []

    if raw_orders is None or raw_orders.empty:
        return pd.DataFrame(), _validation(["[orders] Input orders dataframe is empty."])

    df = _lower_cols(_clean_cols(raw_orders))

    # Detect Shopify & map columns
    is_shopify = detect_shopify_orders(raw_orders) or (platform_hint.lower() == "shopify")

    if is_shopify:
        rename_map = {c: SHOPIFY_COLUMN_MAP[c] for c in df.columns if c in SHOPIFY_COLUMN_MAP}
        df = df.rename(columns=rename_map)

    # Ensure required columns exist
    required = [
        ColumnRule("order_id", True),
        ColumnRule("order_datetime_utc", True),
        ColumnRule("sku", True),
        ColumnRule("quantity_ordered", True),
        ColumnRule("customer_country", True),
    ]
    for col in [r.name for r in required]:
        if col not in df.columns:
            df[col] = pd.NA

    # Tenant columns
    df["account_id"] = account_id
    df["store_id"] = store_id
    df["platform"] = "shopify" if is_shopify else (platform_hint or "other")

    # Clean fields
    df["order_id"] = _safe_str(df["order_id"]).str.strip()
    df["sku"] = _safe_str(df["sku"]).str.strip().str.upper()

    # Datetime
    df["order_datetime_utc"] = _to_utc(df["order_datetime_utc"])

    # Quantity
    df["quantity_ordered"] = _to_int(df["quantity_ordered"], default=1)
    df.loc[df["quantity_ordered"] <= 0, "quantity_ordered"] = 1

    # Country/state
    df["customer_country"] = _safe_str(df["customer_country"]).str.strip().str.upper()
    # if someone gives full country names, we keep as-is for MVP; later can ISO-map
    df["customer_country"] = df["customer_country"].str[:2].where(df["customer_country"].str.len() >= 2, df["customer_country"])
    df["customer_state"] = _safe_str(df.get("customer_state", pd.Series([], dtype="string"))).str.strip()

    # Optional financial/shipping
    if "order_revenue" in df.columns:
        df["order_revenue"] = _to_float(df["order_revenue"])
    else:
        df["order_revenue"] = pd.NA

    if "currency" in df.columns:
        df["currency"] = _safe_str(df["currency"]).str.strip().str.upper()
    else:
        df["currency"] = default_currency

    if "shipping_method" in df.columns:
        df["shipping_method"] = _safe_str(df["shipping_method"]).str.strip()
    else:
        df["shipping_method"] = ""

    df["promised_ship_days"] = int(default_promised_ship_days)

    # Validation errors
    errors.extend(_require_cols(df, required, "orders"))

    # Drop obvious empties
    df = df[df["order_id"].str.len() > 0].copy()
    df = df[df["sku"].str.len() > 0].copy()

    out_cols = [
        "account_id",
        "store_id",
        "platform",
        "order_id",
        "order_datetime_utc",
        "sku",
        "quantity_ordered",
        "customer_country",
        "customer_state",
        "order_revenue",
        "currency",
        "shipping_method",
        "promised_ship_days",
    ]

    # keep any missing columns safe
    for c in out_cols:
        if c not in df.columns:
            df[c] = pd.NA

    return df[out_cols], _validation(errors)


def normalize_shipments(
    raw_shipments: pd.DataFrame,
    account_id: str,
    store_id: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Canonical Shipments output columns (one row per sku shipped):
      account_id, store_id, supplier_name, supplier_order_id,
      order_id, sku, quantity_shipped, ship_datetime_utc,
      carrier, tracking_number, ship_from_country, ship_to_country
    """
    errors: List[str] = []

    if raw_shipments is None or raw_shipments.empty:
        return pd.DataFrame(), _validation(["[shipments] Input shipments dataframe is empty."])

    df = _lower_cols(_clean_cols(raw_shipments))

    # Basic flexible renames (users will upload messy formats)
    rename_candidates = {
        "supplier": "supplier_name",
        "supplier name": "supplier_name",
        "vendor": "supplier_name",

        "supplier order id": "supplier_order_id",
        "supplier_order_id": "supplier_order_id",
        "po": "supplier_order_id",
        "purchase order": "supplier_order_id",

        "order id": "order_id",
        "order_id": "order_id",
        "shopify order id": "order_id",
        "name": "order_id",  # sometimes they paste Shopify order name

        "sku": "sku",
        "item sku": "sku",
        "lineitem sku": "sku",

        "quantity": "quantity_shipped",
        "qty": "quantity_shipped",
        "quantity shipped": "quantity_shipped",

        "ship date": "ship_datetime_utc",
        "shipped at": "ship_datetime_utc",
        "ship_datetime_utc": "ship_datetime_utc",
        "shipment date": "ship_datetime_utc",

        "carrier": "carrier",
        "tracking": "tracking_number",
        "tracking number": "tracking_number",
        "tracking_number": "tracking_number",

        "from country": "ship_from_country",
        "ship from country": "ship_from_country",
        "to country": "ship_to_country",
        "ship to country": "ship_to_country",
    }

    rename_map = {c: rename_candidates[c] for c in df.columns if c in rename_candidates}
    df = df.rename(columns=rename_map)

    # Ensure required columns exist
    required = [
        ColumnRule("supplier_name", True),
        ColumnRule("supplier_order_id", True),
        ColumnRule("sku", True),
        ColumnRule("quantity_shipped", True),
        ColumnRule("ship_datetime_utc", True),
    ]
    for col in [r.name for r in required]:
        if col not in df.columns:
            df[col] = pd.NA

    # Tenant
    df["account_id"] = account_id
    df["store_id"] = store_id

    # Clean types
    df["supplier_name"] = _safe_str(df["supplier_name"]).str.strip().replace("", "Unknown Supplier")
    df["supplier_order_id"] = _safe_str(df["supplier_order_id"]).str.strip()
    df["order_id"] = _safe_str(df.get("order_id", pd.Series([], dtype="string"))).str.strip()

    df["sku"] = _safe_str(df["sku"]).str.strip().str.upper()
    df["quantity_shipped"] = _to_int(df["quantity_shipped"], default=0)
    df["ship_datetime_utc"] = _to_utc(df["ship_datetime_utc"])

    df["carrier"] = _safe_str(df.get("carrier", pd.Series([], dtype="string"))).str.strip()
    df["tracking_number"] = _safe_str(df.get("tracking_number", pd.Series([], dtype="string"))).str.strip()

    df["ship_from_country"] = _safe_str(df.get("ship_from_country", pd.Series([], dtype="string"))).str.strip().str.upper().str[:2]
    df["ship_to_country"] = _safe_str(df.get("ship_to_country", pd.Series([], dtype="string"))).str.strip().str.upper().str[:2]

    # Validation
    errors.extend(_require_cols(df, required, "shipments"))

    # Drop empty criticals
    df = df[df["supplier_order_id"].str.len() > 0].copy()
    df = df[df["sku"].str.len() > 0].copy()

    out_cols = [
        "account_id",
        "store_id",
        "supplier_name",
        "supplier_order_id",
        "order_id",
        "sku",
        "quantity_shipped",
        "ship_datetime_utc",
        "carrier",
        "tracking_number",
        "ship_from_country",
        "ship_to_country",
    ]
    for c in out_cols:
        if c not in df.columns:
            df[c] = pd.NA

    return df[out_cols], _validation(errors)


def normalize_tracking(
    raw_tracking: pd.DataFrame,
    account_id: str,
    store_id: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Canonical Tracking output columns:
      account_id, store_id, carrier, tracking_number,
      order_id, supplier_order_id, tracking_status_raw,
      tracking_status_normalized, last_update_utc,
      delivery_date_utc, delivery_exception
    """
    errors: List[str] = []

    if raw_tracking is None or raw_tracking.empty:
        return pd.DataFrame(), _validation([])

    df = _lower_cols(_clean_cols(raw_tracking))

    rename_candidates = {
        "carrier": "carrier",
        "tracking number": "tracking_number",
        "tracking": "tracking_number",
        "tracking_number": "tracking_number",

        "order id": "order_id",
        "supplier order id": "supplier_order_id",

        "status": "tracking_status_raw",
        "tracking status": "tracking_status_raw",
        "tracking_status_raw": "tracking_status_raw",

        "last update": "last_update_utc",
        "last updated": "last_update_utc",
        "last_update_utc": "last_update_utc",

        "delivered at": "delivery_date_utc",
        "delivered": "delivery_date_utc",
        "delivery date": "delivery_date_utc",
        "delivery_date_utc": "delivery_date_utc",

        "exception": "delivery_exception",
        "delivery exception": "delivery_exception",
    }

    rename_map = {c: rename_candidates[c] for c in df.columns if c in rename_candidates}
    df = df.rename(columns=rename_map)

    required = [
        ColumnRule("tracking_number", True),
    ]
    for col in [r.name for r in required]:
        if col not in df.columns:
            df[col] = pd.NA

    df["account_id"] = account_id
    df["store_id"] = store_id

    df["carrier"] = _safe_str(df.get("carrier", pd.Series([], dtype="string"))).str.strip()
    df["tracking_number"] = _safe_str(df["tracking_number"]).str.strip()

    df["order_id"] = _safe_str(df.get("order_id", pd.Series([], dtype="string"))).str.strip()
    df["supplier_order_id"] = _safe_str(df.get("supplier_order_id", pd.Series([], dtype="string"))).str.strip()

    df["tracking_status_raw"] = _safe_str(df.get("tracking_status_raw", pd.Series([], dtype="string"))).str.strip()
    df["tracking_status_normalized"] = _safe_str(df.get("tracking_status_normalized", pd.Series([], dtype="string"))).str.strip()

    # Date fields
    if "last_update_utc" in df.columns:
        df["last_update_utc"] = _to_utc(df["last_update_utc"])
    else:
        df["last_update_utc"] = pd.NaT

    if "delivery_date_utc" in df.columns:
        df["delivery_date_utc"] = _to_utc(df["delivery_date_utc"])
    else:
        df["delivery_date_utc"] = pd.NaT

    df["delivery_exception"] = _safe_str(df.get("delivery_exception", pd.Series([], dtype="string"))).str.strip()

    errors.extend(_require_cols(df, required, "tracking"))

    # Drop empty tracking numbers
    df = df[df["tracking_number"].str.len() > 0].copy()

    out_cols = [
        "account_id",
        "store_id",
        "carrier",
        "tracking_number",
        "order_id",
        "supplier_order_id",
        "tracking_status_raw",
        "tracking_status_normalized",
        "last_update_utc",
        "delivery_date_utc",
        "delivery_exception",
    ]
    for c in out_cols:
        if c not in df.columns:
            df[c] = pd.NA

    return df[out_cols], _validation(errors)
