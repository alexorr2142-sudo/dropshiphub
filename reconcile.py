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


# -----------------------------
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

    df["quantity_shipped"] = df["quantity_shipped"].fillna(0).astype(int)

    # -----------------------------
    # Timing + lateness
    # -----------------------------
    df["days_since_order"] = (
        (now - df["order_datetime_utc"]).dt.total_seconds() / 86400
    ).astype(int)

    df["is_late"] = df["days_since_order"] > df["promised_ship_days"]

    # -----------------------------
    # Line status
    # -----------------------------
    def _line_status(row):
        if row["quantity_shipped"] <= 0:
            return "UNSHIPPED"
        if row["quantity_shipped"] < row["quantity_ordered"]:
            return "PARTIALLY_SHIPPED"
        return "SHIPPED"

    df["line_status"] = df.apply(_line_status, axis=1)

    # Delivered override if tracking says delivered
    if not tracking.empty and "tracking_number" in df.columns:
        delivered = tracking[
            tracking["delivery_date_utc"].notna()
        ]["tracking_number"].unique().tolist()

        df.loc[df["tracking_number"].isin(delivered), "line_status"] = "DELIVERED"

    # -----------------------------
    # Issue detection
    # -----------------------------
    issues = []

    for _, r in df.iterrows():
        if r["line_status"] == "UNSHIPPED" and r["is_late"]:
            issues.append("LATE_UNSHIPPED")
        elif r["line_status"] == "PARTIALLY_SHIPPED":
            issues.append("PARTIAL_SHIPMENT")
        elif r["line_status"] in ("SHIPPED", "DELIVERED") and not r["tracking_number"]:
            issues.append("MISSING_TRACKING")
        else:
            issues.append(None)

    df["issue_type"] = issues

    # -----------------------------
    # Exceptions table
    # -----------------------------
    exceptions = df[df["issue_type"].notna()].copy()

    exceptions = exceptions[
        [
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
        ]
    ]

    # -----------------------------
    # Supplier follow-ups
    # -----------------------------
    followups = (
        exceptions
        .groupby("supplier_name")
        .agg(
            item_count=("sku", "count"),
            order_ids=("order_id", lambda x: ", ".join(sorted(set(x)))),
        )
        .reset_index()
    )

    followups["urgency"] = followups["item_count"].apply(
        lambda x: "High" if x >= 3 else "Medium"
    )

    followups["subject"] = "Action required: outstanding shipments"
    followups["body"] = (
        "Hello,\n\n"
        "We are missing shipment confirmation or tracking for the following orders:\n\n"
        "Orders: " + followups["order_ids"] +
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

    return df, exceptions, followups, order_rollup, kpis
