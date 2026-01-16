# core/comms_pack.py
import io
import zipfile
from datetime import datetime

import pandas as pd


def _safe_filename(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in ["-", "_"]:
            out.append(ch)
        elif ch in [" ", ".", "/"]:
            out.append("_")
    return "".join(out)[:80] or "file"


def make_comms_pack_bytes(
    followups: pd.DataFrame,
    customer_impact: pd.DataFrame,
    max_supplier: int = 50,
    max_customer: int = 50,
) -> tuple[bytes, str]:
    """
    Returns (zip_bytes, suggested_filename)
    """
    buf = io.BytesIO()
    date_tag = datetime.now().strftime("%Y%m%d")
    zip_name = f"comms_pack_{date_tag}.zip"

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # Supplier emails
        if followups is not None and not followups.empty:
            f = followups.copy().head(int(max_supplier))
            if "supplier_name" in f.columns and "body" in f.columns:
                for i, r in f.iterrows():
                    sname = str(r.get("supplier_name", "supplier")).strip()
                    to = str(r.get("supplier_email", "")).strip()
                    subject = str(r.get("subject", "Action required: outstanding shipments")).strip()
                    body = str(r.get("body", "")).strip()

                    fname = f"supplier_emails/supplier__{_safe_filename(sname)}__{i}.txt"
                    payload = f"To: {to}\nSubject: {subject}\n\n{body}\n"
                    z.writestr(fname, payload)

        # Customer emails
        if customer_impact is not None and not customer_impact.empty:
            c = customer_impact.copy().head(int(max_customer))
            if "customer_message_draft" in c.columns:
                for i, r in c.iterrows():
                    order_id = str(r.get("order_id", "")).strip()

                    # Prefer impact_type, fallback to impact_category, else default
                    cat = str(r.get("impact_type", r.get("impact_category", "customer_update"))).strip()

                    msg = str(r.get("customer_message_draft", "")).strip()

                    # Optional: include customer email if present
                    cust_to = str(r.get("customer_email", "")).strip()

                    name_part = f"order_{order_id}" if order_id else f"row_{i}"
                    fname = (
                        f"customer_emails/customer__{_safe_filename(name_part)}__{_safe_filename(cat)}__{i}.txt"
                    )

                    header = "Subject: Update on your order\n"
                    if cust_to:
                        header = f"To: {cust_to}\n" + header

                    payload = f"{header}\n{msg}\n"
                    z.writestr(fname, payload)

        # README (branding)
        z.writestr(
            "README.txt",
            "ClearOps - Bulk Comms Pack\n\n"
            "supplier_emails/: supplier follow-ups (To/Subject/Body)\n"
            "customer_emails/: customer updates (draft messages)\n"
            "\nTip: You can edit these .txt files before sending.\n"
        )

    buf.seek(0)
    return buf.read(), zip_name
