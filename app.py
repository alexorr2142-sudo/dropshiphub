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
# Core modules
# ============================================================
from core.ops_pack import make_daily_ops_pack_bytes
from core.scorecards import build_supplier_scorecard_from_run, load_recent_scorecard_history
from core.styling import add_urgency_column, style_exceptions_table, copy_button
from core.suppliers import (
    enrich_followups_with_suppliers,
    add_missing_supplier_contact_exceptions,
)
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

# Optional timeline
TimelineStore = None
timeline_path_for_ws_root = None
try:
    from core.timeline_store import TimelineStore, timeline_path_for_ws_root  # type: ignore
except Exception:
    TimelineStore = None
    timeline_path_for_ws_root = None

# ============================================================
# UI modules
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

# Issue tracker (with helper wrapper)
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

# NEW: Supplier follow-ups tab (dedicated module)
render_supplier_followups_tab = None
try:
    from ui.supplier_followups_ui import render_supplier_followups_tab  # type: ignore
except Exception:
    render_supplier_followups_tab = None

# Timeline panel UI (optional)
render_timeline_panel = None
try:
    from ui.timeline_ui import render_timeline_panel  # type: ignore
except Exception:
    render_timeline_panel = None


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


def _is_empty_df(x) -> bool:
    return (x is None) or (not isinstance(x, pd.DataFrame)) or x.empty


def _log_run_event(ws_root: Path, event_type: str, summary: str, data: dict | None = None) -> None:
    """
    Best-effort system-level timeline logging. Never raises.
    """
    try:
        if TimelineStore is None or timeline_path_for_ws_root is None:
            return
        tl = TimelineStore(timeline_path_for_ws_root(ws_root))
        tl.log(scope="system", event_type=event_type, summary=summary, data=data or {}, actor="system")
    except Exception:
        return


# ============================================================
# Page setup (NO ACCESS GATES right now)
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
        platform_hint = st.selectbox(
            "platform hint",
            ["shopify", "amazon", "etsy", "other"],
            index=0,
            key="tenant_platform_hint",
        )

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

# Per-tenant workspace root
ws_root = workspace_root(WORKSPACES_DIR, account_id, store_id)
ws_root.mkdir(parents=True, exist_ok=True)
ISSUE_TRACKER_PATH = Path(ws_root) / "issue_tracker.json"

# ============================================================
# Diagnostics UI (optional)
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
    "build_supplier_accountability_view": build_supplier_accountability_view is not None,
    "render_supplier_accountability": render_supplier_accountability is not None,
    "render_upload_section": render_upload_section is not None,
    "render_onboarding_checklist": render_onboarding_checklist is not None,
    "render_template_downloads": render_template_downloads is not None,
    "render_ops_triage": render_ops_triage is not None,
    "render_supplier_followups_tab": render_supplier_followups_tab is not None,
    "render_timeline_panel": render_timeline_panel is not None,
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
# Sidebar maintenance (issue tracker)
# ============================================================
with st.sidebar:
    if callable(render_issue_tracker_maintenance) and (IssueTrackerStore is not None):
        render_issue_tracker_maintenance(ISSUE_TRACKER_PATH, default_prune_days=30)

# ============================================================
# Onboarding checklist (optional)
# ============================================================
if callable(render_onboarding_checklist):
    render_onboarding_checklist(expanded=True)

