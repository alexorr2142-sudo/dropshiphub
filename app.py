# app.py
import os
from pathlib import Path

import pandas as pd
import streamlit as st

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

# -------------------------------
# Page setup
# -------------------------------
st.set_page_config(page_title="Dropship Hub", layout="wide")

# -------------------------------
# Early Access Gate (Step 6D)
# -------------------------------
ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")

st.title("Dropship Hub — Early Access")
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
# Onboarding checklist (Step 6F-ish)
# -------------------------------
st.divider()
with st.expander("Onboarding checklist", expanded=True):
    st.markdown(
        """
1. Click **Try demo data** to see the workflow instantly  
2. Upload **Orders CSV** (Shopify export)  
3. Upload **Shipments CSV** (supplier / agent export)  
4. (Optional) Upload **Tracking CSV**  
5. Review **Exceptions** and download **Supplier Follow-ups**  
        """.strip()
    )

# -------------------------------
# Demo Mode (Step 2)
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
# Template downloads (reduces drop-off)
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
    # Never crash the app because AI failed
    pass

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
# Exceptions Queue
# -------------------------------
st.divider()
st.subheader("Exceptions Queue (Action this first)")

if exceptions is None or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
    fcol1, fcol2, fcol3 = st.columns(3)

    with fcol1:
        issue_types = sorted(exceptions["issue_type"].dropna().unique().tolist()) if "issue_type" in exceptions.columns else []
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types)

    with fcol2:
        countries = sorted([c for c in exceptions.get("customer_country", pd.Series([])).dropna().unique().tolist() if str(c).strip() != ""])
        country_filter = st.multiselect("Customer country", countries, default=countries)

    with fcol3:
        suppliers = sorted([s for s in exceptions.get("supplier_name", pd.Series([])).dropna().unique().tolist() if str(s).strip() != ""])
        supplier_filter = st.multiselect("Supplier", suppliers, default=suppliers)

    filtered = exceptions.copy()
    if issue_filter and "issue_type" in filtered.columns:
        filtered = filtered[filtered["issue_type"].isin(issue_filter)]
    if country_filter and "customer_country" in filtered.columns:
        filtered = filtered[filtered["customer_country"].isin(country_filter)]
    if supplier_filter and "supplier_name" in filtered.columns:
        filtered = filtered[filtered["supplier_name"].isin(supplier_filter)]

    preferred_cols = [
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
    st.dataframe(filtered[show_cols], use_container_width=True, height=420)

    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
    )

# -------------------------------
# Supplier Follow-ups
# -------------------------------
st.divider()
st.subheader("Supplier Follow-ups (Copy/Paste Ready)")

if followups is None or followups.empty:
    st.info("No follow-ups needed.")
else:
    summary_cols = [c for c in ["supplier_name", "supplier_email", "urgency", "item_count", "order_ids"] if c in followups.columns]
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

    # Preview one supplier email (if available)
    if "supplier_name" in followups.columns and "body" in followups.columns and len(followups) > 0:
        chosen = st.selectbox("Preview email for supplier", followups["supplier_name"].tolist())
        row = followups[followups["supplier_name"] == chosen].iloc[0]
        if "subject" in followups.columns:
            st.text_input("Subject", value=row.get("subject", ""))
        st.text_area("Body", value=row.get("body", ""), height=260)

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
