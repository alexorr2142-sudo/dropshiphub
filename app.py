# app.py
import os
import json
import io
import zipfile
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ✅ NEW: used to keep resolved items resolved even when loading saved runs
from core.issue_tracker import IssueTrackerStore


# ============================================================
# Robust imports (works whether you kept old flat files or moved
# them into /core and /ui packages)
# ============================================================
def _import_or_stop():
    # ---- Normalize / Reconcile / Explain ----
    normalize_orders = normalize_shipments = normalize_tracking = None
    reconcile_all = None
    enhance_explanations = None

    # Prefer new layout: core/*
    try:
        from core.normalize import normalize_orders, normalize_shipments, normalize_tracking  # type: ignore
    except Exception:
        try:
            from normalize import normalize_orders, normalize_shipments, normalize_tracking  # type: ignore
        except Exception as e:
            st.set_page_config(page_title="Dropship Hub", layout="wide")
            st.title("Dropship Hub")
            st.error("Import error: normalize module missing or broken.")
            st.code(str(e))
            st.stop()

    try:
        from core.reconcile import reconcile_all  # type: ignore
    except Exception:
        try:
            from reconcile import reconcile_all  # type: ignore
        except Exception as e:
            st.set_page_config(page_title="Dropship Hub", layout="wide")
            st.title("Dropship Hub")
            st.error("Import error: reconcile module missing or broken.")
            st.code(str(e))
            st.stop()

    try:
        from core.explain import enhance_explanations  # type: ignore
    except Exception:
        try:
            from explain import enhance_explanations  # type: ignore
        except Exception:
            enhance_explanations = None

    # ---- Styling helpers ----
    copy_button = None
    add_urgency_column = None
    style_exceptions_table = None

    try:
        from core.styling import copy_button  # type: ignore
    except Exception:
        copy_button = None

    try:
        from core.urgency import add_urgency_column, style_exceptions_table  # type: ignore
    except Exception:
        add_urgency_column = None
        style_exceptions_table = None

    # ---- Feature UIs ----
    render_daily_action_list = None
    build_daily_action_list = None
    try:
        from core.actions import build_daily_action_list  # type: ignore
        from ui.actions_ui import render_daily_action_list  # type: ignore
    except Exception:
        build_daily_action_list = None
        render_daily_action_list = None

    build_customer_impact_view = None
    render_customer_impact_view = None
    try:
        from core.customer_impact import build_customer_impact_view  # type: ignore
        from ui.customer_impact_ui import render_customer_impact_view  # type: ignore
    except Exception:
        build_customer_impact_view = None
        render_customer_impact_view = None

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

    render_supplier_accountability = None
    try:
        from ui.supplier_accountability_ui import render_supplier_accountability  # type: ignore
    except Exception:
        render_supplier_accountability = None

    build_supplier_accountability_view = None
    try:
        from core.supplier_accountability import build_supplier_accountability_view  # type: ignore
    except Exception:
        build_supplier_accountability_view = None

    # ✅ SLA Escalations + Issue Tracker UI
    render_sla_escalations = None
    try:
        from ui.sla_escalations_ui import render_sla_escalations  # type: ignore
    except Exception:
        render_sla_escalations = None

    # ---- Workspaces / Suppliers / Scorecards / Ops pack ----
    try:
        from core.workspaces import (
            workspace_root,
            list_runs,
            save_run,
            load_run,
            make_run_zip_bytes,
            delete_run_dir,
            build_run_history_df,
        )  # type: ignore
    except Exception:
        workspace_root = list_runs = save_run = load_run = make_run_zip_bytes = delete_run_dir = build_run_history_df = None

    try:
        from core.suppliers_crm import (
            load_suppliers,
            save_suppliers,
            style_supplier_table,
            enrich_followups_with_suppliers,
            add_missing_supplier_contact_exceptions,
        )  # type: ignore
    except Exception:
        load_suppliers = save_suppliers = style_supplier_table = None
        enrich_followups_with_suppliers = add_missing_supplier_contact_exceptions = None

    try:
        from core.scorecards import build_supplier_scorecard_from_run, load_recent_scorecard_history  # type: ignore
    except Exception:
        build_supplier_scorecard_from_run = None
        load_recent_scorecard_history = None

    try:
        from core.ops_pack import make_daily_ops_pack_bytes  # type: ignore
    except Exception:
        make_daily_ops_pack_bytes = None

    return dict(
        normalize_orders=normalize_orders,
        normalize_shipments=normalize_shipments,
        normalize_tracking=normalize_tracking,
        reconcile_all=reconcile_all,
        enhance_explanations=enhance_explanations,
        copy_button=copy_button,
        add_urgency_column=add_urgency_column,
        style_exceptions_table=style_exceptions_table,
        build_daily_action_list=build_daily_action_list,
        render_daily_action_list=render_daily_action_list,
        build_customer_impact_view=build_customer_impact_view,
        render_customer_impact_view=render_customer_impact_view,
        render_comms_pack_download=render_comms_pack_download,
        render_kpi_trends=render_kpi_trends,
        render_supplier_accountability=render_supplier_accountability,
        build_supplier_accountability_view=build_supplier_accountability_view,
        render_sla_escalations=render_sla_escalations,
        workspace_root=workspace_root,
        list_runs=list_runs,
        save_run=save_run,
        load_run=load_run,
        make_run_zip_bytes=make_run_zip_bytes,
        delete_run_dir=delete_run_dir,
        build_run_history_df=build_run_history_df,
        load_suppliers=load_suppliers,
        save_suppliers=save_suppliers,
        style_supplier_table=style_supplier_table,
        enrich_followups_with_suppliers=enrich_followups_with_suppliers,
        add_missing_supplier_contact_exceptions=add_missing_supplier_contact_exceptions,
        build_supplier_scorecard_from_run=build_supplier_scorecard_from_run,
        load_recent_scorecard_history=load_recent_scorecard_history,
        make_daily_ops_pack_bytes=make_daily_ops_pack_bytes,
    )


