# app.py
from __future__ import annotations

import os
import inspect
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# Streamlit components only used by some legacy UI modules (safe to keep)
import streamlit.components.v1 as components  # noqa: F401

# ============================================================
# 🔓 PUBLIC REVIEW MODE (TEMP)
# True  => bypass passcode + email allowlist gates
# False => gates enforced as normal
# ============================================================
PUBLIC_REVIEW_MODE = False


# ============================================================
# Robust local imports (normalize/reconcile/explain)
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
# Core imports (moved out of app.py)
# ============================================================
from core.workspaces import workspace_root  # safe_slug used inside core modules
from core.styling import add_urgency_column, style_exceptions_table
from core.suppliers import enrich_followups_with_suppliers, add_missing_supplier_contact_exceptions
from core.scorecards import build_supplier_scorecard_from_run, load_recent_scorecard_history
from core.ops_pack import make_daily_ops_pack_bytes

# ============================================================
# UI imports (moved out of app.py)
# ============================================================
from ui.auth import early_access_gate, require_email_access_gate
from ui.sidebar import render_sidebar_context
from ui.demo import ensure_demo_state, render_demo_editor, get_active_raw_inputs
from ui.templates import render_template_downloads
from ui.triage_ui import render_ops_triage
from ui.workspaces_ui import render_workspaces_sidebar_and_maybe_override_outputs
from ui.issue_tracker_ui import render_issue_tracker_maintenance, derive_followups_open
from ui.supplier_followups_ui import render_supplier_followups_tab


# ============================================================
# Optional feature imports (do NOT crash if missing)
# ============================================================
render_sla_escalations = None
mailto_link = None
build_customer_impact_view = None
render_customer_comms_ui = None
render_comms_pack_download = None
build_daily_action_list = None
render_daily_action_list = None
render_kpi_trends = None
build_supplier_accountability_view = None
render_supplier_accountability = None

try:
    from ui.sla_escalations_ui import render_sla_escalations  # type: ignore
except Exception:
    render_sla_escalations = None

try:
    from core.email_utils import mailto_link  # type: ignore
except Exception:
    mailto_link = None

try:
    from core.customer_impact import build_customer_impact_view  # type: ignore
except Exception:
    build_customer_impact_view = None

try:
    from ui.customer_comms_ui import render_customer_comms_ui  # type: ignore
except Exception:
    render_customer_comms_ui = None

try:
    from ui.comms_pack_ui import render_comms_pack_download  # type: ignore
except Exception:
    render_comms_pack_download = None

try:
    from core.actions import build_daily_action_list  # type: ignore
except Exception:
    build_daily_action_list = None

try:
    from ui.actions_ui import render_daily_action_list  # type: ignore
except Exception:
    render_daily_action_list = None

try:
    from ui.kpi_trends_ui import render_kpi_trends  # type: ignore
except Exception:
    render_kpi_trends = None

try:
    from core.supplier_accountability import build_supplier_accountability_view  # type: ignore
except Exception:
    build_supplier_accountability_view = None

try:
    from ui.supplier_accountability_ui import render_supplier_accountability  # type: ignore
except Exception:
    render_supplier_accountability = None

# Contact statuses (prefer IssueTrackerStore constant if present)
try:
    from core.issue_tracker import CONTACT_STATUSES  # type: ignore
except Exception:
    CONTACT_STATUSES = ["Not Contacted", "Contacted", "Waiting", "Escalated", "Resolved"]


# ============================================================
# Small helper (safe signature calls)
# ============================================================
def call_with_accepted_kwargs(fn, **kwargs):
    """Calls fn with only kwargs it accepts (prevents unexpected kw crashes)."""
    sig = inspect.signature(fn)
    accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return fn(**accepted)


# ============================================================
# Page setup
# ============================================================
st.set_page_config(page_title="Dropship Hub", layout="wide")


# ============================================================
# Access gates (kept tiny in app.py)
# ============================================================
if not PUBLIC_REVIEW_MODE:
    ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")
    early_access_gate(ACCESS_CODE)
    require_email_access_gate()


# ============================================================
# Paths
# ============================================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

