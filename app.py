# app.py
from __future__ import annotations

import inspect
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# -------------------------------
# App mode
# -------------------------------
PUBLIC_REVIEW_MODE = False  # True => bypass gates

# -------------------------------
# Core pipeline (your repo root)
# -------------------------------
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
# Core modules
# -------------------------------
from core.styling import add_urgency_column
from core.suppliers import enrich_followups_with_suppliers, add_missing_supplier_contact_exceptions
from core.scorecards import build_supplier_scorecard_from_run
from core.workspaces import workspace_root
from core.ops_pack import make_daily_ops_pack_bytes

# -------------------------------
# UI modules (known to exist)
# -------------------------------
from ui.auth import require_access
from ui.sidebar import render_sidebar_context
from ui.demo import ensure_demo_state, render_demo_editor, get_active_raw_inputs
from ui.templates import render_template_downloads
from ui.upload_ui import render_upload_section, enforce_demo_or_uploads_ready
from ui.workspaces_ui import render_workspaces_sidebar_and_maybe_override_outputs
from ui.triage_ui import render_ops_triage
from ui.issue_tracker_ui import (
    derive_followups_open,
    enrich_followups_with_contact_fields,
    render_issue_tracker_maintenance,
)

# -------------------------------
# Optional UI (do not crash if missing)
# -------------------------------
render_sla_escalations = None
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


# -------------------------------
# Helpers
# -------------------------------
def call_with_accepted_kwargs(fn, **kwargs):
    """Call fn with only kwargs it accepts (prevents signature drift crashes)."""
    sig = inspect.signature(fn)
    accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return fn(**accepted)


# ============================================================
# Page setup
# ============================================================
st.set_page_config(page_title="Dropship Hub", layout="wide")

# Gates (kept early so nothing renders before access)
require_access(public_review_mode=PUBLIC_REVIEW_MODE)

# -------------------------------
# Paths
# -------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

WORKSPACES_DIR = DATA_DIR / "workspaces"
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

SUPPLIERS_DIR = DATA_DIR / "suppliers"
SUPPLIERS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Sidebar context (tenant, defaults, demo, suppliers)
# ============================================================
ctx = render_sidebar_context(DATA_DIR, WORKSPACES_DIR, SUPPLIERS_DIR)

account_id = ctx["account_id"]
store_id = ctx["store_id"]
platform_hint = ctx["platform_hint"]
default_currency = ctx["default_currency"]
default_promised_ship_days = int(ctx["default_promised_ship_days"])
suppliers_df = ctx["suppliers_df"]
demo_mode_active = bool(ctx["demo_mode"])

# Ensure demo tables exist if demo mode is on
ensure_demo_state(DATA_DIR)


# ============================================================
# Onboarding checklist (still inline for now)
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
# Start here (demo editor)
# ============================================================
st.subheader("Start here")
render_demo_editor()


# ============================================================
# Upload UI (NEW CUT)
# ============================================================
st.divider()
uploads = render_upload_section(key_prefix="uploader")

# Enforce same behavior as old app.py
enforce_demo_or_uploads_ready(demo_mode_active=demo_mode_active, has_uploads=uploads.has_uploads)

f_orders = uploads.f_orders
f_shipments = uploads.f_shipments
f_tracking = uploads.f_tracking


# ============================================================
# Templates (already extracted)
# ============================================================
st.divider()
render_template_downloads()


# ============================================================
# Load raw inputs (demo OR uploads)
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

# Supplier CRM enrichment + missing contact exceptions
followups = enrich_followups_with_suppliers(followups, suppliers_df)
exceptions = add_missing_supplier_contact_exceptions(exceptions, followups)


# ============================================================
# SLA Escalations UI (optional)
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


# ============================================================
# Issue Tracker: per-tenant path + maintenance + OPEN derivation
# ============================================================
ws_root = workspace_root(WORKSPACES_DIR, account_id, store_id)
ws_root.mkdir(parents=True, exist_ok=True)
issue_tracker_path = ws_root / "issue_tracker.json"

with st.sidebar:
    st.divider()
    render_issue_tracker_maintenance(issue_tracker_path, default_prune_days=30, key_prefix="issue_maint")

followups_open = derive_followups_open(followups_full, issue_tracker_path=issue_tracker_path)
followups_open = enrich_followups_with_contact_fields(followups_open, issue_tracker_path=issue_tracker_path)
followups = followups_open


# ============================================================
# Workspaces sidebar (save/load + override outputs)
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
        exceptions=exceptions if isinstance(exceptions, pd.DataFrame) else pd.DataFrame(),
        followups=followups_full if isinstance(followups_full, pd.DataFrame) else pd.DataFrame(),
        order_rollup=order_rollup if isinstance(order_rollup, pd.DataFrame) else pd.DataFrame(),
        line_status_df=line_status_df if isinstance(line_status_df, pd.DataFrame) else pd.DataFrame(),
        kpis=kpis if isinstance(kpis, dict) else {},
        suppliers_df=suppliers_df if isinstance(suppliers_df, pd.DataFrame) else pd.DataFrame(),
    )
)

# Re-derive OPEN from loaded followups_full (if any)
followups_open = derive_followups_open(followups_full, issue_tracker_path=issue_tracker_path)
followups_open = enrich_followups_with_contact_fields(followups_open, issue_tracker_path=issue_tracker_path)
followups = followups_open


# ============================================================
# Urgency + Scorecards
# ============================================================
if exceptions is not None and isinstance(exceptions, pd.DataFrame) and not exceptions.empty and "Urgency" not in exceptions.columns:
    exceptions = add_urgency_column(exceptions)

