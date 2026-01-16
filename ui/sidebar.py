# app.py
from __future__ import annotations

import inspect
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ============================================================
# Local pipeline modules (required)
# ============================================================
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

# ============================================================
# Core modules (your repo)
# ============================================================
from core.ops_pack import make_daily_ops_pack_bytes
from core.scorecards import build_supplier_scorecard_from_run, load_recent_scorecard_history
from core.styling import add_urgency_column, style_exceptions_table, copy_button
from core.suppliers import enrich_followups_with_suppliers, add_missing_supplier_contact_exceptions
from core.workspaces import workspace_root

# Optional core imports
IssueTrackerStore = None
CONTACT_STATUSES = ["Not Contacted", "Contacted", "Waiting", "Escalated", "Resolved"]
mailto_link = None
build_customer_impact_view = None
build_daily_action_list = None

try:
    from core.issue_tracker import IssueTrackerStore, CONTACT_STATUSES  # type: ignore
except Exception:
    IssueTrackerStore = None

try:
    from core.email_utils import mailto_link  # type: ignore
except Exception:
    mailto_link = None

try:
    from core.customer_impact import build_customer_impact_view  # type: ignore
except Exception:
    build_customer_impact_view = None

try:
    from core.actions import build_daily_action_list  # type: ignore
except Exception:
    build_daily_action_list = None

# ============================================================
# UI modules (HARD REQUIRE sidebar to avoid duplicate keys)
# ============================================================
try:
    from ui.sidebar import render_sidebar_context  # type: ignore
except Exception as e:
    st.set_page_config(page_title="Dropship Hub", layout="wide")
    st.title("Dropship Hub")
    st.error("Import error: ui/sidebar.py is missing or has an error.")
    st.code(str(e))
    st.stop()

# Demo
ensure_demo_state = None
render_demo_editor = None
get_active_raw_inputs = None
try:
    from ui.demo import ensure_demo_state, render_demo_editor, get_active_raw_inputs  # type: ignore
except Exception:
    ensure_demo_state = None
    render_demo_editor = None
    get_active_raw_inputs = None

# Upload UI
render_upload_section = None
try:
    from ui.upload_ui import render_upload_section  # type: ignore
except Exception:
    render_upload_section = None

# Onboarding UI
render_onboarding_checklist = None
try:
    from ui.onboarding_ui import render_onboarding_checklist  # type: ignore
except Exception:
    render_onboarding_checklist = None

# Templates UI
render_template_downloads = None
try:
    from ui.templates import render_template_downloads  # type: ignore
except Exception:
    render_template_downloads = None

# Diagnostics UI
render_diagnostics = None
try:
    from ui.diagnostics_ui import render_diagnostics  # type: ignore
except Exception:
    render_diagnostics = None

# Triage UI
render_ops_triage = None
try:
    from ui.triage_ui import render_ops_triage  # type: ignore
except Exception:
    render_ops_triage = None

# Workspaces UI
render_workspaces_sidebar_and_maybe_override_outputs = None
try:
    from ui.workspaces_ui import render_workspaces_sidebar_and_maybe_override_outputs  # type: ignore
except Exception:
    render_workspaces_sidebar_and_maybe_override_outputs = None

# Issue tracker UI
derive_followups_open = None
enrich_followups_with_contact_fields = None
render_issue_tracker_maintenance = None
try:
    from ui.issue_tracker_ui import (  # type: ignore
        derive_followups_open,
        enrich_followups_with_contact_fields,
        render_issue_tracker_maintenance,
    )
except Exception:
    derive_followups_open = None
    enrich_followups_with_contact_fields = None
    render_issue_tracker_maintenance = None

# SLA escalations UI
render_sla_escalations = None
try:
    from ui.sla_escalations_ui import render_sla_escalations  # type: ignore
except Exception:
    render_sla_escalations = None