MOD = _import_or_stop()


# ============================================================
# Page setup
# ============================================================
st.set_page_config(page_title="Dropship Hub", layout="wide")


# ============================================================
# Early Access Gate
# ============================================================
def _parse_allowed_emails_from_env() -> list[str]:
    raw = os.getenv("DSH_ALLOWED_EMAILS", "").strip()
    if not raw:
        return []
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def get_allowed_emails() -> list[str]:
    allowed = []
    try:
        allowed = st.secrets.get("ALLOWED_EMAILS", [])
        if isinstance(allowed, str):
            allowed = [allowed]
        allowed = [str(e).strip().lower() for e in allowed if str(e).strip()]
    except Exception:
        allowed = []
    allowed_env = _parse_allowed_emails_from_env()
    return sorted(set(allowed + allowed_env))


def require_email_access_gate():
    st.subheader("Access")
    email = st.text_input("Work email", key="auth_email").strip().lower()
    allowed = get_allowed_emails()

    if allowed:
        if not email:
            st.info("Enter your work email to continue.")
            st.stop()
        if email not in allowed:
            st.error("This email is not authorized for early access.")
            st.caption("Ask the admin to add your email to the allowlist.")
            st.stop()
        st.success("Email verified ✅")
    else:
        st.caption("Email verification is currently disabled (accepting all emails).")


ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")
st.title("Dropship Hub — Early Access")
st.caption("Drop ship made easy — exceptions, follow-ups, and visibility in one hub.")

code = st.text_input("Enter early access code", type="password", key="access_code")
if code != ACCESS_CODE:
    st.info("This app is currently in early access. Enter your code to continue.")
    st.stop()

