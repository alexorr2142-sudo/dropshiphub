from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd

from core.reconcile_helpers import _canonicalize_keys, _now_utc, _to_dt

# Core reconciliation function
# -----------------------------
def reconcile_all(
    orders: pd.DataFrame,
    shipments: pd.DataFrame,
    tracking: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    """
    Returns:
      line_status_df : one row per order line (SKU)
      exceptions     : actionable issues
      followups      : grouped supplier follow-ups
      order_rollup   : one row per order
      kpis           : summary metrics dict
    """

    now = _now_utc()

    # ✅ NEW: schema guard (prevents KeyError in groupby/merge)
    orders = _canonicalize_keys(orders, df_name="orders")
    shipments = _canonicalize_keys(shipments, df_name="shipments")
    if tracking is None:
        tracking = pd.DataFrame()

    # Also ensure these exist to avoid later .get() surprises
    if "quantity_ordered" not in orders.columns:
        orders["quantity_ordered"] = 0
    if "quantity_shipped" not in shipments.columns:
        shipments["quantity_shipped"] = 0

    # Normalize ship_datetime_utc if present
    if "ship_datetime_utc" in shipments.columns:
        shipments["ship_datetime_utc"] = _to_dt(shipments["ship_datetime_utc"])

    # -----------------------------
    # Aggregate shipments per order+SKU
    # -----------------------------
    ship_agg = (
        shipments
        .groupby(["order_id", "sku"], dropna=False)
        .agg(
            quantity_shipped=("quantity_shipped", "sum"),
            supplier_name=("supplier_name", "first"),
            supplier_order_id=("supplier_order_id", "first"),
            carrier=("carrier", "first"),
            tracking_number=("tracking_number", "first"),
            ship_datetime_utc=("ship_datetime_utc", "min"),
        )
        .reset_index()
    )

    # -----------------------------
    # Merge orders + shipments
    # -----------------------------
    df = orders.merge(
        ship_agg,
        how="left",
        on=["order_id", "sku"],
        suffixes=("", "_ship"),
    )

    df["quantity_shipped"] = df.get("quantity_shipped", 0).fillna(0)
    try:
        df["quantity_shipped"] = df["quantity_shipped"].astype(int)
    except Exception:
        df["quantity_shipped"] = pd.to_numeric(df["quantity_shipped"], errors="coerce").fillna(0).astype(int)

    # -----------------------------
    # ✅ SLA date fields (NEW — required for SLA escalations)
    # -----------------------------
    # Normalize order datetime into a consistent created column
    if "order_datetime_utc" in df.columns:
        df["order_datetime_utc"] = _to_dt(df["order_datetime_utc"])
        df["order_created_at"] = df["order_datetime_utc"]
    elif "order_created_at" in df.columns:
        df["order_created_at"] = _to_dt(df["order_created_at"])
    else:
        # If no date exists, create a null column (SLA escalations will still show "missing date")
        df["order_created_at"] = pd.NaT

    # Compute a due date using promised_ship_days if present
    # Use an integer fallback if it’s missing or non-numeric
    if "promised_ship_days" in df.columns:
        try:
            df["promised_ship_days"] = pd.to_numeric(df["promised_ship_days"], errors="coerce").fillna(0).astype(int)
        except Exception:
            df["promised_ship_days"] = 0
    else:
        df["promised_ship_days"] = 0

    # sla_due_date = created + promised_ship_days (no grace here; grace is controlled in the SLA UI)
    df["sla_due_date"] = df["order_created_at"] + pd.to_timedelta(df["promised_ship_days"], unit="D")

    # -----------------------------
    # Timing + lateness
    # -----------------------------
    # days_since_order uses order_datetime_utc if available, else order_created_at
    base_dt = df["order_datetime_utc"] if "order_datetime_utc" in df.columns else df["order_created_at"]

    df["days_since_order"] = (
        (now - base_dt).dt.total_seconds() / 86400
    )

    # keep robust int conversion
    df["days_since_order"] = pd.to_numeric(df["days_since_order"], errors="coerce").fillna(0).astype(int)

    df["is_late"] = df["days_since_order"] > df["promised_ship_days"]

    # -----------------------------
    # Line status
    # -----------------------------
    def _line_status(row):
        try:
            qs = int(row.get("quantity_shipped", 0) or 0)
            qo = int(row.get("quantity_ordered", 0) or 0)
        except Exception:
            qs = pd.to_numeric(row.get("quantity_shipped", 0), errors="coerce")
            qo = pd.to_numeric(row.get("quantity_ordered", 0), errors="coerce")
            qs = int(0 if pd.isna(qs) else qs)
            qo = int(0 if pd.isna(qo) else qo)

        if qs <= 0:
            return "UNSHIPPED"
        if qs < qo:
            return "PARTIALLY_SHIPPED"
        return "SHIPPED"

    df["line_status"] = df.apply(_line_status, axis=1)

    # Delivered override if tracking says delivered
    if tracking is not None and not tracking.empty and "tracking_number" in df.columns:
        # tolerate different tracking schemas
        t = tracking.copy()

        # try common rename(s)
        if "tracking_number" not in t.columns and "Tracking Number" in t.columns:
            t["tracking_number"] = t["Tracking Number"]
        if "Delivered At" in t.columns and "delivery_date_utc" not in t.columns:
            # tolerate string timestamps; we only check notna
            pass

        delivered = []
        if "delivery_date_utc" in t.columns:
            delivered = t[t["delivery_date_utc"].notna()]["tracking_number"].dropna().unique().tolist()
        elif "Delivered At" in t.columns:
            delivered = t[t["Delivered At"].notna()]["tracking_number"].dropna().unique().tolist()

        if delivered:
            df.loc[df["tracking_number"].isin(delivered), "line_status"] = "DELIVERED"

    # -----------------------------
    # Issue detection
    # -----------------------------
    issues = []

    for _, r in df.iterrows():
        tracking_num = r.get("tracking_number", "")
        has_tracking = bool(str(tracking_num).strip())

        if r["line_status"] == "UNSHIPPED" and bool(r.get("is_late", False)):
            issues.append("LATE_UNSHIPPED")
        elif r["line_status"] == "PARTIALLY_SHIPPED":
            issues.append("PARTIAL_SHIPMENT")
        elif r["line_status"] in ("SHIPPED", "DELIVERED") and not has_tracking:
            issues.append("MISSING_TRACKING")
        else:
            issues.append(None)

    df["issue_type"] = issues

    # -----------------------------
    # Exceptions table
    # -----------------------------
    exceptions = df[df["issue_type"].notna()].copy()

    # Keep only columns that exist (prevents KeyError if schema changes)
    preferred_exc_cols = [
        "account_id",
        "store_id",
        "platform",
        "order_id",
        "sku",
        "issue_type",
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
        # ✅ include these if present (helps downstream / SLA)
        "order_created_at",
        "sla_due_date",
    ]
    exc_cols = [c for c in preferred_exc_cols if c in exceptions.columns]
    exceptions = exceptions[exc_cols]

    # -----------------------------
    # Supplier follow-ups
    # -----------------------------
    if exceptions is None or exceptions.empty or "supplier_name" not in exceptions.columns:
        followups = pd.DataFrame(columns=["supplier_name", "item_count", "order_ids", "urgency", "subject", "body"])
    else:
        followups = (
            exceptions
            .groupby("supplier_name")
            .agg(
                item_count=("sku", "count") if "sku" in exceptions.columns else ("order_id", "count"),
                order_ids=("order_id", lambda x: ", ".join(sorted(set([str(v) for v in x if str(v).strip() != ""])))) if "order_id" in exceptions.columns else ("supplier_name", "first"),
            )
            .reset_index()
        )

        followups["urgency"] = followups["item_count"].apply(
            lambda x: "High" if float(x) >= 3 else "Medium"
        )

        followups["subject"] = "Action required: outstanding shipments"
        followups["body"] = (
            "Hello,\n\n"
            "We are missing shipment confirmation or tracking for the following orders:\n\n"
            "Orders: " + followups["order_ids"].astype(str) +
            "\n\nPlease provide tracking or an updated ship date.\n\nThank you."
        )

    # -----------------------------
    # Order-level rollup
    # -----------------------------
    order_rollup = (
        df
        .groupby("order_id")
        .agg(
            internal_status=("line_status", lambda x: "Issue" if (x != "DELIVERED").any() else "OK"),
            customer_facing_status=("line_status", "min"),
            top_issue=("issue_type", lambda x: x.dropna().iloc[0] if x.notna().any() else ""),
            risk_score=("is_late", "sum"),
        )
        .reset_index()
    )

    order_rollup["risk_band"] = order_rollup["risk_score"].apply(
        lambda x: "High" if x >= 2 else "Medium" if x == 1 else "Low"
    )

    # -----------------------------
    # KPIs
    # -----------------------------
    total_lines = len(df)
    kpis = {
        "total_order_lines": total_lines,
        "pct_shipped_or_delivered": round(
            100 * (df["line_status"].isin(["SHIPPED", "DELIVERED"]).sum() / total_lines), 1
        ) if total_lines else 0,
        "pct_delivered": round(
            100 * (df["line_status"] == "DELIVERED").sum() / total_lines, 1
        ) if total_lines else 0,
        "pct_unshipped": round(
            100 * (df["line_status"] == "UNSHIPPED").sum() / total_lines, 1
        ) if total_lines else 0,
        "pct_late_unshipped": round(
            100 * ((df["line_status"] == "UNSHIPPED") & (df["is_late"])).sum() / total_lines, 1
        ) if total_lines else 0,
    }

    # ✅ IMPORTANT: we return df as line_status_df (includes sla_due_date + order_created_at now)
    return df, exceptions, followups, order_rollup, kpis