WORKSPACES_DIR = DATA_DIR / "workspaces"
if WORKSPACES_DIR.exists() and not WORKSPACES_DIR.is_dir():
    st.error("Workspace storage path invalid: `data/workspaces` exists but is a FILE.")
    st.stop()
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

SUPPLIERS_DIR = DATA_DIR / "suppliers"
if SUPPLIERS_DIR.exists() and not SUPPLIERS_DIR.is_dir():
    st.error("Supplier storage path invalid: `data/suppliers` exists but is a FILE.")
    st.stop()
SUPPLIERS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Sidebar context (tenant/defaults/demo/suppliers)
# ============================================================
ctx = render_sidebar_context(DATA_DIR, WORKSPACES_DIR, SUPPLIERS_DIR)
account_id = ctx["account_id"]
store_id = ctx["store_id"]
platform_hint = ctx["platform_hint"]
default_currency = ctx["default_currency"]
default_promised_ship_days = int(ctx["default_promised_ship_days"])
suppliers_df = ctx["suppliers_df"]
demo_mode_active = bool(ctx["demo_mode"])

# Ensure demo tables are loaded once when demo_mode is ON
ensure_demo_state(DATA_DIR)


# ============================================================
# Diagnostics (top)
# ============================================================
with st.expander("Diagnostics", expanded=False):
    diag = {
        "render_sla_escalations": render_sla_escalations is not None,
        "mailto_link": callable(mailto_link),
        "build_customer_impact_view": build_customer_impact_view is not None,
        "render_customer_comms_ui": render_customer_comms_ui is not None,
        "render_comms_pack_download": render_comms_pack_download is not None,
        "build_daily_action_list": build_daily_action_list is not None,
        "render_daily_action_list": render_daily_action_list is not None,
        "render_kpi_trends": render_kpi_trends is not None,
        "build_supplier_accountability_view": build_supplier_accountability_view is not None,
        "render_supplier_accountability": render_supplier_accountability is not None,
    }
    st.json(diag)

    ws_root_diag = workspace_root(WORKSPACES_DIR, account_id, store_id)
    st.write(f"ws_root: `{ws_root_diag.as_posix()}`")


# ============================================================
# Onboarding checklist (14)
# ============================================================
st.divider()
with st.expander("Onboarding checklist (14 steps)", expanded=True):
    st.markdown(
        """
1. Enter **Early Access Code**  
2. Verify your **work email** (allowlist gate)  
3. Set **Tenant**: `account_id`, `store_id`, `platform_hint`  
4. Set **Defaults**: currency + promised ship days (SLA)  
5. (Optional) Turn on **Demo Mode (Sticky)** to explore instantly  
6. (Demo Mode) Use **Edit demo data** to simulate real scenarios  
7. Upload **Orders CSV** (required if not using demo)  
8. Upload **Shipments CSV** (required if not using demo)  
9. Upload **Tracking CSV** (optional but recommended)  
10. Download **Templates** if you need the correct format  
11. Upload **suppliers.csv** to enable auto-filled supplier emails  
12. Review **Ops Triage** (Critical + High first)  
13. Work **Exceptions Queue** (filter by supplier/country/urgency)  
14. Use **Ops Outreach (Comms)** then **Save Run** to build trends/history
        """.strip()
    )


# ============================================================
# Start here (Demo editor)
# ============================================================
st.subheader("Start here")
render_demo_editor()


# ============================================================
# Upload section
# ============================================================
st.divider()
st.subheader("Upload your data")
col1, col2, col3 = st.columns(3)
with col1:
    f_orders = st.file_uploader("Orders CSV (Shopify export or generic)", type=["csv"], key="uploader_orders")
with col2:
    f_shipments = st.file_uploader("Shipments CSV (supplier export)", type=["csv"], key="uploader_shipments")
with col3:
    f_tracking = st.file_uploader("Tracking CSV (optional)", type=["csv"], key="uploader_tracking")


# ============================================================
# Templates
# ============================================================
render_template_downloads()


