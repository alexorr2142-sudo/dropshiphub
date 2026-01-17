# ui/supplier_escalation_email_ui.py
from __future__ import annotations

import urllib.parse

import pandas as pd
import streamlit as st


def _mailto_link(to: str, subject: str, body: str) -> str:
    params = {
        "subject": subject,
        "body": body,
    }
    q = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"mailto:{urllib.parse.quote(to)}?{q}" if to else f"mailto:?{q}"


def render_supplier_escalation_email_generator(
    followups_for_ops: pd.DataFrame,
    copy_button=None,
):
    """UI: generate an escalation email to a supplier.

    Expects (best effort) columns:
      supplier_name, supplier_email, order_ids, item_count, urgency, worst_escalation
    """
    st.divider()
    st.subheader("Supplier Email Generator (Escalation / Missing Updates)")

    if followups_for_ops is None or followups_for_ops.empty:
        st.info("No supplier follow-ups are currently needed.")
        return

    df = followups_for_ops.copy()
    if "supplier_name" not in df.columns:
        df["supplier_name"] = "(unknown supplier)"

    supplier_options = (
        df["supplier_name"].dropna().astype(str).map(lambda s: s.strip()).replace("", "(unknown supplier)").tolist()
    )
    if not supplier_options:
        supplier_options = ["(unknown supplier)"]

    chosen_supplier = st.selectbox(
        "Select supplier to generate an email",
        supplier_options,
        key="gen_email_supplier_select",
    )

    row = df[df["supplier_name"].astype(str) == str(chosen_supplier)].iloc[0]

    supplier_email = str(row.get("supplier_email", "") or "").strip()
    order_ids = str(row.get("order_ids", "") or "").strip()
    item_count = row.get("item_count", "")
    urgency = str(row.get("urgency", "") or "").strip()
    worst_escalation = str(row.get("worst_escalation", "") or "").strip()

    default_subject = "Action required: shipment status update needed"
    if worst_escalation:
        default_subject = f"Action required: {worst_escalation} — shipment update needed"

    subject = st.text_input(
        "Subject (editable)",
        value=default_subject,
        key="gen_email_subject",
    )

    extra_note = st.text_input(
        "Optional note to include",
        value="",
        key="gen_email_extra_note",
        placeholder="Add context, e.g., customer is requesting an update by EOD.",
    )

    # Body (simple + consistent)
    bullets = []
    if order_ids:
        bullets.append(f"Orders: {order_ids}")
    if item_count not in (None, ""):
        bullets.append(f"Items impacted: {item_count}")
    if urgency:
        bullets.append(f"Urgency: {urgency}")
    if worst_escalation:
        bullets.append(f"Escalation: {worst_escalation}")

    bullet_block = "\n".join([f"- {b}" for b in bullets]) if bullets else "- (order details missing)"

    body_lines = [
        f"Hi {chosen_supplier},",
        "",
        "We need an updated shipment status for the following orders:",
        bullet_block,
        "",
        "Please reply with:",
        "- Current shipment status (label created / in transit / delivered)",
        "- Carrier + tracking number (if available)",
        "- Estimated delivery date (or reason for delay)",
    ]
    if extra_note.strip():
        body_lines += ["", f"Note: {extra_note.strip()}"]

    body_lines += ["", "Thanks,", ""]

    body = "\n".join(body_lines)

    st.caption("Preview")
    st.text_area("Email body", value=body, height=220, key="gen_email_body_preview")

    c1, c2 = st.columns([1, 1])
    with c1:
        if copy_button is not None:
            copy_button(body, "Copy supplier email", key="copy_supplier_escalation_email")
        else:
            st.code(body)

    with c2:
        st.markdown(
            f"[Open email draft]({_mailto_link(supplier_email, subject, body)})",
            help="Opens your default email client with To/Subject/Body populated.",
        )

    if supplier_email:
        st.caption(f"To: {supplier_email}")
    else:
        st.warning("Supplier email address is missing for this supplier.")