require_email_access_gate()


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
# Sidebar: plan + tenant + defaults + Supplier CRM
# ============================================================
with st.sidebar:
    st.header("Plan")
    _ = st.selectbox("Current plan", ["Early Access (Free)", "Pro", "Team"], index=0)
    with st.expander("Upgrade / Pricing (placeholder)", expanded=False):
        st.markdown(
            """
**Early Access (Free)**
- CSV uploads
- Exceptions + supplier follow-ups
- Supplier Directory (CRM)
- Supplier scorecards

**Pro**
- Saved workspaces + run history
- Automations (coming soon)

**Team**
- Role-based access (coming soon)
- Audit trail (coming soon)
            """.strip()
        )

    st.divider()
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
    st.header("Supplier Directory (CRM)")

    if MOD["load_suppliers"] is None:
        st.warning("Supplier CRM modules not found (core/suppliers_crm.py).")
        suppliers_df = pd.DataFrame()
    else:
        if "suppliers_df" not in st.session_state:
            st.session_state["suppliers_df"] = MOD["load_suppliers"](SUPPLIERS_DIR, account_id, store_id)

        f_suppliers = st.file_uploader("Upload suppliers.csv", type=["csv"], key="suppliers_uploader")
        if f_suppliers is not None:
            try:
                uploaded_suppliers = pd.read_csv(f_suppliers)
                st.session_state["suppliers_df"] = uploaded_suppliers
                p = MOD["save_suppliers"](SUPPLIERS_DIR, account_id, store_id, uploaded_suppliers)
                st.success(f"Saved ✅ {p.as_posix()}")
            except Exception as e:
                st.error("Failed to read suppliers CSV.")
                st.code(str(e))

        with st.expander("View Supplier Directory", expanded=False):
            suppliers_df_preview = st.session_state.get("suppliers_df", pd.DataFrame())
            if suppliers_df_preview is None or suppliers_df_preview.empty:
                st.caption("No supplier directory loaded yet. Upload suppliers.csv to auto-fill follow-up emails.")
            else:
                show_cols = [c for c in ["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"] if c in suppliers_df_preview.columns]
                if not show_cols:
                    st.dataframe(suppliers_df_preview, use_container_width=True, height=220)
                else:
                    styler = MOD["style_supplier_table"](suppliers_df_preview[show_cols]) if MOD["style_supplier_table"] else suppliers_df_preview[show_cols]
                    st.dataframe(styler, use_container_width=True, height=220)

                if "supplier_email" in suppliers_df_preview.columns:
                    missing_emails = suppliers_df_preview["supplier_email"].fillna("").astype(str).str.strip().eq("").sum()
                    st.caption(f"Missing supplier_email: {int(missing_emails)} row(s)")

        st.caption("Tip: Upload suppliers.csv once per account/store to auto-fill follow-up emails.")

    suppliers_df = st.session_state.get("suppliers_df", pd.DataFrame())


# ============================================================
# Onboarding checklist
# ============================================================
st.divider()
with st.expander("Onboarding checklist", expanded=True):
    st.markdown(
        """
1. Click **Try demo data** to see the workflow instantly  
2. Upload **Orders CSV** (Shopify export)  
3. Upload **Shipments CSV** (supplier / agent export)  
4. (Optional) Upload **Tracking CSV**  
5. Review **Exceptions** and use **Supplier Follow-ups** to message suppliers  
6. (Optional) Upload **suppliers.csv** in the sidebar to auto-fill supplier emails  
        """.strip()
    )


# ============================================================
# Demo Mode (✅ STICKY)
# ============================================================
st.subheader("Start here")

if "use_demo" not in st.session_state:
    st.session_state["use_demo"] = False

c_demo1, c_demo2 = st.columns([1, 2])
with c_demo1:
    if st.button("Try demo data (no uploads)", key="btn_use_demo"):
        st.session_state["use_demo"] = True
with c_demo2:
    if st.session_state["use_demo"]:
        if st.button("Reset demo mode", key="btn_reset_demo"):
            st.session_state["use_demo"] = False
            st.rerun()

use_demo = bool(st.session_state["use_demo"])

raw_orders = None
raw_shipments = None
raw_tracking = None

if use_demo:
    try:
        raw_orders = pd.read_csv(DATA_DIR / "raw_orders.csv")
        raw_shipments = pd.read_csv(DATA_DIR / "raw_shipments.csv")
        raw_tracking = pd.read_csv(DATA_DIR / "raw_tracking.csv")
        st.success("Demo data loaded ✅ (sticky mode)")
    except Exception as e:
        st.error("Couldn't load demo data. Make sure data/raw_orders.csv, raw_shipments.csv, raw_tracking.csv exist.")
        st.code(str(e))
        st.stop()


