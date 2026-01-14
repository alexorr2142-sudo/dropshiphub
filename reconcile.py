# normalize.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import pandas as pd
from dateutil import parser


# -----------------------------
# Utilities
# -----------------------------
def _clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def _lower_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    return out


def _safe_str(s: pd.Series) -> pd.Series:
    return s.astype("string").fillna("").astype("string")


def _to_int(s: pd.Series, default: int = 0) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(default).astype(int)


def _to_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _to_utc(s: pd.Series) -> pd.Series:
    """Parse mixed datetime strings -> tz-aware UTC timestamps (NaT if unparseable)."""
    def parse_one(x):
        if pd.isna(x) or str(x).strip() == "":
            return pd.NaT
        try:
            dt = parser.parse(str(x))
            ts = pd.Timestamp(dt)
            if ts.tzinfo is None:
                return ts.tz_localize("UTC")
            return ts.tz_convert("UTC")
        except Exception:
            return pd.NaT

    return s.apply(parse_one)


def _meta(errors: List[str]) -> Dict[str, Any]:
    return {"validation_errors": errors}


@dataclass(frozen=True)
class ColReq:
    name: str
    required: bool = True


def _require(df: pd.DataFrame, reqs: List[ColReq], table: str) -> List[str]:
    errs: List[str] = []
    cols = set(df.columns)
    for r in reqs:
        if r.required and r.name not in cols:
            errs.append(f"[{table}] Missing required column: {r.name}")
    return errs