# ============================================================
# Start here (Demo editor)
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
        f_tracking = st.file_uploader("Tracking CSV\n(optional)", type=["csv"], key="uploader_tracking")
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
# Templates UI
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
# Stop early if Orders/Shipments are empty (avoid reconcile crash)
# ============================================================
if _is_empty_df(raw_orders) or _is_empty_df(raw_shipments):
    st.divider()
    st.subheader("Data checks")
    st.warning("We found some schema issues. You can still proceed, but fixing these improves accuracy:")

    if _is_empty_df(raw_orders):
        st.write("- [orders] Input orders dataframe is empty.")
    if _is_empty_df(raw_shipments):
        st.write("- [shipments] Input shipments dataframe is empty.")

    st.error("Cannot run reconciliation without Orders + Shipments data (missing required columns like order_id and sku).")

    if demo_mode_active:
        st.info(
            "Demo Mode is ON, but demo data is empty. "
            "This means the demo loader didn't populate demo_raw_orders/demo_raw_shipments."
        )
        st.caption("Next fix is in ui/demo.py (demo loader).")
    else:
        st.info("Please upload both **Orders CSV** and **Shipments CSV** in the Upload section.")

    with st.expander("Debug (raw input shapes / columns)", expanded=False):
        if isinstance(raw_orders, pd.DataFrame):
            st.write("raw_orders shape:", raw_orders.shape)
            st.write("raw_orders columns:", list(raw_orders.columns))
        else:
            st.write("raw_orders:", type(raw_orders))

        if isinstance(raw_shipments, pd.DataFrame):
            st.write("raw_shipments shape:", raw_shipments.shape)
            st.write("raw_shipments columns:", list(raw_shipments.columns))
        else:
            st.write("raw_shipments:", type(raw_shipments))

        if isinstance(raw_tracking, pd.DataFrame):
            st.write("raw_tracking shape:", raw_tracking.shape)
            st.write("raw_tracking columns:", list(raw_tracking.columns))
        else:
            st.write("raw_tracking:", type(raw_tracking))

    st.stop()

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
# Reconcile (WITH DEBUG TRY/EXCEPT)
# ============================================================
st.divider()
st.subheader("Running reconciliation")

try:
    line_status_df, exceptions, followups, order_rollup, kpis = reconcile_all(orders, shipments, tracking)
except Exception as e:
    st.error("Reconciliation failed. Showing debug details below.")

    st.markdown("### Debug: normalized inputs")
    st.write("orders columns:", list(orders.columns))
    st.write("shipments columns:", list(shipments.columns))
    st.write("tracking columns:", list(tracking.columns) if isinstance(tracking, pd.DataFrame) else tracking)

    st.markdown("### Error")
    st.code(str(e))

    with st.expander("Preview orders (head)", expanded=False):
        st.dataframe(orders.head(5), use_container_width=True)
    with st.expander("Preview shipments (head)", expanded=False):
        st.dataframe(shipments.head(5), use_container_width=True)
    with st.expander("Preview tracking (head)", expanded=False):
        if isinstance(tracking, pd.DataFrame):
            st.dataframe(tracking.head(5), use_container_width=True)

    st.stop()

# System timeline event (best-effort)
_log_run_event(
    ws_root,
    event_type="run.reconciled",
    summary="Reconciliation completed",
    data={
        "exceptions": int(len(exceptions)) if isinstance(exceptions, pd.DataFrame) else 0,
        "followups": int(len(followups)) if isinstance(followups, pd.DataFrame) else 0,
    },
)

# Explain enhancements (best-effort)
try:
    exceptions = enhance_explanations(exceptions)
except Exception:
    pass

# Enrich followups + add missing supplier contact exceptions
followups = enrich_followups_with_suppliers(followups, suppliers_df)
exceptions = add_missing_supplier_contact_exceptions(exceptions, followups)

# Ensure urgency exists
if exceptions is not None and not exceptions.empty and "Urgency" not in exceptions.columns:
    exceptions = add_urgency_column(exceptions)

# Scorecard
scorecard = build_supplier_scorecard_from_run(line_status_df, exceptions)

# ============================================================
# SLA Escalations + followups_full
# ============================================================
followups_full = followups.copy() if isinstance(followups, pd.DataFrame) else pd.DataFrame()
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

# ============================================================
# Issue Tracker wrapper (OPEN + enriched)
# ============================================================
followups_open = followups_full.copy()
followups_open_enriched = followups_open.copy()

if callable(apply_issue_tracker):
    try:
        it = apply_issue_tracker(ws_root=ws_root, followups_full=followups_full)
        ISSUE_TRACKER_PATH = it["issue_tracker_path"]
        followups_full = it["followups_full"]
        followups_open = it["followups_open"]
        followups_open_enriched = it.get("followups_open_enriched", followups_open)
    except Exception:
        pass
else:
    # fallback: if no wrapper, keep current behavior
    followups_open = followups_full.copy()
    followups_open_enriched = followups_open.copy()

# ============================================================
# Customer impact build
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

_log_run_event(
    ws_root,
    event_type="run.ops_pack_generated",
    summary="Ops pack generated",
    data={"pack_name": pack_name},
)

