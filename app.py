# app.py
from __future__ import annotations

import inspect
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
# Core modules (required)
# ============================================================
from core.ops_pack import make_daily_ops_pack_bytes
from core.scorecards import build_supplier_scorecard_from_run, load_recent_scorecard_history
from core.styling import add_urgency_column, style_exceptions_table
from core.suppliers import enrich_followups_with_suppliers, add_missing_supplier_contact_exceptions
from core.workspaces import workspace_root

# Optional core imports
IssueTrackerStore = None
CONTACT_STATUSES = ["Not Contacted", "Contacted", "Waiting", "Escalated", "Resolved"]
mailto_link = None
build_customer_impact_view = None
build_daily_action_list = None
build_supplier_accountability_view = None

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

try:
    from core.supplier_accountability import build_supplier_accountability_view  # type: ignore
except Exception:
    build_supplier_accountability_view = None

# ============================================================
# UI modules (optional)
# ============================================================
render_sidebar_context = None
try:
    from ui.sidebar import render_sidebar_context  # type: ignore
except Exception:
    render_sidebar_context = None

ensure_demo_state = None
render_demo_editor = None
get_active_raw_inputs = None
try:
    from ui.demo import ensure_demo_state, render_demo_editor, get_active_raw_inputs  # type: ignore
except Exception:
    ensure_demo_state = None
    render_demo_editor = None
    get_active_raw_inputs = None

render_upload_section = None
try:
    from ui.upload_ui import render_upload_section  # type: ignore
except Exception:
    render_upload_section = None

render_onboarding_checklist = None
try:
    from ui.onboarding_ui import render_onboarding_checklist  # type: ignore
except Exception:
    render_onboarding_checklist = None

render_template_downloads = None
try:
    from ui.templates import render_template_downloads  # type: ignore
except Exception:
    render_template_downloads = None

render_diagnostics = None
try:
    from ui.diagnostics_ui import render_diagnostics  # type: ignore
except Exception:
    render_diagnostics = None

render_ops_triage = None
try:
    from ui.triage_ui import render_ops_triage  # type: ignore
except Exception:
    render_ops_triage = None

render_workspaces_sidebar_and_maybe_override_outputs = None
try:
    from ui.workspaces_ui import render_workspaces_sidebar_and_maybe_override_outputs  # type: ignore
except Exception:
    render_workspaces_sidebar_and_maybe_override_outputs = None

apply_issue_tracker = None
render_issue_tracker_maintenance = None
try:
    from ui.issue_tracker_ui import apply_issue_tracker, render_issue_tracker_maintenance  # type: ignore
except Exception:
    apply_issue_tracker = None
    render_issue_tracker_maintenance = None

render_sla_escalations = None
try:
    from ui.sla_escalations_ui import render_sla_escalations  # type: ignore
except Exception:
    render_sla_escalations = None

render_customer_comms_ui = None
try:
    from ui.customer_comms_ui import render_customer_comms_ui  # type: ignore
except Exception:
    render_customer_comms_ui = None

render_comms_pack_download = None
try:
    from ui.comms_pack_ui import render_comms_pack_download  # type: ignore
except Exception:
    render_comms_pack_download = None

render_kpi_trends = None
try:
    from ui.kpi_trends_ui import render_kpi_trends  # type: ignore
except Exception:
    render_kpi_trends = None

render_daily_action_list = None
try:
    from ui.actions_ui import render_daily_action_list  # type: ignore
except Exception:
    render_daily_action_list = None

render_supplier_accountability = None
try:
    from ui.supplier_accountability_ui import render_supplier_accountability  # type: ignore
except Exception:
    render_supplier_accountability = None

render_supplier_followups_tab = None
try:
    from ui.supplier_followups_ui import render_supplier_followups_tab  # type: ignore
except Exception:
    render_supplier_followups_tab = None

render_exceptions_queue = None
try:
    from ui.exceptions_ui import render_exceptions_queue  # type: ignore
except Exception:
    render_exceptions_queue = None

