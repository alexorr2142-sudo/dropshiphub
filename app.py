# app.py
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# --- Local modules (your repo files) ---
# If these imports fail, Streamlit will crash—so we wrap with a helpful message.
try:
    from normalize import normalize_orders, normalize_shipments, normalize_tracking
    from reconcile import reconcile_all
    from explain import enhance_explanations
except Exception as e:
    st.set_page_config(page_title="Dropship Hub", layout="wide")
    st.title("Dropship Hub")
    st.error("Import error: one of your local .py files is missing or has an error.")
    st.code(str(e))
    st.stop()


def copy_button(text: str, label: str, key: str):
    """
    Renders a button that copies `text` to clipboard using the browser clipboard API.
    Uses a unique `key` to avoid DOM id collisions.
    """
    # Escape for JS template literal
    safe_text = (
        str(text)
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )
    html = f"""
    <div style="margin: 0.25rem 0;">
      <button
        id="btn-{key}"
        style="
          padding: 0.45rem 0.75rem;
          border-radius: 0.5rem;
          border: 1px solid rgba(49, 51, 63, 0.2);
          background: white;
          cursor: pointer;
          font-size: 0.9rem;
        "
        onclick="navigator.clipboard.writeText(`{safe_text}`)
          .then(() => {{
            const b = document.getElementById('btn-{key}');
            const old = b.innerText;
            b.innerText = 'Copied ✅';
            setTimeout(() => b.innerText = old, 1200);
          }})
          .catch(() => alert('Copy failed. Your browser may block clipboard access.'));">
        {label}
      </button>
    </div>
    """
    components.html(html, height=55)


