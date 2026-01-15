# ui/customer_comms_ui.py
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import streamlit as st


@dataclass
class CustomerEmail:
    order_id: str
    to_email: str
    subject: str
    body: str
    reason: str = ""


def _pick_col(cols: list[str], options: list[str]) -> Optional[str]:
    for c in options:
        if c in cols:
            return c
    return None


def _safe_str(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()


def _default_subject(order_id: str) -> str:
    if order_id and order_id != "(customer item)":
        return f"Update on your order {order_id}"
    return "Order update"


def _default_body(order_id: str, reason: str, signature: str = "Ops Team") -> str:
    lines = []
    lines.append("Hi there,")
    lines.append("")
    if order_id and order_id != "(customer item)":
        lines.append(f"We’re reaching out with an update on your order {order_id}.")
    else:
        lines.append("We’re reaching out with an update on your order.")

    if reason:
        lines.append("")
        lines.append(f"Update: {reason}")

    lines.append("")
    lines.append("What we’re doing next:")
    lines.append("• We’ve contacted the supplier/carrier and requested an immediate status update.")
    lines.append("• We’re monitoring progress and will share confirmed details as soon as we have them.")
    lines.append("• If we can’t confirm progress quickly, we’ll offer next steps (replacement, refund, or alternative).")
    lines.append("")
    lines.append("Thank you for your patience — we’ll follow up again soon.")
    lines.append("")
    lines.append("Best,")
    lines.append(signature.strip() if signature else "Ops Team")
    return "\n".join(lines)


def _download_txt(to_email: str, subject: str, body: str) -> bytes:
    payload = f"To: {to_email}\nSubject: {subject}\n\n{body}"
    return payload.encode("utf-8")


def render_customer_comms_ui(
    customer_impact: pd.DataFrame,
    title: str = "Customer Emails (Auto-generated)",
    max_preview_rows: int = 200,
) -> pd.DataFrame:
    """
    Import-safe, compact customer email generator.

    Returns a DataFrame of generated emails with columns:
    order_id, to_email, subject, body, reason
    """
    st.subheader(title)

    if customer_impact is None or customer_impact.empty:
        st.caption("No customer-impact items detected.")
        return pd.DataFrame(columns=["order_id", "to_email", "subject", "body", "reason"])

    df = customer_impact.copy()

    cols = df.columns.tolist()
    order_col = _pick_col(cols, ["order_id", "order", "Order ID", "Order"])
    email_col = _pick_col(cols, ["customer_email", "email", "Email", "Customer Email"])
    reason_col = _pick_col(cols, ["reason", "issue_summary", "explanation", "summary", "Issue", "Issue Summary"])

    view = pd.DataFrame()
    view["order_id"] = df[order_col].map(_safe_str) if order_col else "(customer item)"
    view["to_email"] = df[email_col].map(_safe_str) if email_col else ""
    view["reason"] = df[reason_col].map(_safe_str) if reason_col else ""
    view = view.fillna("")

    tab_compose, tab_candidates, tab_bulk = st.tabs(["Compose", "Candidates", "Bulk"])

    with tab_candidates:
        st.dataframe(view.head(int(max_preview_rows)), use_container_width=True, height=320)

    with tab_compose:
        options = view["order_id"].tolist()
        chosen = st.selectbox("Select order", options, key="cust_email_select_order_ui")

        crow = view[view["order_id"] == chosen].iloc[0] if len(view) else None
        order_id = _safe_str(crow["order_id"]) if crow is not None else "(customer item)"
        to_email = _safe_str(crow["to_email"]) if crow is not None else ""
        reason = _safe_str(crow["reason"]) if crow is not None else ""

        st.markdown("**To**")
        st.code(to_email if to_email else "(missing email in customer impact data)")

        subject = st.text_input("Subject", value=_default_subject(order_id), key="cust_email_subject_ui")
        signature = st.text_input("Signature", value="Ops Team", key="cust_email_sig_ui")
        body = st.text_area(
            "Body",
            value=_default_body(order_id, reason, signature=signature),
            height=260,
            key="cust_email_body_ui",
        )

        st.download_button(
            "Download this email (.txt)",
            data=_download_txt(to_email, subject, body),
            file_name=f"customer_email_{str(order_id).replace(' ', '_').lower()}.txt",
            mime="text/plain",
            use_container_width=True,
            key="cust_email_download_one_ui",
        )

        emails_df = pd.DataFrame(
            [{"order_id": order_id, "to_email": to_email, "subject": subject, "body": body, "reason": reason}]
        )
        return emails_df

    with tab_bulk:
        signature_bulk = st.text_input("Signature (bulk)", value="Ops Team", key="cust_email_bulk_sig_ui")
        out_rows = []
        for _, r in view.iterrows():
            oid = _safe_str(r["order_id"]) or "(customer item)"
            em = _safe_str(r["to_email"])
            rsn = _safe_str(r["reason"])
            out_rows.append(
                CustomerEmail(
                    order_id=oid,
                    to_email=em,
                    subject=_default_subject(oid),
                    body=_default_body(oid, rsn, signature=signature_bulk),
                    reason=rsn,
                ).__dict__
            )

        emails_df = pd.DataFrame(out_rows)
        st.dataframe(emails_df, use_container_width=True, height=320)

        st.download_button(
            "Download emails.csv",
            data=emails_df.to_csv(index=False).encode("utf-8"),
            file_name="customer_emails.csv",
            mime="text/csv",
            use_container_width=True,
            key="cust_email_bulk_csv_ui",
        )

        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for _, r in emails_df.iterrows():
                oid = _safe_str(r.get("order_id", "order"))
                fn = f"customer_email_{oid.replace(' ', '_').lower()}.txt"
                z.writestr(fn, _download_txt(r.get("to_email", ""), r.get("subject", ""), r.get("body", "")).decode("utf-8"))
        buf.seek(0)

        st.download_button(
            "Download all emails (.zip)",
            data=buf.read(),
            file_name="customer_emails_txt.zip",
            mime="application/zip",
            use_container_width=True,
            key="cust_email_bulk_zip_ui",
        )

        return emails_df