# ============================================================
# Internal section helpers (new)
# ============================================================
from ui.app_helpers import call_with_accepted_kwargs, mailto_fallback
from ui.app_inputs import render_start_here, render_upload_and_templates, resolve_raw_inputs
from ui.app_pipeline import run_pipeline
from ui.app_views import (
    render_dashboard,
    render_ops_triage,
    render_ops_outreach_comms,
    render_exceptions_queue_section,
    render_supplier_scorecards,
    render_sla_escalations_panel,
)


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
# Sidebar context (tenant/defaults/demo/suppliers)
# ============================================================
if callable(render_sidebar_context):
    ctx = render_sidebar_context(DATA_DIR, WORKSPACES_DIR, SUPPLIERS_DIR)
else:
    with st.sidebar:
        st.header("Tenant")
        account_id = st.text_input("account_id", value="demo_account", key="tenant_account_id")
        store_id = st.text_input("store_id", value="demo_store", key="tenant_store_id")
        platform_hint = st.selectbox("platform hint", ["shopify", "amazon", "etsy", "other"], index=0)

        st.header("Defaults")
        default_currency = st.text_input("Default currency", value="USD", key="defaults_currency")
        default_promised_ship_days = st.number_input(
            "Default promised ship days (SLA)",
            min_value=1,
            max_value=30,
            value=3,
            key="defaults_sla_days",
        )

        demo_mode = st.toggle("Use demo data (sticky)", key="demo_mode_fallback")
        suppliers_df = pd.DataFrame()

    ctx = {
        "account_id": account_id,
        "store_id": store_id,
        "platform_hint": platform_hint,
        "default_currency": default_currency,
        "default_promised_ship_days": int(default_promised_ship_days),
        "suppliers_df": suppliers_df,
        "demo_mode": bool(demo_mode),
    }

account_id = ctx["account_id"]
store_id = ctx["store_id"]
platform_hint = ctx["platform_hint"]
default_currency = ctx["default_currency"]
default_promised_ship_days = int(ctx["default_promised_ship_days"])
suppliers_df = ctx.get("suppliers_df", pd.DataFrame())
demo_mode_active = bool(ctx.get("demo_mode", False))

# ============================================================
# Diagnostics UI (optional)
# ============================================================
diag = {
    "render_sla_escalations": render_sla_escalations is not None,
    "IssueTrackerStore": IssueTrackerStore is not None,
    "apply_issue_tracker": apply_issue_tracker is not None,
    "render_supplier_followups_tab": render_supplier_followups_tab is not None,
    "mailto_link": mailto_link is not None,
    "build_customer_impact_view": build_customer_impact_view is not None,
    "render_customer_comms_ui": render_customer_comms_ui is not None,
    "render_comms_pack_download": render_comms_pack_download is not None,
    "build_daily_action_list": build_daily_action_list is not None,
    "render_daily_action_list": render_daily_action_list is not None,
    "render_kpi_trends": render_kpi_trends is not None,
    "build_supplier_accountability_view": build_supplier_accountability_view is not None,
    "render_supplier_accountability": render_supplier_accountability is not None,
    "render_upload_section": render_upload_section is not None,
    "render_onboarding_checklist": render_onboarding_checklist is not None,
    "render_template_downloads": render_template_downloads is not None,
    "render_ops_triage": render_ops_triage is not None,
    "render_exceptions_queue": render_exceptions_queue is not None,
}
if callable(render_diagnostics):
    render_diagnostics(
        workspaces_dir=WORKSPACES_DIR,
        account_id=account_id,
        store_id=store_id,
        diag=diag,
        expanded=False,
    )

# ============================================================
# Onboarding checklist (optional)
# ============================================================
if callable(render_onboarding_checklist):
    render_onboarding_checklist(expanded=True)

# ============================================================
# Start + Uploads
# ============================================================
render_start_here(
    data_dir=DATA_DIR,
    demo_mode_active=demo_mode_active,
    ensure_demo_state=ensure_demo_state,
    render_demo_editor=render_demo_editor,
)

uploads = render_upload_and_templates(
    render_upload_section=render_upload_section,
    render_template_downloads=render_template_downloads,
)