# ============================================================
# Active inputs (demo OR uploads)
# ============================================================
raw_orders, raw_shipments, raw_tracking = get_active_raw_inputs(
    demo_mode=demo_mode_active,
    data_dir=DATA_DIR,
    f_orders=f_orders,
    f_shipments=f_shipments,
    f_tracking=f_tracking,
)


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

# Enrich with supplier CRM + add “missing supplier contact” exceptions
followups = enrich_followups_with_suppliers(followups, suppliers_df)
exceptions = add_missing_supplier_contact_exceptions(exceptions, followups)


# ============================================================
# SLA Escalations UI (may enrich followups_full)
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
# Per-tenant workspace + issue tracker path
# ============================================================
ws_root = workspace_root(WORKSPACES_DIR, account_id, store_id)
ws_root.mkdir(parents=True, exist_ok=True)
ISSUE_TRACKER_PATH = Path(ws_root) / "issue_tracker.json"


# ============================================================
# Issue tracker maintenance (sidebar)
# ============================================================
with st.sidebar:
    render_issue_tracker_maintenance(
        issue_tracker_path=ISSUE_TRACKER_PATH,
        default_prune_days=30,
        key_prefix="issue_maint",
    )


# ============================================================
# OPEN followups derived from issue tracker (resolved filtered out)
# ============================================================
followups_open = derive_followups_open(followups_full, issue_tracker_path=ISSUE_TRACKER_PATH)
followups = followups_open