# ============================================================
# Upload section
# ============================================================
st.divider()
st.subheader("Upload your data")

col1, col2, col3 = st.columns(3)
with col1:
    f_orders = st.file_uploader("Orders CSV (Shopify export or generic)", type=["csv"], key="upl_orders")
with col2:
    f_shipments = st.file_uploader("Shipments CSV (supplier export)", type=["csv"], key="upl_shipments")
with col3:
    f_tracking = st.file_uploader("Tracking CSV (optional)", type=["csv"], key="upl_tracking")


# ============================================================
# Template downloads
# ============================================================
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
suppliers_template = pd.DataFrame(columns=["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"])

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


# ============================================================
# Run pipeline: demo OR uploads
# ============================================================
has_uploads = (f_orders is not None) and (f_shipments is not None)
if not (use_demo or has_uploads):
    st.info("Upload Orders + Shipments, or click **Try demo data** to begin.")
    st.stop()

if not use_demo:
    try:
        raw_orders = pd.read_csv(f_orders)
        raw_shipments = pd.read_csv(f_shipments)
        raw_tracking = pd.read_csv(f_tracking) if f_tracking else pd.DataFrame()
    except Exception as e:
        st.error("Failed to read one of your CSV uploads.")
        st.code(str(e))
        st.stop()


# ============================================================
# Normalize
# ============================================================
st.divider()
st.subheader("Data checks")

orders, meta_o = MOD["normalize_orders"](
    raw_orders,
    account_id=account_id,
    store_id=store_id,
    platform_hint=platform_hint,
    default_currency=default_currency,
    default_promised_ship_days=int(default_promised_ship_days),
)
shipments, meta_s = MOD["normalize_shipments"](raw_shipments, account_id=account_id, store_id=store_id)

tracking = pd.DataFrame()
meta_t = {"validation_errors": []}
if raw_tracking is not None and isinstance(raw_tracking, pd.DataFrame) and not raw_tracking.empty:
    tracking, meta_t = MOD["normalize_tracking"](raw_tracking, account_id=account_id, store_id=store_id)

errs = (meta_o or {}).get("validation_errors", []) + (meta_s or {}).get("validation_errors", []) + (meta_t or {}).get("validation_errors", [])
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

try:
    line_status_df, exceptions, followups, order_rollup, kpis = MOD["reconcile_all"](orders, shipments, tracking)
except Exception as e:
    st.error("Reconciliation failed. This usually means a required column is missing after normalization.")
    st.code(str(e))
    st.stop()

# AI explanations (safe fallback)
if MOD["enhance_explanations"] is not None:
    try:
        exceptions = MOD["enhance_explanations"](exceptions)
    except Exception:
        pass

# Enrich followups with supplier CRM + add missing supplier contact exceptions
if MOD["enrich_followups_with_suppliers"] is not None:
    followups = MOD["enrich_followups_with_suppliers"](followups, suppliers_df)
if MOD["add_missing_supplier_contact_exceptions"] is not None:
    exceptions = MOD["add_missing_supplier_contact_exceptions"](exceptions, followups)


# ============================================================
# SLA Escalations + Issue Tracker
# Place this AFTER followups exist and AFTER CRM enrichment
# ============================================================
followups_full = followups  # full snapshot (includes issue_id + notes/resolved when available)
followups_open = followups  # operational list (unresolved only)

if MOD["render_sla_escalations"] is not None:
    try:
        escalations_df, followups_full, followups_open = MOD["render_sla_escalations"](
            line_status_df=line_status_df,
            followups=followups,
            promised_ship_days=int(default_promised_ship_days),
        )
        followups = followups_open  # downstream behavior uses open-only
    except TypeError:
        out = MOD["render_sla_escalations"](
            line_status_df=line_status_df,
            followups=followups,
            promised_ship_days=int(default_promised_ship_days),
        )
        if isinstance(out, tuple) and len(out) >= 2:
            followups_full = out[1]
            followups_open = out[1]
            followups = out[1]
        else:
            followups_full = out
            followups_open = out
            followups = out