# -----------------------------
# Shopify detection & mapping
# -----------------------------
def detect_shopify_orders(raw_df: pd.DataFrame) -> bool:
    df = _lower_cols(_clean_cols(raw_df))
    cols = set(df.columns)

    # Shopify exports vary, so we score "signals"
    signals = {
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
    return len(signals.intersection(cols)) >= 3


SHOPIFY_COLUMN_MAP = {
    # Order IDs
    "name": "order_id",
    "order id": "order_id",

    # Time
    "created at": "order_datetime_utc",

    # SKU variants
    "lineitem sku": "sku",
    "variant sku": "sku",
    "lineitem name": "sku",  # fallback only

    # Quantity
    "lineitem quantity": "quantity_ordered",
    "quantity": "quantity_ordered",

    # Geography
    "shipping country": "customer_country",
    "shipping province": "customer_state",

    # Financials
    "total": "order_revenue",
    "subtotal": "order_revenue",
    "currency": "currency",

    # Shipping method
    "shipping method": "shipping_method",
    "shipping line title": "shipping_method",
}


# -----------------------------
# Public functions used by app.py
# -----------------------------
def normalize_orders(
    raw_orders: pd.DataFrame,
    account_id: str,
    store_id: str,
    platform_hint: str = "shopify",
    default_currency: str = "USD",
    default_promised_ship_days: int = 3,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Produces canonical Orders (one row per order line / SKU):
      account_id, store_id, platform,
      order_id, order_datetime_utc,
      sku, quantity_ordered,
      customer_country, customer_state,
      order_revenue, currency, shipping_method,
      promised_ship_days

    Returns (df, meta) where meta['validation_errors'] lists missing/invalid fields.
    """
    errs: List[str] = []

    if raw_orders is None or raw_orders.empty:
        return pd.DataFrame(), _meta(["[orders] Input orders dataframe is empty."])

    df = _lower_cols(_clean_cols(raw_orders))

    is_shopify = detect_shopify_orders(raw_orders) or (platform_hint.lower() == "shopify")
    if is_shopify:
        rename_map = {c: SHOPIFY_COLUMN_MAP[c] for c in df.columns if c in SHOPIFY_COLUMN_MAP}
        df = df.rename(columns=rename_map)

    # Ensure required columns exist (create if missing)
    required = [
        ColReq("order_id", True),
        ColReq("order_datetime_utc", True),
        ColReq("sku", True),
        ColReq("quantity_ordered", True),
        ColReq("customer_country", True),
    ]
    for r in required:
        if r.name not in df.columns:
            df[r.name] = pd.NA

    # Tenant + platform
    df["account_id"] = account_id
    df["store_id"] = store_id
    df["platform"] = "shopify" if is_shopify else (platform_hint or "other")

    # Clean fields
    df["order_id"] = _safe_str(df["order_id"]).str.strip()
    df["sku"] = _safe_str(df["sku"]).str.strip().str.upper()

    df["order_datetime_utc"] = _to_utc(df["order_datetime_utc"])

    df["quantity_ordered"] = _to_int(df["quantity_ordered"], default=1)
    df.loc[df["quantity_ordered"] <= 0, "quantity_ordered"] = 1

    df["customer_country"] = _safe_str(df["customer_country"]).str.strip().str.upper()
    df["customer_state"] = _safe_str(df.get("customer_state", pd.Series(dtype="string"))).str.strip()

    # Optional columns
    df["order_revenue"] = _to_float(df["order_revenue"]) if "order_revenue" in df.columns else pd.NA
    df["currency"] = _safe_str(df["currency"]).str.strip().str.upper() if "currency" in df.columns else default_currency
    df["shipping_method"] = _safe_str(df["shipping_method"]).str.strip() if "shipping_method" in df.columns else ""

    df["promised_ship_days"] = int(default_promised_ship_days)

    # Validation + cleanup
    errs.extend(_require(df, required, "orders"))
    df = df[df["order_id"].str.len() > 0].copy()
    df = df[df["sku"].str.len() > 0].copy()

    out_cols = [
        "account_id", "store_id", "platform",
        "order_id", "order_datetime_utc",
        "sku", "quantity_ordered",
        "customer_country", "customer_state",
        "order_revenue", "currency", "shipping_method",
        "promised_ship_days",
    ]
    for c in out_cols:
        if c not in df.columns:
            df[c] = pd.NA

    return df[out_cols], _meta(errs)


def normalize_shipments(
    raw_shipments: pd.DataFrame,
    account_id: str,
    store_id: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Produces canonical Shipments (one row per shipped SKU line):
      account_id, store_id,
      supplier_name, supplier_order_id, order_id,
      sku, quantity_shipped,
      ship_datetime_utc, carrier, tracking_number,
      ship_from_country, ship_to_country
    """
    errs: List[str] = []

    if raw_shipments is None or raw_shipments.empty:
        return pd.DataFrame(), _meta(["[shipments] Input shipments dataframe is empty."])

    df = _lower_cols(_clean_cols(raw_shipments))

    # Flexible renames for common supplier export fields
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
        "name": "order_id",

        "sku": "sku",
        "item sku": "sku",
        "lineitem sku": "sku",

        "quantity": "quantity_shipped",
        "qty": "quantity_shipped",
        "quantity shipped": "quantity_shipped",

        "ship date": "ship_datetime_utc",
        "shipped at": "ship_datetime_utc",
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

    df = df.rename(columns={c: rename_candidates[c] for c in df.columns if c in rename_candidates})

    required = [
        ColReq("supplier_name", True),
        ColReq("supplier_order_id", True),
        ColReq("sku", True),
        ColReq("quantity_shipped", True),
        ColReq("ship_datetime_utc", True),
    ]
    for r in required:
        if r.name not in df.columns:
            df[r.name] = pd.NA

    df["account_id"] = account_id
    df["store_id"] = store_id

    df["supplier_name"] = _safe_str(df["supplier_name"]).str.strip()
    df.loc[df["supplier_name"].str.len() == 0, "supplier_name"] = "Unknown Supplier"

    df["supplier_order_id"] = _safe_str(df["supplier_order_id"]).str.strip()
    df["order_id"] = _safe_str(df.get("order_id", pd.Series(dtype="string"))).str.strip()

    df["sku"] = _safe_str(df["sku"]).str.strip().str.upper()
    df["quantity_shipped"] = _to_int(df["quantity_shipped"], default=0)
    df["ship_datetime_utc"] = _to_utc(df["ship_datetime_utc"])

    df["carrier"] = _safe_str(df.get("carrier", pd.Series(dtype="string"))).str.strip()
    df["tracking_number"] = _safe_str(df.get("tracking_number", pd.Series(dtype="string"))).str.strip()

    df["ship_from_country"] = _safe_str(df.get("ship_from_country", pd.Series(dtype="string"))).str.strip().str.upper().str[:2]
    df["ship_to_country"] = _safe_str(df.get("ship_to_country", pd.Series(dtype="string"))).str.strip().str.upper().str[:2]

    errs.extend(_require(df, required, "shipments"))

    df = df[df["supplier_order_id"].str.len() > 0].copy()
    df = df[df["sku"].str.len() > 0].copy()

    out_cols = [
        "account_id", "store_id",
        "supplier_name", "supplier_order_id", "order_id",
        "sku", "quantity_shipped",
        "ship_datetime_utc", "carrier", "tracking_number",
        "ship_from_country", "ship_to_country",
    ]
    for c in out_cols:
        if c not in df.columns:
            df[c] = pd.NA

    return df[out_cols], _meta(errs)


def normalize_tracking(
    raw_tracking: pd.DataFrame,
    account_id: str,
    store_id: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Produces canonical Tracking:
      account_id, store_id,
      carrier, tracking_number,
      order_id, supplier_order_id,
      tracking_status_raw, tracking_status_normalized,
      last_update_utc, delivery_date_utc,
      delivery_exception
    """
    errs: List[str] = []

    if raw_tracking is None or raw_tracking.empty:
        return pd.DataFrame(), _meta([])

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

        "last update": "last_update_utc",
        "last updated": "last_update_utc",

        "delivered at": "delivery_date_utc",
        "delivered": "delivery_date_utc",
        "delivery date": "delivery_date_utc",

        "exception": "delivery_exception",
        "delivery exception": "delivery_exception",
    }

    df = df.rename(columns={c: rename_candidates[c] for c in df.columns if c in rename_candidates})

    required = [ColReq("tracking_number", True)]
    if "tracking_number" not in df.columns:
        df["tracking_number"] = pd.NA

    df["account_id"] = account_id
    df["store_id"] = store_id

    df["carrier"] = _safe_str(df.get("carrier", pd.Series(dtype="string"))).str.strip()
    df["tracking_number"] = _safe_str(df["tracking_number"]).str.strip()

    df["order_id"] = _safe_str(df.get("order_id", pd.Series(dtype="string"))).str.strip()
    df["supplier_order_id"] = _safe_str(df.get("supplier_order_id", pd.Series(dtype="string"))).str.strip()

    df["tracking_status_raw"] = _safe_str(df.get("tracking_status_raw", pd.Series(dtype="string"))).str.strip()
    df["tracking_status_normalized"] = _safe_str(df.get("tracking_status_normalized", pd.Series(dtype="string"))).str.strip()

    df["last_update_utc"] = _to_utc(df["last_update_utc"]) if "last_update_utc" in df.columns else pd.NaT
    df["delivery_date_utc"] = _to_utc(df["delivery_date_utc"]) if "delivery_date_utc" in df.columns else pd.NaT
    df["delivery_exception"] = _safe_str(df.get("delivery_exception", pd.Series(dtype="string"))).str.strip()

    errs.extend(_require(df, required, "tracking"))
    df = df[df["tracking_number"].str.len() > 0].copy()

    out_cols = [
        "account_id", "store_id",
        "carrier", "tracking_number",
        "order_id", "supplier_order_id",
        "tracking_status_raw", "tracking_status_normalized",
        "last_update_utc", "delivery_date_utc",
        "delivery_exception",
    ]
    for c in out_cols:
        if c not in df.columns:
            df[c] = pd.NA

    return df[out_cols], _meta(errs)