# ============================================================
# Workspaces sidebar (optional UI module)
# ============================================================
if callable(render_workspaces_sidebar_and_maybe_override_outputs):
    exceptions, followups_full2, order_rollup, line_status_df, suppliers_df = render_workspaces_sidebar_and_maybe_override_outputs(
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

    if isinstance(followups_full2, pd.DataFrame):
        followups_full = followups_full2.copy()

    # Re-apply issue tracker after override
    if callable(apply_issue_tracker):
        try:
            it = apply_issue_tracker(ws_root=ws_root, followups_full=followups_full)
            ISSUE_TRACKER_PATH = it["issue_tracker_path"]
            followups_full = it["followups_full"]
            followups_open = it["followups_open"]
            followups_open_enriched = it.get("followups_open_enriched", followups_open)
        except Exception:
            pass

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
# Optional: Timeline (system)
# ============================================================
if callable(render_timeline_panel):
    try:
        render_timeline_panel(
            timeline_path=(ws_root / "timeline.jsonl"),
            title="Timeline (System + Issues)",
            limit=100,
            key_prefix="timeline_system",
        )
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
# Ops Outreach (Comms)
# ============================================================
st.divider()
st.subheader("Ops Outreach (Comms)")
tab1, tab2, tab3 = st.tabs(["Supplier Follow-ups", "Customer Emails", "Comms Pack"])

with tab1:
    if callable(render_supplier_followups_tab):
        render_supplier_followups_tab(
            followups_open=followups_open,
            issue_tracker_path=ISSUE_TRACKER_PATH,
            contact_statuses=CONTACT_STATUSES,
            mailto_link_fn=mailto_link if callable(mailto_link) else _mailto_fallback,
            scorecard=scorecard,
            build_supplier_accountability_view=build_supplier_accountability_view,
            render_supplier_accountability=render_supplier_accountability,
            key_prefix="supplier_followups",
        )
    else:
        st.warning("ui/supplier_followups_ui.py is not available.")

with tab2:
    st.caption("Customer-facing updates (email-first).")
    if customer_impact is None or customer_impact.empty:
        st.info("No customer-impact items detected for this run.")
    else:
        if render_customer_comms_ui is not None:
            try:
                call_with_accepted_kwargs(
                    render_customer_comms_ui,
                    customer_impact=customer_impact,
                    ws_root=ws_root,
                    account_id=account_id,
                    store_id=store_id,
                )
            except Exception:
                try:
                    render_customer_comms_ui(customer_impact=customer_impact)
                except Exception:
                    render_customer_comms_ui(customer_impact)
        else:
            st.dataframe(customer_impact, use_container_width=True, height=320)

with tab3:
    st.caption("Download combined comms artifacts (supplier + customer).")
    if render_comms_pack_download is not None:
        try:
            call_with_accepted_kwargs(
                render_comms_pack_download,
                followups=followups_open,
                customer_impact=customer_impact,
                ws_root=ws_root,
                account_id=account_id,
                store_id=store_id,
            )
        except Exception:
            try:
                render_comms_pack_download(followups=followups_open, customer_impact=customer_impact)
            except Exception:
                render_comms_pack_download()
    else:
        st.info("Comms pack UI module not available.")

# ============================================================
# Exceptions Queue
# ============================================================
st.divider()
st.subheader("Exceptions Queue (Action this first)")

if exceptions is None or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
    fcol1, fcol2, fcol3, fcol4 = st.columns(4)

    with fcol1:
        issue_types = (
            sorted(exceptions["issue_type"].dropna().unique().tolist())
            if "issue_type" in exceptions.columns
            else []
        )
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types, key="exq_issue_types")

    with fcol2:
        countries = sorted(
            [
                c
                for c in exceptions.get("customer_country", pd.Series([], dtype="object"))
                .dropna()
                .unique()
                .tolist()
                if str(c).strip() != ""
            ]
        )
        country_filter = st.multiselect("Customer country", countries, default=countries, key="exq_countries")

    with fcol3:
        suppliers = sorted(
            [
                s
                for s in exceptions.get("supplier_name", pd.Series([], dtype="object"))
                .dropna()
                .unique()
                .tolist()
                if str(s).strip() != ""
            ]
        )
        supplier_filter = st.multiselect("Supplier", suppliers, default=suppliers, key="exq_suppliers")

    with fcol4:
        urgencies = ["Critical", "High", "Medium", "Low"]
        urgency_filter = st.multiselect("Urgency", urgencies, default=urgencies, key="exq_urgency")

    filtered = exceptions.copy()
    if issue_filter and "issue_type" in filtered.columns:
        filtered = filtered[filtered["issue_type"].isin(issue_filter)]
    if country_filter and "customer_country" in filtered.columns:
        filtered = filtered[filtered["customer_country"].isin(country_filter)]
    if supplier_filter and "supplier_name" in filtered.columns:
        filtered = filtered[filtered["supplier_name"].isin(supplier_filter)]
    if urgency_filter and "Urgency" in filtered.columns:
        filtered = filtered[filtered["Urgency"].isin(urgency_filter)]

    sort_cols = [c for c in ["Urgency", "order_id"] if c in filtered.columns]
    if sort_cols:
        filtered = filtered.sort_values(sort_cols, ascending=True)

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

    st.dataframe(style_exceptions_table(filtered[show_cols]), use_container_width=True, height=420)
    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
        key="dl_exceptions_csv",
    )