else:
    st.warning("SLA escalations UI not found. Create ui/sla_escalations_ui.py + core/sla_escalations.py to enable.")


# ============================================================
# Workspaces UI (optional, if you have core/workspaces.py)
# ============================================================
runs = []
if MOD["workspace_root"] is not None:
    ws_root = MOD["workspace_root"](WORKSPACES_DIR, account_id, store_id)
    ws_root.mkdir(parents=True, exist_ok=True)

    if "loaded_run" not in st.session_state:
        st.session_state["loaded_run"] = None

    with st.sidebar:
        st.divider()
        st.header("Workspaces")

        workspace_name = st.text_input("Workspace name", value="default", key="ws_name")

        if st.button("💾 Save this run", key="btn_save_run"):
            run_dir = MOD["save_run"](
                ws_root=ws_root,
                workspace_name=workspace_name,
                account_id=account_id,
                store_id=store_id,
                platform_hint=platform_hint,
                orders=orders,
                shipments=shipments,
                tracking=tracking,
                exceptions=exceptions,
                followups=followups_full,  # ✅ save full snapshot
                order_rollup=order_rollup,
                line_status_df=line_status_df,
                kpis=kpis,
                suppliers_df=suppliers_df,
            )
            st.success(f"Saved ✅ {workspace_name}/{run_dir.name}")
            st.session_state["loaded_run"] = str(run_dir)

        runs = MOD["list_runs"](ws_root)

        if runs:
            run_labels = [
                f"{r['workspace_name']} / {r['run_id']}  (exceptions: {r.get('meta', {}).get('row_counts', {}).get('exceptions', '?')})"
                for r in runs
            ]
            chosen_idx = st.selectbox(
                "Load previous run",
                options=list(range(len(runs))),
                format_func=lambda i: run_labels[i],
                key="ws_load_select",
            )

            cL1, cL2 = st.columns(2)
            with cL1:
                if st.button("📂 Load", key="btn_load_run"):
                    st.session_state["loaded_run"] = str(runs[chosen_idx]["path"])
                    st.success("Loaded ✅")
            with cL2:
                if st.session_state["loaded_run"]:
                    run_dir = Path(st.session_state["loaded_run"])
                    zip_bytes = MOD["make_run_zip_bytes"](run_dir)
                    st.download_button(
                        "⬇️ Run Pack",
                        data=zip_bytes,
                        file_name=f"runpack_{run_dir.parent.name}_{run_dir.name}.zip",
                        mime="application/zip",
                        key="btn_zip_runpack",
                    )

            with st.expander("Run history", expanded=False):
                history_df = MOD["build_run_history_df"](runs)
                st.dataframe(history_df, use_container_width=True, height=220)

                st.divider()
                st.markdown("**Delete a saved run**")
                delete_idx = st.selectbox(
                    "Select run to delete",
                    options=list(range(len(runs))),
                    format_func=lambda i: f"{runs[i]['workspace_name']} / {runs[i]['run_id']}",
                    key="ws_delete_select",
                )
                confirm = st.checkbox("I understand this cannot be undone", key="ws_delete_confirm")
                if st.button("🗑️ Delete run", disabled=not confirm, key="btn_delete_run"):
                    target = Path(runs[delete_idx]["path"])
                    loaded_path = st.session_state.get("loaded_run")
                    MOD["delete_run_dir"](target)
                    if loaded_path and Path(loaded_path) == target:
                        st.session_state["loaded_run"] = None
                    st.success("Deleted ✅")
                    st.rerun()
        else:
            st.caption("No saved runs yet. Click **Save this run** to create your first run history entry.")

    # ✅ If a run is loaded, override outputs (+ suppliers snapshot if present)
    if st.session_state.get("loaded_run"):
        loaded = MOD["load_run"](Path(st.session_state["loaded_run"]))
        exceptions = loaded.get("exceptions", exceptions)

        # ✅ Load full snapshot
        followups_full = loaded.get("followups", followups_full)

        # ✅ NEW: Re-derive OPEN followups using issue_tracker.json
        store = IssueTrackerStore()
        issue_map = store.load()

        followups_open = followups_full.copy() if followups_full is not None else pd.DataFrame()
        if followups_open is not None and not followups_open.empty and "issue_id" in followups_open.columns:
            followups_open["_resolved_tmp"] = followups_open["issue_id"].map(
                lambda k: bool(issue_map.get(str(k), {}).get("resolved", False))
            )
            followups_open = followups_open[followups_open["_resolved_tmp"] == False].copy()
            followups_open = followups_open.drop(columns=["_resolved_tmp"], errors="ignore")

        # ✅ Operational followups everywhere else should be open-only
        followups = followups_open

        order_rollup = loaded.get("order_rollup", order_rollup)
        line_status_df = loaded.get("line_status_df", line_status_df)

        loaded_suppliers = loaded.get("suppliers_df", pd.DataFrame())
        if loaded_suppliers is not None and not loaded_suppliers.empty:
            suppliers_df = loaded_suppliers
            st.session_state["suppliers_df"] = loaded_suppliers

        meta = loaded.get("meta", {}) or {}
        st.info(f"Viewing saved run: **{meta.get('workspace_name','')} / {meta.get('created_at','')}**")