# Customer comms UI
render_customer_comms_ui = None
try:
    from ui.customer_comms_ui import render_customer_comms_ui  # type: ignore
except Exception:
    render_customer_comms_ui = None

# Comms pack UI
render_comms_pack_download = None
try:
    from ui.comms_pack_ui import render_comms_pack_download  # type: ignore
except Exception:
    render_comms_pack_download = None

# KPI trends UI
render_kpi_trends = None
try:
    from ui.kpi_trends_ui import render_kpi_trends  # type: ignore
except Exception:
    render_kpi_trends = None

# Daily actions UI
render_daily_action_list = None
try:
    from ui.actions_ui import render_daily_action_list  # type: ignore
except Exception:
    render_daily_action_list = None


# ============================================================
# Helpers
# ============================================================
def call_with_accepted_kwargs(fn, **kwargs):
    sig = inspect.signature(fn)
    accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return fn(**accepted)


def _mailto_fallback(to: str, subject: str, body: str) -> str:
    from urllib.parse import quote
    return f"mailto:{quote(to or '')}?subject={quote(subject or '')}&body={quote(body or '')}"


# ============================================================
# Page setup
# ============================================================
st.set_page_config(page_title="Dropship Hub", layout="wide")


# ============================================================
# Paths
# ============================================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

WORKSPACES_DIR = DATA_DIR / "workspaces"
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

SUPPLIERS_DIR = DATA_DIR / "suppliers"
SUPPLIERS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Sidebar context (single source of truth)
# ============================================================
ctx = render_sidebar_context(DATA_DIR, WORKSPACES_DIR, SUPPLIERS_DIR)

account_id = ctx["account_id"]
store_id = ctx["store_id"]
platform_hint = ctx["platform_hint"]
default_currency = ctx["default_currency"]
default_promised_ship_days = int(ctx["default_promised_ship_days"])
suppliers_df = ctx.get("suppliers_df", pd.DataFrame())
demo_mode_active = bool(ctx.get("demo_mode", False))


# ============================================================
# Diagnostics
# ============================================================
diag = {
    "render_sla_escalations": render_sla_escalations is not None,
    "IssueTrackerStore": IssueTrackerStore is not None,
    "mailto_link": mailto_link is not None,
    "build_customer_impact_view": build_customer_impact_view is not None,
    "render_customer_comms_ui": render_customer_comms_ui is not None,
    "render_comms_pack_download": render_comms_pack_download is not None,
    "build_daily_action_list": build_daily_action_list is not None,
    "render_daily_action_list": render_daily_action_list is not None,
    "render_kpi_trends": render_kpi_trends is not None,
    "render_upload_section": render_upload_section is not None,
    "render_onboarding_checklist": render_onboarding_checklist is not None,
    "render_template_downloads": render_template_downloads is not None,
    "render_ops_triage": render_ops_triage is not None,
}
if callable(render_diagnostics):
    render_diagnostics(workspaces_dir=WORKSPACES_DIR, account_id=account_id, store_id=store_id, diag=diag, expanded=False)


# ============================================================
# Onboarding checklist
# ============================================================
if callable(render_onboarding_checklist):
    render_onboarding_checklist(expanded=True)


# ============================================================
# Start Here (Demo editor)
# ============================================================
st.subheader("Start here")
if callable(ensure_demo_state):
    ensure_demo_state(DATA_DIR)
if callable(render_demo_editor):
    render_demo_editor()
else:
    if demo_mode_active:
        st.info("Demo mode is ON but demo editor UI module is not available.")
    else:
        st.info("Turn on **Demo Mode (Sticky)** in the sidebar to play with demo data (edits persist).")


# ============================================================
# Upload UI
# ============================================================
st.divider()
uploads = None
if callable(render_upload_section):
    uploads = render_upload_section()
