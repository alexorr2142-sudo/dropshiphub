# app.py
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
from datetime import datetime

import pandas as pd
import streamlit as st

# --- Local modules (your repo files) ---
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

from core.paths import init_paths
from core.styling import add_urgency_column, style_exceptions_table, copy_button
from core.scorecards import build_supplier_scorecard_from_run
from core.ops_pack import make_daily_ops_pack_bytes
from core.suppliers import enrich_followups_with_suppliers, add_missing_supplier_contact_exceptions
from core.actions import build_daily_action_list
from core.customer_impact import build_customer_impact_view

from ui.auth import early_access_gate, require_email_access_gate
from ui.sidebar import render_sidebar_context
from ui.demo import ensure_demo_state, render_demo_editor, get_active_raw_inputs
from ui.templates import render_template_downloads
from ui.workspaces_ui import render_workspaces_sidebar_and_maybe_override_outputs
from ui.actions_ui import render_daily_action_list
from ui.customer_impact_ui import render_customer_impact_view


# -------------------------------
# Page setup
# -------------------------------
st.set_page_config(page_title="Dropship Hub", layout="wide")


# -------------------------------
# Startup sanity check (prevents redacted ModuleNotFoundError)
# -------------------------------
def _startup_sanity_check():
    required = [
        "core/__init__.py",
        "core/paths.py",
        "core/styling.py",
        "core/ops_pack.py",
        "core/workspaces.py",
        "core/suppliers.py",
        "core/scorecards.py",
        "core/actions.py",
        "core/customer_impact.py",
        "ui/__init__.py",
        "ui/auth.py",
        "ui/demo.py",
        "ui/templates.py",
        "ui/sidebar.py",
        "ui/workspaces_ui.py",
        "ui/actions_ui.py",
        "ui/customer_impact_ui.py",
    ]
    missing = [rel for rel in required if not (ROOT / rel).exists()]
    if missing:
        st.error("Missing required app files (repo structure issue).")
        st.code("\n".join(missing))
        st.stop()


_startup_sanity_check()


# -------------------------------
# Helpers: detect when inputs change (invalidate cached results)
# -------------------------------
def _df_signature(df: pd.DataFrame) -> str:
    """
    Cheap-ish signature so we can detect when demo edits/uploads change inputs.
    Avoids hashing the full dataframe (which can be slow).
    """
    if df is None:
        return "none"
    if not isinstance(df, pd.DataFrame):
        return f"not_df:{type(df)}"
    shape = df.shape
    cols = ",".join(map(str, df.columns.tolist()))
    sample = df.head(50).copy()
    tail = df.tail(50).copy()
    try:
        h1 = pd.util.hash_pandas_object(sample, index=True).sum()
        h2 = pd.util.hash_pandas_object(tail, index=True).sum()
        return f"{shape}|{cols}|{int(h1)}|{int(h2)}"
    except Exception:
        return f"{shape}|{cols}"


def _inputs_signature(raw_orders: pd.DataFrame, raw_shipments: pd.DataFrame, raw_tracking: pd.DataFrame, demo_mode: bool) -> str:
    return "||".join(
        [
            f"demo={int(bool(demo_mode))}",
            _df_signature(raw_orders),
            _df_signature(raw_shipments),
            _df_signature(raw_tracking),
        ]
    )


def _invalidate_results_if_inputs_changed(sig_now: str):
    prev = st.session_state.get("inputs_sig")
    if prev is None:
        st.session_state["inputs_sig"] = sig_now
        return

    if sig_now != prev:
        st.session_state["inputs_sig"] = sig_now
        st.session_state["run_requested"] = False
        st.session_state.pop("results_bundle", None)


# -------------------------------
# Early Access Gate
# -------------------------------
ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")
early_access_gate(ACCESS_CODE)
require_email_access_gate()

# -------------------------------
# Paths
# -------------------------------
BASE_DIR, DATA_DIR, WORKSPACES_DIR, SUPPLIERS_DIR = init_paths(Path(__file__).parent)

# -------------------------------
# Sidebar
# -------------------------------
ctx = render_sidebar_context(
    data_dir=DATA_DIR,
    workspaces_dir=WORKSPACES_DIR,
    suppliers_dir=SUPPLIERS_DIR,
)

account_id = ctx["account_id"]
store_id = ctx["store_id"]
platform_hint = ctx["platform_hint"]
default_currency = ctx["default_currency"]
default_promised_ship_days = ctx["default_promised_ship_days"]
suppliers_df = ctx["suppliers_df"]
demo_mode = ctx["demo_mode"]

