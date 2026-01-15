# ui/comms_pack_ui.py
import io
import zipfile
import pandas as pd
import streamlit as st


def _safe(s: str) -> str:
    return "".join([c for c in (s or "") if c.isalnum() or c in ["_", "-", "."]]).strip()[:80] or "item"


def render_comms_pack_download(followups: pd.DataFrame, customer_impact: pd.DataFrame) -> None:
    st.divider()
    st.subheader("Comms Pack (Supplier + Customer)")

    fu = followups if isinstance(followups, pd.DataFrame) else pd.DataFrame()
    ci = customer_impact if isinstance(customer_impact, pd.DataFrame) else pd.DataFrame()

    c1, c2, c3 = st.columns(3)
    c1.metric("Open supplier followups", int(len(fu)))
    c2.metric("Customer impact items", int(len(ci)))
    c3.caption("Exports CSV + email .txt templates")

    if st.button("Build Comms Pack ZIP", use_container_width=True, key="btn_build_comms_pack"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            # CSVs
            z.writestr("supplier_followups_open.csv", fu.to_csv(index=False))
            z.writestr("customer_impact.csv", ci.to_csv(index=False))

            # Supplier email templates
            if not fu.empty:
                for i, r in fu.head(200).iterrows():
                    sname = str(r.get("supplier_name", "")).strip()
                    to = str(r.get("supplier_email", "")).strip()
                    subj = str(r.get("subject", "")).strip() or f"Shipment follow-up needed — {sname}".strip(" —")
                    body = str(r.get("body", "")).strip()
                    payload = f"To: {to}\nSubject: {subj}\n\n{body}"
                    z.writestr(f"supplier_emails/{_safe(sname or f'supplier_{i}')}.txt", payload)

            # Customer email templates (best-effort)
            if not ci.empty:
                cols = ci.columns.tolist()
                order_col = "order_id" if "order_id" in cols else ("order" if "order" in cols else None)
                email_col = "customer_email" if "customer_email" in cols else ("email" if "email" in cols else None)
                reason_col = "reason" if "reason" in cols else ("issue_summary" if "issue_summary" in cols else None)

                for i, r in ci.head(200).iterrows():
                    oid = str(r.get(order_col, "")).strip() if order_col else f"item_{i}"
                    to = str(r.get(email_col, "")).strip() if email_col else ""
                    reason = str(r.get(reason_col, "")).strip() if reason_col else ""
                    subj = f"Update on your order {oid}".strip()
                    body = (
                        "Hi there,\n\n"
                        f"We’re reaching out with an update on your order {oid}.\n\n"
                        f"Update: {reason}\n\n"
                        "What we’re doing next:\n"
                        "• We’ve contacted the supplier/carrier and requested an immediate status update.\n"
                        "• We’re monitoring the shipment and will update you as soon as we have confirmed details.\n"
                        "• If we can’t confirm progress quickly, we’ll offer next steps (replacement, refund, or alternative).\n\n"
                        "Thank you for your patience — we’ll follow up again soon.\n\n"
                        "Best,\n"
                    )
                    payload = f"To: {to}\nSubject: {subj}\n\n{body}"
                    z.writestr(f"customer_emails/{_safe(oid)}.txt", payload)

            z.writestr(
                "README.txt",
                "Comms Pack\n\n"
                "- supplier_followups_open.csv\n"
                "- customer_impact.csv\n"
                "- supplier_emails/*.txt\n"
                "- customer_emails/*.txt\n"
            )

        buf.seek(0)
        st.session_state["comms_pack_zip_bytes"] = buf.read()
        st.success("Comms pack built ✅")

    zip_bytes = st.session_state.get("comms_pack_zip_bytes")
    if zip_bytes:
        st.download_button(
            "⬇️ Download Comms Pack ZIP",
            data=zip_bytes,
            file_name="comms_pack.zip",
            mime="application/zip",
            use_container_width=True,
            key="btn_download_comms_pack",
        )