scorecard = build_supplier_scorecard_from_run(line_status_df, exceptions)


# ============================================================
# Customer impact (optional core)
# ============================================================
customer_impact = pd.DataFrame()
if build_customer_impact_view is not None:
    try:
        customer_impact = build_customer_impact_view(exceptions=exceptions, max_items=50)
    except Exception:
        customer_impact = pd.DataFrame()


# ============================================================
# Daily Ops Pack ZIP (core currently supports scorecards; customer_impact may be added later)
# ============================================================
pack_date = datetime.now().strftime("%Y%m%d")
pack_name = f"daily_ops_pack_{pack_date}.zip"

try:
    # If your core.ops_pack supports customer_impact now (signature drift-safe)
    ops_pack_bytes = call_with_accepted_kwargs(
        make_daily_ops_pack_bytes,
        exceptions=exceptions if isinstance(exceptions, pd.DataFrame) else pd.DataFrame(),
        followups=followups_open if isinstance(followups_open, pd.DataFrame) else pd.DataFrame(),
        order_rollup=order_rollup if isinstance(order_rollup, pd.DataFrame) else pd.DataFrame(),
        line_status_df=line_status_df if isinstance(line_status_df, pd.DataFrame) else pd.DataFrame(),
        kpis=kpis if isinstance(kpis, dict) else {},
        supplier_scorecards=scorecard if isinstance(scorecard, pd.DataFrame) else pd.DataFrame(),
        customer_impact=customer_impact,
    )
except Exception:
    ops_pack_bytes = make_daily_ops_pack_bytes(
        exceptions=exceptions if isinstance(exceptions, pd.DataFrame) else pd.DataFrame(),
        followups=followups_open if isinstance(followups_open, pd.DataFrame) else pd.DataFrame(),
        order_rollup=order_rollup if isinstance(order_rollup, pd.DataFrame) else pd.DataFrame(),
        line_status_df=line_status_df if isinstance(line_status_df, pd.DataFrame) else pd.DataFrame(),
        kpis=kpis if isinstance(kpis, dict) else {},
        supplier_scorecards=scorecard if isinstance(scorecard, pd.DataFrame) else pd.DataFrame(),
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
# Dashboard (still inline for now)
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
# Ops Triage (extracted)
# ============================================================
st.divider()
render_ops_triage(
    exceptions=exceptions if isinstance(exceptions, pd.DataFrame) else pd.DataFrame(),
    ops_pack_bytes=ops_pack_bytes,
    pack_name=pack_name,
    key_prefix="triage",
    top_n=10,
)


# ============================================================
# Ops Outreach (Comms) (still inline for now)
# ============================================================
st.divider()
st.subheader("Ops Outreach (Comms)")

tab1, tab2, tab3 = st.tabs(["Supplier Follow-ups", "Customer Emails", "Comms Pack"])

with tab1:
    st.caption("Supplier-facing outreach based on OPEN follow-ups (unresolved only).")

    followups_for_ops = followups_open if isinstance(followups_open, pd.DataFrame) else pd.DataFrame()
    if followups_for_ops is None or followups_for_ops.empty:
        st.info("No supplier follow-ups needed.")
    else:
        summary_cols = [
            c
            for c in [
                "supplier_name",
                "supplier_email",
                "worst_escalation",
                "urgency",
                "item_count",
                "order_ids",
                "contact_status",
                "follow_up_count",
            ]
            if c in followups_for_ops.columns
        ]
        st.dataframe(
            followups_for_ops[summary_cols] if summary_cols else followups_for_ops,
            use_container_width=True,
            height=220,
        )
        st.caption("Supplier email generator + one-click compose remains inline (we’ll extract next).")

        # Supplier accountability (optional)
        if build_supplier_accountability_view is not None and render_supplier_accountability is not None:
            st.divider()
            st.markdown("#### Supplier Accountability (Auto)")
            try:
                sig = inspect.signature(build_supplier_accountability_view)
                params = list(sig.parameters.keys())
                if "scorecard" in params:
                    accountability = build_supplier_accountability_view(scorecard=scorecard, top_n=10)
                else:
                    accountability = build_supplier_accountability_view(scorecard, 10)
                if isinstance(accountability, pd.DataFrame):
                    render_supplier_accountability(accountability)
                else:
                    render_supplier_accountability(pd.DataFrame(accountability))
            except Exception as e:
                st.warning("Supplier accountability failed to render.")
                st.code(str(e))

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
            st.dataframe(customer_impact, use_container_width=True, height=260)

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
# Exceptions Queue (still inline for now)
# ============================================================
st.divider()
st.subheader("Exceptions Queue (Action this first)")

if exceptions is None or not isinstance(exceptions, pd.DataFrame) or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
    st.dataframe(exceptions, use_container_width=True, height=320)


# ============================================================
# Supplier Scorecards (still inline for now)
# ============================================================
st.divider()
st.subheader("Supplier Scorecards (Performance + Trends)")

if scorecard is None or scorecard.empty:
    st.info("Scorecards require `supplier_name` in your normalized line status data.")
else:
    st.dataframe(scorecard, use_container_width=True, height=320)


# ============================================================
# SLA Escalations panel table (still inline for now)
# ============================================================
if isinstance(escalations_df, pd.DataFrame) and not escalations_df.empty:
    st.divider()
    st.subheader("SLA Escalations (Supplier-level)")
    st.dataframe(escalations_df, use_container_width=True, height=260)