else:
    st.subheader("Upload your data")
    c1, c2, c3 = st.columns(3)
    with c1:
        f_orders = st.file_uploader("Orders CSV (Shopify export or generic)", type=["csv"], key="uploader_orders")
    with c2:
        f_shipments = st.file_uploader("Shipments CSV (supplier export)", type=["csv"], key="uploader_shipments")
    with c3:
        f_tracking = st.file_uploader("Tracking CSV (optional)", type=["csv"], key="uploader_tracking")
    uploads = type(
        "U",
        (),
        {
            "f_orders": f_orders,
            "f_shipments": f_shipments,
            "f_tracking": f_tracking,
            "has_uploads": (f_orders is not None and f_shipments is not None),
        },
    )


# ============================================================
# Templates
# ============================================================
if callable(render_template_downloads):
    render_template_downloads()


# ============================================================
# Resolve raw inputs (demo OR uploads)
# ============================================================
if callable(get_active_raw_inputs):
    raw_orders, raw_shipments, raw_tracking = get_active_raw_inputs(
        demo_mode_active,
        DATA_DIR,
        uploads.f_orders,
        uploads.f_shipments,
        uploads.f_tracking,
    )
else:
    if not (demo_mode_active or uploads.has_uploads):
        st.info("Upload Orders + Shipments, or turn on **Demo Mode (Sticky)** in the sidebar to begin.")
        st.stop()
    if demo_mode_active:
        raw_orders = st.session_state.get("demo_raw_orders", pd.DataFrame())
        raw_shipments = st.session_state.get("demo_raw_shipments", pd.DataFrame())
        raw_tracking = st.session_state.get("demo_raw_tracking", pd.DataFrame())
    else:
        raw_orders = pd.read_csv(uploads.f_orders)
        raw_shipments = pd.read_csv(uploads.f_shipments)
        raw_tracking = pd.read_csv(uploads.f_tracking) if uploads.f_tracking else pd.DataFrame()


# ============================================================
# Normalize
# ============================================================
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


# ============================================================
# Reconcile
# ============================================================
st.divider()
st.subheader("Running reconciliation")

line_status_df, exceptions, followups, order_rollup, kpis = reconcile_all(orders, shipments, tracking)

try:
    exceptions = enhance_explanations(exceptions)
except Exception:
    pass

followups = enrich_followups_with_suppliers(followups, suppliers_df)
exceptions = add_missing_supplier_contact_exceptions(exceptions, followups)

if exceptions is not None and not exceptions.empty and "Urgency" not in exceptions.columns:
    exceptions = add_urgency_column(exceptions)

scorecard = build_supplier_scorecard_from_run(line_status_df, exceptions)


# ============================================================
# SLA Escalations + followups_full/open
# ============================================================
followups_full = followups.copy() if isinstance(followups, pd.DataFrame) else pd.DataFrame()
followups_open = followups_full.copy()
escalations_df = pd.DataFrame()

if render_sla_escalations is not None:
    try:
        escalations_df, followups_full_from_ui, _open_from_ui = render_sla_escalations(
            line_status_df=line_status_df,
            followups=followups_full,
            promised_ship_days=int(default_promised_ship_days),
        )
        if isinstance(followups_full_from_ui, pd.DataFrame) and not followups_full_from_ui.empty:
            followups_full = followups_full_from_ui.copy()
    except Exception:
        pass

ws_root = workspace_root(WORKSPACES_DIR, account_id, store_id)
ws_root.mkdir(parents=True, exist_ok=True)
ISSUE_TRACKER_PATH = Path(ws_root) / "issue_tracker.json"

with st.sidebar:
    if callable(render_issue_tracker_maintenance) and (IssueTrackerStore is not None):
        render_issue_tracker_maintenance(ISSUE_TRACKER_PATH, default_prune_days=30)

if callable(derive_followups_open):
    followups_open = derive_followups_open(followups_full, ISSUE_TRACKER_PATH)
else:
    followups_open = followups_full.copy()

followups = followups_open


