# ui/supplier_escalation_email_ui.py
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_supplier_escalation_email_generator(
    followups_for_ops: pd.DataFrame,
    copy_button=None,
):
    st.divider()
    st.subheader("Supplier Email Generator (Escalation / Missing Updates)")

    if followups_for_ops is None or followups_for_ops.empty:
        st.info("No supplier follow-ups are currently needed.")
        return

    if "supplier_name" in followups_for_ops.columns:
        supplier_options = followups_for_ops["supplier_name"].dropna().astype(str).tolist()
    else:
        supplier_options = ["(unknown supplier)"]

    chosen_supplier = st.selectbox(
        "Select supplier to generate an email",
        supplier_options,
        key="gen_email_supplier_select",
    )

    if "supplier_name" in followups_for_ops.columns:
        row = followups_for_ops[followups_for_ops["supplier_name"].astype(str) == str(chosen_supplier)].iloc[0]
    else:
        row = followups_for_ops.iloc[0]

    supplier_email = str(row.get("supplier_email", "")).strip() if "supplier_email" in followups_for_ops.columns else ""
    order_ids = str(row.get("order_ids", "")).strip() if "order_ids" in followups_for_ops.columns else ""
    item_count = row.get("item_count", "")
    urgency = row.get("urgency", "")
    worst_escalation = row.get("worst_escalation", "")

    default_subject = "Action required: shipment status update needed"
    if str(worst_escalation).strip():
        default_subject = f"Action required: {worst_escalation} — shipment update needed"

    subject = st.text_input(
        "Subject (editable)",
        value=default_subject,
        key="gen_email_subject",
    )

    extra_note = st.text_input(
        "Optional note to include (
