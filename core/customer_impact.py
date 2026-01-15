# core/customer_impact.py
from __future__ import annotations
import pandas as pd


def build_customer_impact_view(exceptions: pd.DataFrame, max_items: int = 50) -> pd.DataFrame:
    if exceptions is None or exceptions.empty:
        return pd.DataFrame()

    df = exceptions.copy()

    # IMPORTANT: cast to string to avoid pandas Categorical fillna crash
    if "Urgency" not in df.columns:
        df["Urgency"] = "—"
    df["Urgency"] = df["Urgency"].astype(str)

    def classify(row) -> str:
        blob = " ".join(
            [
                str(row.get("issue_type", "")),
                str(row.get("explanation", "")),
                str(row.get("next_action", "")),
                str(row.get("line_status", "")),
            ]
        ).lower()

        if "missing tracking" in blob or "no tracking" in blob or ("tracking" in blob and "missing" in blob):
            return "Tracking missing"
        if "late" in blob or "overdue" in blob or "past due" in blob or "late unshipped" in blob:
            return "Shipping delay risk"
        if "partial" in blob or "quantity mismatch" in blob:
            return "Partial shipment / mismatch"
        if "address" in blob:
            return "Address issue"
        if "carrier exception" in blob or "returned to sender" in blob or "lost" in blob or "stuck" in blob:
            return "Carrier exception"
        return "Needs review"

    df["impact_type"] = df.apply(classify, axis=1)

    def draft(row) -> str:
        order_id = str(row.get("order_id", "")).strip()
        sku = str(row.get("sku", "")).strip()
        impact = str(row.get("impact_type", "Update")).strip()

        if impact == "Tracking missing":
            return (
                f"Hi! Quick update on your order {order_id}. "
                f"We’re confirming tracking details for item {sku} and will send tracking as soon as it’s available."
            )
        if impact == "Shipping delay risk":
            return (
                f"Hi! Your order {order_id} may be delayed due to supplier timing. "
                "We’re working to confirm the updated ship date and will update you shortly."
            )
        if impact == "Carrier exception":
            return (
                f"Hi! We’re seeing a carrier issue on order {order_id}. "
                "We’re investigating and will follow up with the next steps ASAP."
            )
        if impact == "Address issue":
            return (
                f"Hi! We need to confirm the shipping address for order {order_id}. "
                "Please reply to confirm the best address to deliver to."
            )
        if impact == "Partial shipment / mismatch":
            return (
                f"Hi! Part of order {order_id} may ship separately. "
                "We’ll send an update with the remaining shipment details shortly."
            )

        return f"Hi! Quick update on order {order_id}. We’re checking status and will follow up soon."

    df["customer_message_draft"] = df.apply(draft, axis=1)

    keep = [c for c in [
        "Urgency",
        "order_id",
        "sku",
        "customer_country",
        "supplier_name",
        "issue_type",
        "impact_type",
        "customer_message_draft",
    ] if c in df.columns]

    out = df[keep].copy()

    urgency_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    out["_u"] = out["Urgency"].astype(str).map(urgency_rank).fillna(9)
    out = out.sort_values(["_u"], ascending=True).drop(columns=["_u"], errors="ignore")

    return out.head(int(max_items)).reset_index(drop=True)