raw_orders, raw_shipments, raw_tracking = resolve_raw_inputs(
    demo_mode_active=demo_mode_active,
    data_dir=DATA_DIR,
    uploads=uploads,
    get_active_raw_inputs=get_active_raw_inputs,
)

# ============================================================
# Pipeline
# ============================================================
run = run_pipeline(
    raw_orders=raw_orders,
    raw_shipments=raw_shipments,
    raw_tracking=raw_tracking,
    account_id=account_id,
    store_id=store_id,
    platform_hint=platform_hint,
    default_currency=default_currency,
    default_promised_ship_days=default_promised_ship_days,
    suppliers_df=suppliers_df,
    workspaces_dir=WORKSPACES_DIR,
    normalize_orders=normalize_orders,
    normalize_shipments=normalize_shipments,
    normalize_tracking=normalize_tracking,
    reconcile_all=reconcile_all,
    enhance_explanations=enhance_explanations,
    enrich_followups_with_suppliers=enrich_followups_with_suppliers,
    add_missing_supplier_contact_exceptions=add_missing_supplier_contact_exceptions,
    add_urgency_column=add_urgency_column,
    build_supplier_scorecard_from_run=build_supplier_scorecard_from_run,
    make_daily_ops_pack_bytes=make_daily_ops_pack_bytes,
    workspace_root=workspace_root,
    render_sla_escalations=render_sla_escalations,
    apply_issue_tracker=apply_issue_tracker,
    render_issue_tracker_maintenance=render_issue_tracker_maintenance,
    IssueTrackerStore=IssueTrackerStore,
    build_customer_impact_view=build_customer_impact_view,
    mailto_link=mailto_link,
    render_workspaces_sidebar_and_maybe_override_outputs=render_workspaces_sidebar_and_maybe_override_outputs,
)

# ============================================================
# Views
# ============================================================
render_dashboard(
    kpis=run["kpis"] if isinstance(run.get("kpis"), dict) else {},
    exceptions=run["exceptions"],
    followups_open=run["followups_open"],
    workspaces_dir=WORKSPACES_DIR,
    account_id=account_id,
    store_id=store_id,
    build_daily_action_list=build_daily_action_list,
    render_daily_action_list=render_daily_action_list,
    render_kpi_trends=render_kpi_trends,
)

render_ops_triage(
    exceptions=run["exceptions"],
    ops_pack_bytes=run["ops_pack_bytes"],
    pack_name=run["pack_name"],
    style_exceptions_table=style_exceptions_table,
    render_ops_triage=render_ops_triage,
)

render_ops_outreach_comms(
    followups_open=run["followups_open"],
    customer_impact=run["customer_impact"],
    scorecard=run["scorecard"],
    ws_root=run["ws_root"],
    issue_tracker_path=run["issue_tracker_path"],
    contact_statuses=CONTACT_STATUSES if isinstance(CONTACT_STATUSES, list) else ["Not Contacted", "Contacted", "Waiting", "Escalated", "Resolved"],
    mailto_link_fn=mailto_link if callable(mailto_link) else mailto_fallback,
    build_supplier_accountability_view=build_supplier_accountability_view,
    render_supplier_accountability=render_supplier_accountability,
    render_supplier_followups_tab=render_supplier_followups_tab,
    render_customer_comms_ui=render_customer_comms_ui,
    render_comms_pack_download=render_comms_pack_download,
    account_id=account_id,
    store_id=store_id,
)

render_exceptions_queue_section(
    exceptions=run["exceptions"],
    style_exceptions_table=style_exceptions_table,
    render_exceptions_queue=render_exceptions_queue,
)

# Supplier scorecards + trend
list_runs = None
try:
    from core.workspaces import list_runs  # type: ignore
except Exception:
    list_runs = None

render_supplier_scorecards(
    scorecard=run["scorecard"],
    ws_root=run["ws_root"],
    load_recent_scorecard_history=load_recent_scorecard_history,
    list_runs=list_runs,
)

render_sla_escalations_panel(escalations_df=run.get("escalations_df", pd.DataFrame()))