# ============================================================
# Workspaces (sidebar) + maybe override outputs (load saved run)
# ============================================================
exceptions, followups_full, order_rollup, line_status_df, suppliers_df = (
    render_workspaces_sidebar_and_maybe_override_outputs(
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
)

# Re-derive open after override (if loaded run changed followups_full)
followups_open = derive_followups_open(followups_full, issue_tracker_path=ISSUE_TRACKER_PATH)
followups = followups_open


# ============================================================
# Urgency + scorecards
# ============================================================
if exceptions is not None and not exceptions.empty and "Urgency" not in exceptions.columns:
    exceptions = add_urgency_column(exceptions)

scorecard = build_supplier_scorecard_from_run(line_status_df, exceptions)


# ============================================================
# Customer impact build (optional)
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

# Use safe-call so ops_pack signature can evolve without breaking app.py
ops_pack_bytes = call_with_accepted_kwargs(
    make_daily_ops_pack_bytes,
    exceptions=exceptions if exceptions is not None else pd.DataFrame(),
    followups=followups_open if followups_open is not None else pd.DataFrame(),
    order_rollup=order_rollup if order_rollup is not None else pd.DataFrame(),
    line_status_df=line_status_df if line_status_df is not None else pd.DataFrame(),
    kpis=kpis if isinstance(kpis, dict) else {},
    supplier_scorecards=scorecard,
    customer_impact=customer_impact,  # ignored if core signature doesn't accept it
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
# Ops Triage (moved out of app.py)
# ============================================================
st.divider()
render_ops_triage(
    exceptions=exceptions,
    ops_pack_bytes=ops_pack_bytes,
    pack_name=pack_name,
    key_prefix="triage",
    top_n=10,
)


# ============================================================
# Ops Outreach (Comms)
# ============================================================
st.divider()
st.subheader("Ops Outreach (Comms)")

tab1, tab2, tab3 = st.tabs(["Supplier Follow-ups", "Customer Emails", "Comms Pack"])

with tab1:
    render_supplier_followups_tab(
        followups_open=followups_open,
        issue_tracker_path=ISSUE_TRACKER_PATH,
        contact_statuses=CONTACT_STATUSES,
        mailto_link_fn=mailto_link,
        scorecard=scorecard,
        build_supplier_accountability_view=build_supplier_accountability_view,
        render_supplier_accountability=render_supplier_accountability,
        key_prefix="supplier_followups",
    )

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
                # ultra-safe fallback
                try:
                    render_customer_comms_ui(customer_impact=customer_impact)
                except Exception:
                    try:
                        render_customer_comms_ui(customer_impact)
                    except Exception:
                        st.warning("Customer comms UI failed to render.")
        else:
            cols = customer_impact.columns.tolist()
            order_col = "order_id" if "order_id" in cols else ("order" if "order" in cols else None)
            email_col = "customer_email" if "customer_email" in cols else ("email" if "email" in cols else None)
            reason_col = "reason" if "reason" in cols else ("issue_summary" if "issue_summary" in cols else None)

            if order_col:
                opts = customer_impact[order_col].fillna("").astype(str).tolist()
                chosen_order = st.selectbox("Select order", opts, key="cust_email_order_select")
                crow = customer_impact[customer_impact[order_col].astype(str) == str(chosen_order)].iloc[0]
            else:
                chosen_order = "(customer item)"
                crow = customer_impact.iloc[0]

            cust_email = str(crow.get(email_col, "")).strip() if email_col else ""
            reason = str(crow.get(reason_col, "")).strip() if reason_col else ""

            subj_default = f"Update on your order {chosen_order}".strip()
            c_subject = st.text_input("Subject", value=subj_default, key="cust_email_subject")

            body_lines = [
                "Hi there,",
                "",
                f"We’re reaching out with an update on your order {chosen_order}.",
            ]
            if reason:
                body_lines += ["", f"Update: {reason}"]
            body_lines += [
                "",
                "What we’re doing next:",
                "• We’ve contacted the supplier/carrier and requested an immediate status update.",
                "• We’re monitoring the shipment and will keep you updated as soon as we have confirmed details.",
                "• If we cannot confirm progress quickly, we will offer next steps (replacement, refund, or alternative).",
                "",
                "Thank you for your patience — we’ll follow up again soon.",
                "",
                "Best,",
            ]
            c_body = st.text_area("Body", value="\n".join(body_lines), height=240, key="cust_email_body")

            # NOTE: copy buttons live in core/styling, but customer tab extraction is next.
            from core.styling import copy_button  # local import to keep app.py startup stable

            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                copy_button(cust_email, "Copy customer email", key=f"copy_customer_email_{chosen_order}")
            with cc2:
                copy_button(c_subject, "Copy subject", key=f"copy_customer_subject_{chosen_order}")
            with cc3:
                copy_button(c_body, "Copy body", key=f"copy_customer_body_{chosen_order}")

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
                try:
                    render_comms_pack_download()
                except Exception:
                    st.info("Comms pack UI module not available.")
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
        issue_types = sorted(exceptions["issue_type"].dropna().unique().tolist()) if "issue_type" in exceptions.columns else []
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types, key="exq_issue_types")

    with fcol2:
        countries = sorted(
            [c for c in exceptions.get("customer_country", pd.Series([], dtype="object")).dropna().unique().tolist() if str(c).strip() != ""]
        )
        country_filter = st.multiselect("Customer country", countries, default=countries, key="exq_countries")

    with fcol3:
        suppliers = sorted(
            [s for s in exceptions.get("supplier_name", pd.Series([], dtype="object")).dropna().unique().tolist() if str(s).strip() != ""]
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

    st.dataframe(style_exceptions_table(filtered[show_cols] if show_cols else filtered), use_container_width=True, height=420)
    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
        key="dl_exceptions_csv",
    )


# ============================================================
# Supplier Scorecards (Performance + Trends)
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
        min_lines = st.number_input("Min total lines", min_value=1, max_value=1000000, value=1, step=1, key="scorecard_min_lines")

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
    st.dataframe(view[show_cols] if show_cols else view, use_container_width=True, height=320)

    st.download_button(
        "Download Supplier Scorecards CSV",
        data=scorecard.to_csv(index=False).encode("utf-8"),
        file_name="supplier_scorecards.csv",
        mime="text/csv",
        key="dl_scorecards_csv",
    )

    with st.expander("Trend over time (from saved runs)", expanded=True):
        runs_for_trend = []  # list_runs lives in core.workspaces, but history loader uses ws_root directly
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
            st.dataframe(s_hist[tcols].sort_values("run_id", ascending=False), use_container_width=True, height=220)


# ============================================================
# SLA Escalations panel (table)
# ============================================================
if isinstance(escalations_df, pd.DataFrame) and not escalations_df.empty:
    st.divider()
    st.subheader("SLA Escalations (Supplier-level)")
    st.dataframe(escalations_df, use_container_width=True, height=260)
