import streamlit as st
import os
from pathlib import Path
import pandas as pd

from normalize import normalize_orders, normalize_shipments, normalize_tracking
from reconcile import reconcile_all
from explain import enhance_explanations

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
# Demo Mode (Step 2)
# -------------------------------
st.divider()
st.subheader("Start here")

use_demo = st.button("Try demo data (no uploads)")

raw_orders = None
raw_shipments = None
raw_tracking = None

if use_demo:
    raw_orders = pd.read_csv(DATA_DIR / "raw_orders.csv")
    raw_shipments = pd.read_csv(DATA_DIR / "raw_shipments.csv")
    raw_tracking = pd.read_csv(DATA_DIR / "raw_tracking.csv")
    st.success("Demo data loaded ✅")

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

# Optional: tenant + defaults
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
        value=3
    )

    st.divider()
    st.caption("Tip: If your Shopify export varies, we still try to auto-detect it.")

# -------------------------------
# Run pipeline: demo OR uploads
# -------------------------------
has_uploads = (f_orders is not None) and (f_shipments is not None)

if use_demo or has_uploads:
    if not use_demo:
        raw_orders = pd.read_csv(f_orders)
        raw_shipments = pd.read_csv(f_shipments)
        raw_tracking = pd.read_csv(f_tracking) if f_tracking else pd.DataFrame()

    # Normalize
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
    if raw_tracking is not None and not raw_tracking.empty:
        tracking, meta_t = normalize_tracking(raw_tracking, account_id=account_id, store_id=store_id)

    # Show schema warnings (don’t block)
    st.divider()
    st.subheader("Data checks")

    errs = meta_o.get("validation_errors", []) + meta_s.get("validation_errors", []) + meta_t.get("validation_errors", [])
    if errs:
        st.warning("We found some schema issues. You can still proceed, but fixing these improves accuracy:")
        for e in errs:
            st.write("- ", e)
    else:
        st.success("Looks good — running reconciliation ✅")

    # Reconcile
    line_status_df, exceptions, followups, order_rollup, kpis = reconcile_all(orders, shipments, tracking)

    # AI explanations (safe fallback if no API key)
    exceptions = enhance_explanations(exceptions)

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
            issue_filter = st.multiselect(
                "Issue types",
                sorted(exceptions["issue_type"].dropna().unique().tolist()),
                default=sorted(exceptions["issue_type"].dropna().unique().tolist()),
            )
        with fcol2:
            country_filter = st.multiselect(
                "Customer country",
                sorted([c for c in exceptions["customer_country"].dropna().unique().tolist() if c]),
                default=sorted([c for c in exceptions["customer_country"].dropna().unique().tolist() if c]),
            )
        with fcol3:
            supplier_filter = st.multiselect(
                "Supplier",
                sorted([s for s in exceptions["supplier_name"].dropna().unique().tolist() if s]),
                default=sorted([s for s in exceptions["supplier_name"].dropna().unique().tolist() if s]),
            )

        filtered = exceptions.copy()
        if issue_filter:
            filtered = filtered[filtered["issue_type"].isin(issue_filter)]
        if country_filter:
            filtered = filtered[filtered["customer_country"].isin(country_filter)]
        if supplier_filter:
            filtered = filtered[filtered["supplier_name"].isin(supplier_filter)]

        # Show the most useful columns first (keep it readable)
        preferred_cols = [
            "order_id", "sku", "issue_type",
            "customer_country", "supplier_name",
            "quantity_ordered", "quantity_shipped",
            "line_status",
            "explanation", "next_action", "customer_risk",
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
        # If your Step 3 followups are batched, this will show them nicely
        cols = [c for c in ["supplier_name", "supplier_email", "urgency", "item_count", "subject", "body"] if c in followups.columns]
        st.dataframe(followups[cols], use_container_width=True, height=320)

        st.download_button(
            "Download Supplier Follow-ups CSV",
            data=followups.to_csv(index=False).encode("utf-8"),
            file_name="supplier_followups.csv",
            mime="text/csv",
        )

        # Optional: preview one supplier email
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

else:
    st.divider()
    st.subheader("Manage your dropshipping operation from one hub")
    st.write("Upload Orders + Shipments, or click **Try demo data** to see how it works.")