# -------------------------------
# NEW: Exceptions urgency + styling (Step B)
# -------------------------------
def add_urgency_column(exceptions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds an 'Urgency' column based on issue_type/explanation/next_action/customer_risk.
    This is best-effort and safe (won't crash if columns are missing).
    """
    df = exceptions_df.copy()

    # Pick a text column to classify from (best effort)
    # We'll combine several columns if present.
    def classify_row(row) -> str:
        issue_type = str(row.get("issue_type", "")).lower()
        explanation = str(row.get("explanation", "")).lower()
        next_action = str(row.get("next_action", "")).lower()
        risk = str(row.get("customer_risk", "")).lower()

        blob = " ".join([issue_type, explanation, next_action, risk])

        # Critical signals
        critical_terms = [
            "late unshipped", "late", "past due", "overdue",
            "address missing", "missing address",
            "missing tracking", "no tracking",
            "carrier exception", "exception", "returned to sender",
            "lost", "stuck", "seized"
        ]
        if any(t in blob for t in critical_terms):
            return "Critical"

        # High signals
        high_terms = [
            "partial", "partial shipment",
            "mismatch", "quantity mismatch",
            "invalid tracking", "tracking invalid",
            "carrier unknown", "unknown carrier",
            "needs follow up", "follow-up", "follow up"
        ]
        if any(t in blob for t in high_terms):
            return "High"

        # Medium signals
        med_terms = ["verify", "check", "confirm", "format", "invalid", "missing"]
        if any(t in blob for t in med_terms):
            return "Medium"

        return "Low"

    df["Urgency"] = df.apply(classify_row, axis=1)

    # Order for sorting
    order = ["Critical", "High", "Medium", "Low"]
    df["Urgency"] = pd.Categorical(df["Urgency"], categories=order, ordered=True)

    return df


def style_exceptions_table(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """
    Row highlighting based on Urgency.
    """
    if "Urgency" not in df.columns:
        return df.style

    colors = {
        "Critical": "background-color: #ffd6d6;",
        "High": "background-color: #fff1cc;",
        "Medium": "background-color: #f3f3f3;",
        "Low": ""
    }

    def row_style(row):
        u = row.get("Urgency", "Low")
        return [colors.get(str(u), "")] * len(row)

    return df.style.apply(row_style, axis=1)


# -------------------------------
# Page setup
# -------------------------------
st.set_page_config(page_title="Dropship Hub", layout="wide")

# -------------------------------
# Early Access Gate (Step 6D)
# -------------------------------
ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")

st.title("Dropship Hub — Early Access")
st.caption("Drop ship made easy — exceptions, follow-ups, and visibility in one hub.")

code = st.text_input("Enter early access code", type="password")

if code != ACCESS_CODE:
    st.info("This app is currently in early access. Enter your code to continue.")
    st.stop()

# -------------------------------
# Paths
# -------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# -------------------------------
# Onboarding checklist
# -------------------------------
st.divider()
with st.expander("Onboarding checklist", expanded=True):
    st.markdown(
        """
1. Click **Try demo data** to see the workflow instantly  
2. Upload **Orders CSV** (Shopify export)  
3. Upload **Shipments CSV** (supplier / agent export)  
4. (Optional) Upload **Tracking CSV**  
5. Review **Exceptions** and use **Supplier Follow-ups** to message suppliers  
        """.strip()
    )

# -------------------------------
# Demo Mode
# -------------------------------
st.subheader("Start here")
use_demo = st.button("Try demo data (no uploads)")

raw_orders = None
raw_shipments = None
raw_tracking = None

if use_demo:
    try:
        raw_orders = pd.read_csv(DATA_DIR / "raw_orders.csv")
        raw_shipments = pd.read_csv(DATA_DIR / "raw_shipments.csv")
        raw_tracking = pd.read_csv(DATA_DIR / "raw_tracking.csv")
        st.success("Demo data loaded ✅")
    except Exception as e:
        st.error("Couldn't load demo data. Make sure data/raw_orders.csv, raw_shipments.csv, raw_tracking.csv exist.")
        st.code(str(e))
        st.stop()

# -------------------------------
# Upload section
# -------------------------------
st.divider()
st.subheader("Upload your data")

col1, col2, col3 = st.columns(3)
with col1:
    f_orders = st.file_uploader("Orders CSV (Shopify export or generic)", type=["csv"])
with col2:
    f_shipments = st.file_uploader("Shipments CSV (supplier export)", type=["csv"])
with col3:
    f_tracking = st.file_uploader("Tracking CSV (optional)", type=["csv"])

# -------------------------------
# Template downloads
# -------------------------------
st.subheader("Download templates")

shipments_template = pd.DataFrame(
    columns=[
        "Supplier",
        "Supplier Order ID",
        "Order ID",
        "SKU",
        "Quantity",
        "Ship Date",
        "Carrier",
        "Tracking",
        "From Country",
        "To Country",
    ]
)

tracking_template = pd.DataFrame(
    columns=[
        "Carrier",
        "Tracking Number",
        "Order ID",
        "Supplier Order ID",
        "Status",
        "Last Update",
        "Delivered At",
        "Exception",
    ]
)

suppliers_template = pd.DataFrame(
    columns=["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"]
)

t1, t2, t3 = st.columns(3)
with t1:
    st.download_button(
        "Shipments template CSV",
        data=shipments_template.to_csv(index=False).encode("utf-8"),
        file_name="shipments_template.csv",
        mime="text/csv",
    )
with t2:
    st.download_button(
        "Tracking template CSV",
        data=tracking_template.to_csv(index=False).encode("utf-8"),
        file_name="tracking_template.csv",
        mime="text/csv",
    )
with t3:
    st.download_button(
        "Suppliers template CSV",
        data=suppliers_template.to_csv(index=False).encode("utf-8"),
        file_name="suppliers_template.csv",
        mime="text/csv",
    )

# -------------------------------
# Sidebar: tenant + defaults
# -------------------------------
with st.sidebar:
    st.header("Tenant")
    account_id = st.text_input("account_id", value="demo_account")
    store_id = st.text_input("store_id", value="demo_store")
    platform_hint = st.selectbox("platform hint", ["shopify", "amazon", "etsy", "other"], index=0)

    st.divider()
    st.header("Defaults")
    default_currency = st.text_input("Default currency", value="USD")
    default_promised_ship_days = st.number_input(
        "Default promised ship days (SLA)",
        min_value=1,
        max_value=30,
        value=3,
    )

    st.divider()
    st.caption("Tip: Click demo to see the workflow before uploading files.")

# -------------------------------
# Run pipeline: demo OR uploads
# -------------------------------
has_uploads = (f_orders is not None) and (f_shipments is not None)

if not (use_demo or has_uploads):
    st.info("Upload Orders + Shipments, or click **Try demo data** to begin.")
    st.stop()

# Load uploads if not demo
if not use_demo:
    try:
        raw_orders = pd.read_csv(f_orders)
        raw_shipments = pd.read_csv(f_shipments)
        raw_tracking = pd.read_csv(f_tracking) if f_tracking else pd.DataFrame()
    except Exception as e:
        st.error("Failed to read one of your CSV uploads.")
        st.code(str(e))
        st.stop()

# -------------------------------
# Normalize
# -------------------------------
st.divider()
st.subheader("Data checks")

orders, meta_o = normalize_orders(
    raw_orders,
    account_id=account_id,
    store_id=store_id,
    platform_hint=platform_hint,
    default_currency=default_currency,
    default_promised_ship_days=int(default_promised_ship_days),
)
shipments, meta_s = normalize_shipments(raw_shipments, account_id=account_id, store_id=store_id)

tracking = pd.DataFrame()
meta_t = {"validation_errors": []}
if raw_tracking is not None and isinstance(raw_tracking, pd.DataFrame) and not raw_tracking.empty:
    tracking, meta_t = normalize_tracking(raw_tracking, account_id=account_id, store_id=store_id)

errs = meta_o.get("validation_errors", []) + meta_s.get("validation_errors", []) + meta_t.get("validation_errors", [])

if errs:
    st.warning("We found some schema issues. You can still proceed, but fixing these improves accuracy:")
    for e in errs:
        st.write("- ", e)
else:
    st.success("Looks good ✅")

# -------------------------------
# Reconcile
# -------------------------------
st.divider()
st.subheader("Running reconciliation")

try:
    line_status_df, exceptions, followups, order_rollup, kpis = reconcile_all(orders, shipments, tracking)
except Exception as e:
    st.error("Reconciliation failed. This usually means a required column is missing after normalization.")
    st.code(str(e))
    st.stop()

# AI explanations (safe fallback if no API key)
try:
    exceptions = enhance_explanations(exceptions)
except Exception:
    pass  # never crash because AI failed

# -------------------------------
# Dashboard KPIs
# -------------------------------
st.divider()
st.subheader("Dashboard")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Order lines", int(kpis.get("total_order_lines", 0)))
k2.metric("% Shipped/Delivered", f"{kpis.get('pct_shipped_or_delivered', 0)}%")
k3.metric("% Delivered", f"{kpis.get('pct_delivered', 0)}%")
k4.metric("% Unshipped", f"{kpis.get('pct_unshipped', 0)}%")
k5.metric("% Late Unshipped", f"{kpis.get('pct_late_unshipped', 0)}%")

# -------------------------------
# "What am I looking at?" panel
# -------------------------------
st.divider()
with st.expander("What am I looking at?", expanded=True):
    st.markdown(
        """
### How to use this app (daily workflow)

**1) Start with the Exceptions Queue**
- These are the **order lines (SKU-level)** that need attention.
- Common reasons:
  - Orders are **late and unshipped**
  - **Partial shipments**
  - **Missing tracking**
  - **Carrier exceptions**

**2) Use Supplier Follow-ups**
- Copy/paste the email text to request **tracking or an updated ship date**.
- This is the fastest way to reduce customer complaints.