# ============================================================
# Urgency (if you have a module for it)
# ============================================================
if MOD["add_urgency_column"] is not None and exceptions is not None and not exceptions.empty and "Urgency" not in exceptions.columns:
    try:
        exceptions = MOD["add_urgency_column"](exceptions)
    except Exception:
        pass


# ============================================================
# Scorecards + Ops Pack (optional)
# ============================================================
scorecard = pd.DataFrame()
if MOD["build_supplier_scorecard_from_run"] is not None:
    try:
        scorecard = MOD["build_supplier_scorecard_from_run"](line_status_df, exceptions)
    except Exception:
        scorecard = pd.DataFrame()

if MOD["make_daily_ops_pack_bytes"] is not None:
    try:
        pack_date = datetime.now().strftime("%Y%m%d")
        pack_name = f"daily_ops_pack_{pack_date}.zip"
        ops_pack_bytes = MOD["make_daily_ops_pack_bytes"](
            exceptions=exceptions if exceptions is not None else pd.DataFrame(),
            followups=followups_open if followups_open is not None else (followups if followups is not None else pd.DataFrame()),
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


# ============================================================
# Feature: Daily Action List
# ============================================================
if MOD["build_daily_action_list"] is not None and MOD["render_daily_action_list"] is not None:
    actions = MOD["build_daily_action_list"](
        exceptions=exceptions,
        followups=followups_open if followups_open is not None else followups,
        max_items=10,
    )
    MOD["render_daily_action_list"](actions)


# ============================================================
# Feature: KPI Trends (from saved runs)
# ============================================================
if MOD["render_kpi_trends"] is not None:
    try:
        MOD["render_kpi_trends"](
            workspaces_dir=WORKSPACES_DIR,
            account_id=account_id,
            store_id=store_id,
        )
    except TypeError:
        pass


# ============================================================
# Feature: Customer Impact + Bulk Comms Pack
# ============================================================
customer_impact = pd.DataFrame()
if MOD["build_customer_impact_view"] is not None:
    try:
        customer_impact = MOD["build_customer_impact_view"](exceptions=exceptions, max_items=50)
    except Exception:
        customer_impact = pd.DataFrame()

if MOD["render_customer_impact_view"] is not None:
    MOD["render_customer_impact_view"](customer_impact)

if MOD["render_comms_pack_download"] is not None:
    MOD["render_comms_pack_download"](
        followups=followups_open if followups_open is not None else followups,
        customer_impact=customer_impact,
    )


# ============================================================
# Supplier Accountability
# ============================================================
if MOD["build_supplier_accountability_view"] is not None and MOD["render_supplier_accountability"] is not None:
    try:
        accountability_view = MOD["build_supplier_accountability_view"](scorecard=scorecard, exceptions=exceptions)
        MOD["render_supplier_accountability"](accountability_view)
    except Exception:
        pass


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
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types)

    with fcol2:
        countries = sorted([c for c in exceptions.get("customer_country", pd.Series([], dtype="object")).dropna().unique().tolist() if str(c).strip() != ""])
        country_filter = st.multiselect("Customer country", countries, default=countries)

    with fcol3:
        suppliers = sorted([s for s in exceptions.get("supplier_name", pd.Series([], dtype="object")).dropna().unique().tolist() if str(s).strip() != ""])
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
        filtered = filtered[filtered["Urgency"].astype(str).isin(urgency_filter)]

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

    if MOD["style_exceptions_table"] is not None:
        try:
            st.dataframe(MOD["style_exceptions_table"](filtered[show_cols]), use_container_width=True, height=420)
        except Exception:
            st.dataframe(filtered[show_cols], use_container_width=True, height=420)
    else:
        st.dataframe(filtered[show_cols], use_container_width=True, height=420)

    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
    )


