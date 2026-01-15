# ui/customer_comms_ui.py
import pandas as pd
import streamlit as st

from core.customer_comms import build_customer_email_draft


def render_customer_comms_ui(customer_impact: pd.DataFrame):
    """
    Compact, email-first customer comms.
    Avoids rendering customer impact + emails as two big repeated blocks.
    """
    df = customer_impact if isinstance(customer_impact, pd.DataFrame) else pd.DataFrame()
    if df.empty:
        st.info("No customer-impact items detected.")
        return

    # minimal preview
    preview_cols = [c for c in ["order_id", "customer_email", "reason", "issue_summary", "supplier_name", "Urgency"] if c in df.columns]
    st.dataframe(df[preview_cols] if preview_cols else df, use_container_width=True, height=220)

    cols = df.columns.tolist()
    order_col = "order_id" if "order_id" in cols else ("order" if "order" in cols else None)
    email_col = "customer_email" if "customer_email" in cols else ("email" if "email" in cols else None)
    reason_col = "reason" if "reason" in cols else ("issue_summary" if "issue_summary" in cols else None)

    if order_col:
        opts = df[order_col].fillna("").astype(str).tolist()
        chosen = st.selectbox("Select order", opts, key="cust_comms_select_order")
        row = df[df[order_col].astype(str) == str(chosen)].iloc[0]
    else:
        chosen = "(customer item)"
        row = df.iloc[0]

    to_email = str(row.get(email_col, "")).strip() if email_col else ""
    reason = str(row.get(reason_col, "")).strip() if reason_col else ""

    draft = build_customer_email_draft(order_id=str(chosen), customer_email=to_email, reason=reason)

    st.text_input("To", value=draft["to"], disabled=True)
    subject = st.text_input("Subject", value=draft["subject"], key="cust_comms_subject")
    body = st.text_area("Body", value=draft["body"], height=260, key="cust_comms_body")

    st.download_button(
        "Download customer email .txt",
        data=(f"To: {to_email}\nSubject: {subject}\n\n{body}").encode("utf-8"),
        file_name=f"customer_email_{str(chosen)}".replace(" ", "_").lower() + ".txt",
        mime="text/plain",
        key="cust_comms_download_txt",
    )