# ============================================================
# Supplier Scorecards
# ============================================================
st.divider()
st.subheader("Supplier Scorecards (Performance + Trends)")

if scorecard is None or scorecard.empty:
    st.info("Scorecards require `supplier_name` in your normalized line status data.")
else:
    sc1, sc2 = st.columns(2)
    with sc1:
        top_n = st.slider("Show top N suppliers", min_value=5, max_value=50, value=15, step=5, key="scorecard_top_n")
    with sc2:
        min_lines = st.number_input(
            "Min total lines",
            min_value=1,
            max_value=1000000,
            value=1,
            step=1,
            key="scorecard_min_lines",
        )

    view = scorecard[scorecard["total_lines"] >= int(min_lines)].head(int(top_n))

    show_cols = [
        "supplier_name",
        "total_lines",
        "exception_lines",
        "exception_rate",
        "critical",
        "high",
        "missing_tracking_flags",
        "late_flags",
        "carrier_exception_flags",
    ]
    show_cols = [c for c in show_cols if c in view.columns]
    st.dataframe(view[show_cols], use_container_width=True, height=320)

    st.download_button(
        "Download Supplier Scorecards CSV",
        data=scorecard.to_csv(index=False).encode("utf-8"),
        file_name="supplier_scorecards.csv",
        mime="text/csv",
        key="dl_scorecards_csv",
    )

    with st.expander("Trend over time (from saved runs)", expanded=True):
        runs_for_trend = []
        try:
            from core.workspaces import list_runs

            runs_for_trend = list_runs(ws_root)
        except Exception:
            runs_for_trend = []

        if not runs_for_trend:
            st.caption("No saved runs yet. Click **Save this run** to build trend history.")
        else:
            max_runs = st.slider("Use last N saved runs", 5, 50, 25, 5, key="trend_max_runs")
            hist = load_recent_scorecard_history(str(ws_root), max_runs=int(max_runs))

            if hist is None or hist.empty:
                st.caption("No historical scorecards found yet (save a run first).")
            else:
                supplier_options = sorted(hist["supplier_name"].dropna().unique().tolist())
                chosen_supplier = st.selectbox("Supplier", supplier_options, key="scorecard_trend_supplier")

                s_hist = hist[hist["supplier_name"] == chosen_supplier].copy().sort_values("run_dt")
                chart_df = s_hist[["run_dt", "exception_rate"]].dropna()
                if not chart_df.empty:
                    st.line_chart(chart_df.set_index("run_dt"))

                tcols = ["run_id", "total_lines", "exception_lines", "exception_rate", "critical", "high"]
                tcols = [c for c in tcols if c in s_hist.columns]
                st.dataframe(
                    s_hist[tcols].sort_values("run_id", ascending=False),
                    use_container_width=True,
                    height=220,
                )

# ============================================================
# SLA Escalations panel (table)
# ============================================================
if isinstance(escalations_df, pd.DataFrame) and not escalations_df.empty:
    st.divider()
    st.subheader("SLA Escalations (Supplier-level)")
    st.dataframe(escalations_df, use_container_width=True, height=260)