# ============================================================
# Supplier Follow-ups (Copy/Paste Ready)
# ============================================================
st.divider()
st.subheader("Supplier Follow-ups (Copy/Paste Ready)")

followups_for_ops = followups_open if followups_open is not None else followups

if followups_for_ops is None or followups_for_ops.empty:
    st.info("No follow-ups needed.")
else:
    summary_cols = [c for c in ["supplier_name", "supplier_email", "worst_escalation", "urgency", "item_count", "order_ids"] if c in followups_for_ops.columns]
    if summary_cols:
        st.dataframe(followups_for_ops[summary_cols], use_container_width=True, height=220)
    else:
        st.dataframe(followups_for_ops, use_container_width=True, height=220)

    cdl1, cdl2 = st.columns(2)
    with cdl1:
        st.download_button(
            "Download OPEN Follow-ups CSV (Unresolved)",
            data=followups_for_ops.to_csv(index=False).encode("utf-8"),
            file_name="supplier_followups_open.csv",
            mime="text/csv",
        )
    with cdl2:
        if followups_full is not None and not followups_full.empty:
            st.download_button(
                "Download FULL Follow-ups CSV (Includes resolved/notes)",
                data=followups_full.to_csv(index=False).encode("utf-8"),
                file_name="supplier_followups_full.csv",
                mime="text/csv",
            )

    if MOD["copy_button"] is not None and "supplier_name" in followups_for_ops.columns and "body" in followups_for_ops.columns and len(followups_for_ops) > 0:
        st.divider()
        st.markdown("### Email preview (select a supplier)")

        chosen = st.selectbox("Supplier", followups_for_ops["supplier_name"].tolist(), key="supplier_email_preview_select")
        row = followups_for_ops[followups_for_ops["supplier_name"] == chosen].iloc[0]

        supplier_email = row.get("supplier_email", "")
        subject = row.get("subject", "Action required: outstanding shipments")
        body = row.get("body", "")

        c1, c2, c3 = st.columns(3)
        with c1:
            MOD["copy_button"](supplier_email, "Copy supplier email", key=f"copy_supplier_email_{chosen}")
        with c2:
            MOD["copy_button"](subject, "Copy subject", key=f"copy_subject_{chosen}")
        with c3:
            MOD["copy_button"](body, "Copy body", key=f"copy_body_{chosen}")

        st.text_input("To (supplier email)", value=supplier_email, key="email_to_preview")
        st.text_input("Subject", value=subject, key="email_subject_preview")
        st.text_area("Body", value=body, height=260, key="email_body_preview")


# ============================================================
# Order-level rollup
# ============================================================
st.divider()
st.subheader("Order-Level Rollup (One row per order)")
st.dataframe(order_rollup, use_container_width=True, height=320)
st.download_button(
    "Download Order Rollup CSV",
    data=order_rollup.to_csv(index=False).encode("utf-8"),
    file_name="order_rollup.csv",
    mime="text/csv",
)


# ============================================================
# All order lines
# ============================================================
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