**3) Check Order Rollup**
- One row per order so you can quickly see **overall status**.
- Use this view for customer support updates.

**Tip:** Click **Try demo data** to understand the flow in 30 seconds before uploading your own files.
        """.strip()
    )

# -------------------------------
# Exceptions Queue
# -------------------------------
st.divider()
st.subheader("Exceptions Queue (Action this first)")

if exceptions is None or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
    # Add urgency + sort (NEW)
    exceptions = add_urgency_column(exceptions)

    fcol1, fcol2, fcol3, fcol4 = st.columns(4)

    with fcol1:
        issue_types = sorted(exceptions["issue_type"].dropna().unique().tolist()) if "issue_type" in exceptions.columns else []
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types)

    with fcol2:
        countries = sorted(
            [c for c in exceptions.get("customer_country", pd.Series([], dtype="object")).dropna().unique().tolist()
             if str(c).strip() != ""]
        )
        country_filter = st.multiselect("Customer country", countries, default=countries)

    with fcol3:
        suppliers = sorted(
            [s for s in exceptions.get("supplier_name", pd.Series([], dtype="object")).dropna().unique().tolist()
             if str(s).strip() != ""]
        )
        supplier_filter = st.multiselect("Supplier", suppliers, default=suppliers)

    # NEW: urgency filter
    with fcol4:
        urgencies = ["Critical", "High", "Medium", "Low"]
        urgency_filter = st.multiselect("Urgency", urgencies, default=urgencies)

    filtered = exceptions.copy()
    if issue_filter and "issue_type" in filtered.columns:
        filtered = filtered[filtered["issue_type"].isin(issue_filter)]
    if country_filter and "customer_country" in filtered.columns:
        filtered = filtered[filtered["customer_country"].isin(country_filter)]
    if supplier_filter and "supplier_name" in filtered.columns:
        filtered = filtered[filtered["supplier_name"].isin(supplier_filter)]
    if urgency_filter and "Urgency" in filtered.columns:
        filtered = filtered[filtered["Urgency"].isin(urgency_filter)]

    # NEW: summary counts
    if "Urgency" in filtered.columns:
        counts = filtered["Urgency"].value_counts().to_dict()
        st.write(
            f"**Critical:** {counts.get('Critical', 0)} | "
            f"**High:** {counts.get('High', 0)} | "
            f"**Medium:** {counts.get('Medium', 0)} | "
            f"**Low:** {counts.get('Low', 0)}"
        )

    preferred_cols = [
        "Urgency",
        "order_id",
        "sku",
        "issue_type",
        "customer_country",
        "supplier_name",
        "quantity_ordered",
        "quantity_shipped",
        "line_status",
        "explanation",
        "next_action",
        "customer_risk",
    ]
    show_cols = [c for c in preferred_cols if c in filtered.columns]

    # NEW: sort by urgency first
    if "Urgency" in filtered.columns:
        filtered = filtered.sort_values(["Urgency"], ascending=True)

    st.dataframe(style_exceptions_table(filtered[show_cols]), use_container_width=True, height=420)

    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
    )

# -------------------------------
# Supplier Follow-ups (with Copy buttons)
# -------------------------------
st.divider()
st.subheader("Supplier Follow-ups (Copy/Paste Ready)")

if followups is None or followups.empty:
    st.info("No follow-ups needed.")
else:
    summary_cols = [
        c for c in ["supplier_name", "supplier_email", "urgency", "item_count", "order_ids"]
        if c in followups.columns
    ]
    if summary_cols:
        st.dataframe(followups[summary_cols], use_container_width=True, height=220)
    else:
        st.dataframe(followups, use_container_width=True, height=220)

    st.download_button(
        "Download Supplier Follow-ups CSV",
        data=followups.to_csv(index=False).encode("utf-8"),
        file_name="supplier_followups.csv",
        mime="text/csv",
    )

    # Email preview + ONE-CLICK COPY
    if "supplier_name" in followups.columns and "body" in followups.columns and len(followups) > 0:
        st.divider()
        st.markdown("### Email preview (select a supplier)")

        chosen = st.selectbox(
            "Supplier",
            followups["supplier_name"].tolist(),
            key="supplier_email_preview_select",
        )
        row = followups[followups["supplier_name"] == chosen].iloc[0]

        subject = (
            row.get("subject", "Action required: outstanding shipments")
            if "subject" in followups.columns
            else "Action required: outstanding shipments"
        )
        body = row.get("body", "")

        c1, c2 = st.columns(2)
        with c1:
            copy_button(subject, "Copy subject", key=f"copy_subject_{chosen}")
        with c2:
            copy_button(body, "Copy body", key=f"copy_body_{chosen}")

        st.text_input("Subject", value=subject, key="email_subject_preview")
        st.text_area("Body", value=body, height=260, key="email_body_preview")

        st.download_button(
            "Download email as .txt",
            data=(f"Subject: {subject}\n\n{body}").encode("utf-8"),
            file_name=f"supplier_email_{chosen}.txt".replace(" ", "_").lower(),
            mime="text/plain",
        )

# -------------------------------
# Order-level rollup
# -------------------------------
st.divider()
st.subheader("Order-Level Rollup (One row per order)")

st.dataframe(order_rollup, use_container_width=True, height=320)
st.download_button(
    "Download Order Rollup CSV",
    data=order_rollup.to_csv(index=False).encode("utf-8"),
    file_name="order_rollup.csv",
    mime="text/csv",
)

# -------------------------------
# All order lines
# -------------------------------
st.divider()
st.subheader("All Order Lines (Normalized + Status)")

st.dataframe(line_status_df, use_container_width=True, height=380)
st.download_button(
    "Download Line Status CSV",
    data=line_status_df.to_csv(index=False).encode("utf-8"),
    file_name="order_line_status.csv",
    mime="text/csv",
)

st.caption("MVP note: This version uses CSV uploads. Integrations + automation can be added after early-user feedback.")