# ============================================================
# Customer impact
# ============================================================
customer_impact = pd.DataFrame()
if build_customer_impact_view is not None:
    try:
        customer_impact = build_customer_impact_view(exceptions=exceptions, max_items=50)
    except Exception:
        customer_impact = pd.DataFrame()


# ============================================================
# Daily Ops Pack ZIP
# ============================================================
pack_date = datetime.now().strftime("%Y%m%d")
pack_name = f"daily_ops_pack_{pack_date}.zip"

ops_pack_bytes = make_daily_ops_pack_bytes(
    exceptions=exceptions if exceptions is not None else pd.DataFrame(),
    followups=followups_open if followups_open is not None else pd.DataFrame(),
    order_rollup=order_rollup if order_rollup is not None else pd.DataFrame(),
    line_status_df=line_status_df if line_status_df is not None else pd.DataFrame(),
    kpis=kpis if isinstance(kpis, dict) else {},
    supplier_scorecards=scorecard,
)

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


# ============================================================
# Workspaces sidebar (optional)
# ============================================================
if callable(render_workspaces_sidebar_and_maybe_override_outputs):
    exceptions, followups, order_rollup, line_status_df, suppliers_df = render_workspaces_sidebar_and_maybe_override_outputs(
        workspaces_dir=WORKSPACES_DIR,
        account_id=account_id,
        store_id=store_id,
        platform_hint=platform_hint,
        orders=orders,
        shipments=shipments,
        tracking=tracking,
        exceptions=exceptions if exceptions is not None else pd.DataFrame(),
        followups=followups_full if followups_full is not None else pd.DataFrame(),
        order_rollup=order_rollup if order_rollup is not None else pd.DataFrame(),
        line_status_df=line_status_df if line_status_df is not None else pd.DataFrame(),
        kpis=kpis if isinstance(kpis, dict) else {},
        suppliers_df=suppliers_df if suppliers_df is not None else pd.DataFrame(),
    )

    if callable(derive_followups_open):
        followups_open = derive_followups_open(followups, ISSUE_TRACKER_PATH)
        followups = followups_open


# ============================================================
# Dashboard KPIs
# ============================================================
st.divider()
st.subheader("Dashboard")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Order lines", int((kpis or {}).get("total_order_lines", 0)))
k2.metric("% Shipped/Delivered", f"{(kpis or {}).get('pct_shipped_or_delivered', 0)}%")
k3.metric("% Delivered", f"{(kpis or {}).get('pct_delivered', 0)}%")
k4.metric("% Unshipped", f"{(kpis or {}).get('pct_unshipped', 0)}%")
k5.metric("% Late Unshipped", f"{(kpis or {}).get('pct_late_unshipped', 0)}%")

if build_daily_action_list is not None and render_daily_action_list is not None:
    try:
        actions = build_daily_action_list(exceptions=exceptions, followups=followups_open, max_items=10)
        render_daily_action_list(actions)
    except Exception:
        pass

if render_kpi_trends is not None:
    try:
        render_kpi_trends(workspaces_dir=WORKSPACES_DIR, account_id=account_id, store_id=store_id)
    except Exception:
        pass


# ============================================================
# Ops Triage
# ============================================================
st.divider()
if callable(render_ops_triage):
    render_ops_triage(exceptions, ops_pack_bytes, pack_name, top_n=10)
else:
    st.subheader("Ops Triage (Start here)")
    if exceptions is None or exceptions.empty:
        st.info("No exceptions found 🎉")
    else:
        st.dataframe(style_exceptions_table(exceptions.head(10)), use_container_width=True, height=320)


# ============================================================
# SLA Escalations panel
# ============================================================
if isinstance(escalations_df, pd.DataFrame) and not escalations_df.empty:
    st.divider()
    st.subheader("SLA Escalations (Supplier-level)")
    st.dataframe(escalations_df, use_container_width=True, height=260)