# -------------------------------
# Onboarding checklist
# -------------------------------
st.divider()
with st.expander("Onboarding checklist", expanded=True):
    st.markdown(
        """
1. Turn on **Demo Mode (Sticky)** to see the workflow instantly  
2. Upload **Orders CSV** (Shopify export)  
3. Upload **Shipments CSV** (supplier / agent export)  
4. (Optional) Upload **Tracking CSV**  
5. Click **Run reconciliation** (this refreshes outputs)  
6. Review **Daily Action List** (what to do today)  
7. Review **Customer Impact View** (draft customer messages)  
8. Review **Exceptions** and use **Supplier Follow-ups** to message suppliers  
9. (Optional) Upload **suppliers.csv** in the sidebar to auto-fill supplier emails  
        """.strip()
    )

# -------------------------------
# Demo Mode (sticky)
# -------------------------------
ensure_demo_state(DATA_DIR)
st.subheader("Start here")
render_demo_editor()

# -------------------------------
# Upload section
# -------------------------------
st.divider()
st.subheader("Upload your data")

col1, col2, col3 = st.columns(3)
with col1:
    f_orders = st.file_uploader("Orders CSV (Shopify export or generic)", type=["csv"], key="u_orders_main")
with col2:
    f_shipments = st.file_uploader("Shipments CSV (supplier export)", type=["csv"], key="u_shipments_main")
with col3:
    f_tracking = st.file_uploader("Tracking CSV (optional)", type=["csv"], key="u_tracking_main")

# -------------------------------
# Template downloads
# -------------------------------
render_template_downloads()

# -------------------------------
# Choose raw inputs (demo OR uploads)
# -------------------------------
raw_orders, raw_shipments, raw_tracking = get_active_raw_inputs(
    demo_mode=demo_mode,
    data_dir=DATA_DIR,
    f_orders=f_orders,
    f_shipments=f_shipments,
    f_tracking=f_tracking,
)

# -------------------------------
# High impact change: "Run reconciliation" control
# -------------------------------
if "run_requested" not in st.session_state:
    st.session_state["run_requested"] = False

if "results_bundle" not in st.session_state:
    st.session_state["results_bundle"] = None

sig_now = _inputs_signature(raw_orders, raw_shipments, raw_tracking, demo_mode=demo_mode)
_invalidate_results_if_inputs_changed(sig_now)

st.divider()
st.subheader("Run")

r1, r2, r3 = st.columns([1, 1, 3])
with r1:
    if st.button("▶ Run reconciliation", use_container_width=True, key="btn_run_recon"):
        st.session_state["run_requested"] = True
        st.session_state["results_bundle"] = None

with r2:
    if st.button("⟲ Reset results", use_container_width=True, key="btn_reset_results"):
        st.session_state["run_requested"] = False
        st.session_state["results_bundle"] = None
        st.rerun()

with r3:
    st.caption("Tip: Edit demo tables or upload files above, then click **Run reconciliation** to refresh outputs.")

if not st.session_state["run_requested"]:
    st.info("Make changes above, then click **Run reconciliation** to generate outputs.")
    st.stop()

# -------------------------------
# Compute pipeline ONCE per run request (cached in session_state)
# -------------------------------
if st.session_state["results_bundle"] is None:
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

    # AI explanations (safe fallback)
    try:
        exceptions = enhance_explanations(exceptions)
    except Exception:
        pass

    # Enrich followups with CRM + add missing supplier contact exceptions
    followups = enrich_followups_with_suppliers(followups, suppliers_df)
    exceptions = add_missing_supplier_contact_exceptions(exceptions, followups)

    # Add urgency once
    if exceptions is not None and not exceptions.empty and "Urgency" not in exceptions.columns:
        exceptions = add_urgency_column(exceptions)

    # Scorecard once
    scorecard = build_supplier_scorecard_from_run(line_status_df, exceptions)

    # Ops pack once
    pack_date = datetime.now().strftime("%Y%m%d")
    pack_name = f"daily_ops_pack_{pack_date}.zip"
    ops_pack_bytes = make_daily_ops_pack_bytes(
        exceptions=exceptions if exceptions is not None else pd.DataFrame(),
        followups=followups if followups is not None else pd.DataFrame(),
        order_rollup=order_rollup if order_rollup is not None else pd.DataFrame(),
        line_status_df=line_status_df if line_status_df is not None else pd.DataFrame(),
        kpis=kpis if isinstance(kpis, dict) else {},
        supplier_scorecards=scorecard,
    )

    st.session_state["results_bundle"] = {
        "orders": orders,
        "shipments": shipments,
        "tracking": tracking,
        "line_status_df": line_status_df,
        "exceptions": exceptions,
        "followups": followups,
        "order_rollup": order_rollup,
        "kpis": kpis,
        "scorecard": scorecard,
        "ops_pack_bytes": ops_pack_bytes,
        "pack_name": pack_name,
    }

