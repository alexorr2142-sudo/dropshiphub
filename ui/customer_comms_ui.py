# ui/customer_comms_ui.py
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_customer_email_generator(
    customer_emails: pd.DataFrame,
    copy_button=None,
):
    st.divider()
    st.subheader("Auto Customer Emails (Copy/Paste Ready)")

    if customer_emails is None or customer_emails.empty:
        st.info("No customer emails generated (no customer-impact exceptions detected).")
        return

    cols = [c for c in ["order_id", "customer_email", "template_type", "customer_risk"] if c in customer_emails.columns]
    st.dataframe(customer_emails[cols] if cols else customer_emails, use_container_width=True, height=240)

    st.download_button(
        "Download Customer Emails CSV",
        data=customer_emails.to_csv(index=False).encode("utf-8"),
        file_name="customer_emails.csv",
        mime="text/csv",
        key="btn_download_customer_emails_csv",
    )

    if "order_id" not in customer_emails.columns or "body" not in customer_emails.columns:
        return

    st.divider()
    st.markdown("### Customer email preview (select an order)")

    options = customer_emails["order_id"].dropna().astype(str).tolist()
    chosen = st.selectbox("Order", options, key="customer_email_preview_select")
    row = customer_emails[customer_emails["order_id"].astype(str) == str(chosen)].iloc[0]

    to_email = str(row.get("customer_email", "")).strip()
    subject = str(row.get("subject", "Update on your order")).strip()
    body = str(row.get("body", "")).strip()

    c1, c2, c3 = st.columns(3)
    with c1:
        if copy_button:
            copy_button(to_email, "Copy customer email", key=f"copy_customer_to_{chosen}")
        else:
            st.text_input("To", value=to_email, key=f"fallback_customer_to_{chosen}")

    with c2:
        if copy_button:
            copy_button(subject, "Copy subject", key=f"copy_customer_subject_{chosen}")
        else:
            st.text_input("Subject", value=subject, key=f"fallback_customer_subject_{chosen}")

    with c3:
        if copy_button:
            copy_button(body, "Copy body", key=f"copy_customer_body_{chosen}")
        else:
            st.text_area("Body", value=body, height=160, key=f"fallback_customer_body_{chosen}")

    st.text_input("To (customer email)", value=to_email, key="customer_to_preview")
    st.text_input("Subject", value=subject, key="customer_subject_preview")
    st.text_area("Body", value=body, height=260, key="customer_body_preview")

    st.download_button(
        "Download this email as .txt",
        data=(f"To: {to_email}\nSubject: {subject}\n\n{body}").encode("utf-8"),
        file_name=f"customer_email_order_{chosen}.txt".replace(" ", "_").lower(),
        mime="text/plain",
        key="btn_download_customer_email_txt",
    )
