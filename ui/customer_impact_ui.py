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

import pandas as pd
import streamlit as st

from core.styling import copy_button


def render_customer_impact_view(df: pd.DataFrame):
    st.divider()
    st.subheader("Customer Impact View (Protect customer experience)")

    if df is None or df.empty:
        st.info("No customer-impact items detected 🎉")
        return

    # Quick filter controls
    c1, c2 = st.columns(2)

    with c1:
        categories = sorted(df["impact_category"].dropna().unique().tolist()) if "impact_category" in df.columns else []
        cat_filter = st.multiselect("Impact category", categories, default=categories)

    with c2:
        urgencies = ["Critical", "High", "Medium", "Low"]
        urg_filter = st.multiselect("Urgency", urgencies, default=[u for u in urgencies if u in df.get("Urgency", []).astype(str).unique()])

    view = df.copy()
    if cat_filter and "impact_category" in view.columns:
        view = view[view["impact_category"].isin(cat_filter)]
    if urg_filter and "Urgency" in view.columns:
        view = view[view["Urgency"].astype(str).isin(urg_filter)]

    st.dataframe(view, use_container_width=True, height=360)

    st.download_button(
        "Download Customer Impact CSV",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name="customer_impact_view.csv",
        mime="text/csv",
    )

    # Message preview tool
    if "customer_message_draft" in view.columns and len(view) > 0:
        st.divider()
        st.markdown("### Customer message preview (copy/paste)")

        label_col = "order_id" if "order_id" in view.columns else None
        options = list(range(len(view)))
        chosen_idx = st.selectbox(
            "Select row",
            options=options,
            format_func=lambda i: f"{view.iloc[i].get('impact_category','')} | Order {view.iloc[i].get(label_col,'')}".strip(),
            key="cust_impact_select",
        )

        row = view.iloc[int(chosen_idx)]
        msg = str(row.get("customer_message_draft", "")).strip()

        copy_button(msg, "Copy customer message", key=f"copy_customer_msg_{chosen_idx}")
        st.text_area("Message draft", value=msg, height=180, key="cust_msg_preview")