bundle = st.session_state["results_bundle"]
orders = bundle["orders"]
shipments = bundle["shipments"]
tracking = bundle["tracking"]
line_status_df = bundle["line_status_df"]
exceptions = bundle["exceptions"]
followups = bundle["followups"]
order_rollup = bundle["order_rollup"]
kpis = bundle["kpis"]
scorecard = bundle["scorecard"]
ops_pack_bytes = bundle["ops_pack_bytes"]
pack_name = bundle["pack_name"]

# -------------------------------
# Workspaces UI (Save/Load/History/Delete) + optional override if loaded
# -------------------------------
exceptions, followups, order_rollup, line_status_df, suppliers_df = render_workspaces_sidebar_and_maybe_override_outputs(
    workspaces_dir=WORKSPACES_DIR,
    account_id=account_id,
    store_id=store_id,
    platform_hint=platform_hint,
    orders=orders,
    shipments=shipments,
    tracking=tracking,
    exceptions=exceptions,
    followups=followups,
    order_rollup=order_rollup,
    line_status_df=line_status_df,
    kpis=kpis,
    suppliers_df=suppliers_df,
)

# If saved run loaded, ensure urgency/scorecard/ops pack match loaded outputs
if exceptions is not None and not exceptions.empty and "Urgency" not in exceptions.columns:
    exceptions = add_urgency_column(exceptions)

scorecard = build_supplier_scorecard_from_run(line_status_df, exceptions)
ops_pack_bytes = make_daily_ops_pack_bytes(
    exceptions=exceptions if exceptions is not None else pd.DataFrame(),
    followups=followups if followups is not None else pd.DataFrame(),
    order_rollup=order_rollup if order_rollup is not None else pd.DataFrame(),
    line_status_df=line_status_df if line_status_df is not None else pd.DataFrame(),
    kpis=kpis if isinstance(kpis, dict) else {},
    supplier_scorecards=scorecard,
)

# -------------------------------
# Sidebar: Ops Pack download
# -------------------------------
with st.sidebar:
    st.divider()
    st.header("Daily Ops Pack")
    st.download_button(
        "⬇️ Download Daily Ops Pack ZIP",
        data=ops_pack_bytes,
        file_name=pack_name,
        mime="application/zip",
        use_container_width=True,
        key="btn_daily_ops_pack_sidebar",
    )
    st.caption("Exports: exceptions, followups, rollup, line status, KPIs, scorecards (if available).")

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
# Daily Action List (Feature #1)
# -------------------------------
actions = build_daily_action_list(exceptions=exceptions, followups=followups, max_items=10)
from ui.actions_ui import render_daily_action_list  # safe import even if reloaded
render_daily_action_list(actions)

# -------------------------------
# Customer Impact View (Feature #2)
# -------------------------------
customer_impact = build_customer_impact_view(exceptions=exceptions, max_items=50)
render_customer_impact_view(customer_impact)

# -------------------------------
# Exceptions Queue
# -------------------------------
st.divider()
st.subheader("Exceptions Queue (Action this first)")

if exceptions is None or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
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

    sort_cols = [c for c in ["Urgency", "order_id"] if c in filtered.columns]
    if sort_cols:
        filtered = filtered.sort_values(sort_cols, ascending=True)

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

    if "supplier_name" in followups.columns and "body" in followups.columns and len(followups) > 0:
        st.divider()
        st.markdown("### Email preview (select a supplier)")

        chosen = st.selectbox(
            "Supplier",
            followups["supplier_name"].tolist(),
            key="supplier_email_preview_select",
        )
        row = followups[followups["supplier_name"] == chosen].iloc[0]

        supplier_email = row.get("supplier_email", "") if "supplier_email" in followups.columns else ""
        subject = row.get("subject", "Action required: outstanding shipments") if "subject" in followups.columns else "Action required: outstanding shipments"
        body = row.get("body", "")

        c1, c2, c3 = st.columns(3)
        with c1:
            copy_button(supplier_email, "Copy supplier email", key=f"copy_supplier_email_{chosen}")
        with c2:
            copy_button(subject, "Copy subject", key=f"copy_subject_{chosen}")
        with c3:
            copy_button(body, "Copy body", key=f"copy_body_{chosen}")

        st.text_input("To (supplier email)", value=supplier_email, key="email_to_preview")
        st.text_input("Subject", value=subject, key="email_subject_preview")
        st.text_area("Body", value=body, height=260, key="email_body_preview")

        st.download_button(
            "Download email as .txt",
            data=(f"To: {supplier_email}\nSubject: {subject}\n\n{body}").encode("utf-8"),
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
