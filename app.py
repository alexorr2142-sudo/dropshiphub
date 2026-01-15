# app.py
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.issue_tracker import IssueTrackerStore


# ---------------------------
# Robust imports (core/* preferred; fall back to flat files)
# ---------------------------
def _import_or_stop():
    def _try(import_path, name=None):
        try:
            mod = __import__(import_path, fromlist=[name] if name else [])
            return getattr(mod, name) if name else mod
        except Exception:
            return None

    # Normalize / Reconcile / Explain
    normalize_orders = _try("core.normalize", "normalize_orders") or _try("normalize", "normalize_orders")
    normalize_shipments = _try("core.normalize", "normalize_shipments") or _try("normalize", "normalize_shipments")
    normalize_tracking = _try("core.normalize", "normalize_tracking") or _try("normalize", "normalize_tracking")
    reconcile_all = _try("core.reconcile", "reconcile_all") or _try("reconcile", "reconcile_all")
    enhance_explanations = _try("core.explain", "enhance_explanations") or _try("explain", "enhance_explanations")

    if not (normalize_orders and normalize_shipments and normalize_tracking and reconcile_all):
        st.set_page_config(page_title="Dropship Hub", layout="wide")
        st.title("Dropship Hub")
        st.error("Import error: required modules missing (normalize/reconcile).")
        st.stop()

    # Styling + urgency
    copy_button = _try("core.styling", "copy_button")
    add_urgency_column = _try("core.urgency", "add_urgency_column")
    style_exceptions_table = _try("core.urgency", "style_exceptions_table")

    # Feature UIs
    build_daily_action_list = _try("core.actions", "build_daily_action_list")
    render_daily_action_list = _try("ui.actions_ui", "render_daily_action_list")
    build_customer_impact_view = _try("core.customer_impact", "build_customer_impact_view")
    render_customer_impact_view = _try("ui.customer_impact_ui", "render_customer_impact_view")
    render_comms_pack_download = _try("ui.comms_pack_ui", "render_comms_pack_download")
    render_kpi_trends = _try("ui.kpi_trends_ui", "render_kpi_trends")
    build_supplier_accountability_view = _try("core.supplier_accountability", "build_supplier_accountability_view")
    render_supplier_accountability = _try("ui.supplier_accountability_ui", "render_supplier_accountability")
    render_sla_escalations = _try("ui.sla_escalations_ui", "render_sla_escalations")

    # Workspaces / Suppliers / Scorecards / Ops pack
    workspaces = _try("core.workspaces")
    suppliers_crm = _try("core.suppliers_crm")
    scorecards = _try("core.scorecards")
    make_daily_ops_pack_bytes = _try("core.ops_pack", "make_daily_ops_pack_bytes")

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
        build_supplier_accountability_view=build_supplier_accountability_view,
        render_supplier_accountability=render_supplier_accountability,
        render_sla_escalations=render_sla_escalations,
        workspaces=workspaces,
        suppliers_crm=suppliers_crm,
        scorecards=scorecards,
        make_daily_ops_pack_bytes=make_daily_ops_pack_bytes,
    )


MOD = _import_or_stop()


# ---------------------------
# Page setup
# ---------------------------
st.set_page_config(page_title="Dropship Hub", layout="wide")


# ---------------------------
# Access gate
# ---------------------------
def _parse_allowed_emails_from_env() -> list[str]:
    raw = os.getenv("DSH_ALLOWED_EMAILS", "").strip()
    return [e.strip().lower() for e in raw.split(",") if e.strip()] if raw else []


def get_allowed_emails() -> list[str]:
    allowed = []
    try:
        allowed = st.secrets.get("ALLOWED_EMAILS", [])
        if isinstance(allowed, str):
            allowed = [allowed]
        allowed = [str(e).strip().lower() for e in allowed if str(e).strip()]
    except Exception:
        allowed = []
    return sorted(set(allowed + _parse_allowed_emails_from_env()))


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


# ---------------------------
# Paths
# ---------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACES_DIR = DATA_DIR / "workspaces"
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
SUPPLIERS_DIR = DATA_DIR / "suppliers"
SUPPLIERS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------
# Sidebar: settings + CRM + issue tracker maintenance + workspaces
# ---------------------------
with st.sidebar:
    st.header("Plan")
    st.selectbox("Current plan", ["Early Access (Free)", "Pro", "Team"], index=0)

    st.divider()
    st.header("Tenant")
    account_id = st.text_input("account_id", value="demo_account")
    store_id = st.text_input("store_id", value="demo_store")
    platform_hint = st.selectbox("platform hint", ["shopify", "amazon", "etsy", "other"], index=0)

    st.divider()
    st.header("Defaults")
    default_currency = st.text_input("Default currency", value="USD")
    default_promised_ship_days = st.number_input("Default promised ship days (SLA)", 1, 30, 3)

    # Supplier Directory (CRM)
    suppliers_df = pd.DataFrame()
    crm = MOD["suppliers_crm"]
    st.divider()
    st.header("Supplier Directory (CRM)")
    if crm is None:
        st.warning("Supplier CRM modules not found (core/suppliers_crm.py).")
    else:
        if "suppliers_df" not in st.session_state:
            st.session_state["suppliers_df"] = crm.load_suppliers(SUPPLIERS_DIR, account_id, store_id)

        f_suppliers = st.file_uploader("Upload suppliers.csv", type=["csv"], key="suppliers_uploader")
        if f_suppliers is not None:
            try:
                uploaded = pd.read_csv(f_suppliers)
                st.session_state["suppliers_df"] = uploaded
                p = crm.save_suppliers(SUPPLIERS_DIR, account_id, store_id, uploaded)
                st.success(f"Saved ✅ {p.as_posix()}")
            except Exception as e:
                st.error("Failed to read suppliers CSV.")
                st.code(str(e))

        with st.expander("View Supplier Directory", expanded=False):
            suppliers_df_preview = st.session_state.get("suppliers_df", pd.DataFrame())
            if suppliers_df_preview is None or suppliers_df_preview.empty:
                st.caption("Upload suppliers.csv to auto-fill follow-up emails.")
            else:
                cols = [c for c in ["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"] if c in suppliers_df_preview.columns]
                view = suppliers_df_preview[cols] if cols else suppliers_df_preview
                st.dataframe(crm.style_supplier_table(view) if hasattr(crm, "style_supplier_table") else view, use_container_width=True, height=220)

        suppliers_df = st.session_state.get("suppliers_df", pd.DataFrame())

    # Issue tracker maintenance
    st.divider()
    st.header("Issue Tracker Maintenance")
    with st.expander("Maintenance tools", expanded=False):
        store = IssueTrackerStore()
        issue_map = store.load()
        total = len(issue_map)
        resolved = sum(1 for v in issue_map.values() if bool((v or {}).get("resolved", False)))
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", total)
        c2.metric("Resolved", resolved)
        c3.metric("Unresolved", total - resolved)

        prune_days = st.selectbox("Prune resolved older than…", [14, 30, 60, 90], index=1, key="it_prune_days")
        if st.button("🧹 Prune old resolved", use_container_width=True, key="it_prune_btn"):
            removed, remaining = store.prune_resolved(older_than_days=int(prune_days))
            st.success(f"Pruned {removed}. Remaining: {remaining}.")
            st.rerun()

        st.markdown("**Danger zone**")
        confirm_clear = st.checkbox("I understand this cannot be undone", key="it_clear_confirm")
        if st.button("🗑️ Clear ALL resolved", disabled=not confirm_clear, use_container_width=True, key="it_clear_btn"):
            removed, remaining = store.clear_resolved()
            st.success(f"Cleared {removed}. Remaining: {remaining}.")
            st.rerun()


# ---------------------------
# Onboarding
# ---------------------------
st.divider()
with st.expander("Onboarding checklist", expanded=True):
    st.markdown(
        """
1. Click **Try demo data**  
2. Upload **Orders CSV**  
3. Upload **Shipments CSV**  
4. (Optional) Upload **Tracking CSV**  
5. Review **Exceptions** + **Supplier Follow-ups**  
6. (Optional) Upload **suppliers.csv** to auto-fill supplier emails
        """.strip()
    )


# ---------------------------
# Sticky demo mode
# ---------------------------
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

raw_orders = raw_shipments = raw_tracking = None
if use_demo:
    raw_orders = pd.read_csv(DATA_DIR / "raw_orders.csv")
    raw_shipments = pd.read_csv(DATA_DIR / "raw_shipments.csv")
    raw_tracking = pd.read_csv(DATA_DIR / "raw_tracking.csv")
    st.success("Demo data loaded ✅ (sticky mode)")


# ---------------------------
# Uploads + templates
# ---------------------------
st.divider()
st.subheader("Upload your data")
col1, col2, col3 = st.columns(3)
with col1:
    f_orders = st.file_uploader("Orders CSV", type=["csv"], key="upl_orders")
with col2:
    f_shipments = st.file_uploader("Shipments CSV", type=["csv"], key="upl_shipments")
with col3:
    f_tracking = st.file_uploader("Tracking CSV (optional)", type=["csv"], key="upl_tracking")

st.subheader("Download templates")
shipments_template = pd.DataFrame(columns=["Supplier", "Supplier Order ID", "Order ID", "SKU", "Quantity", "Ship Date", "Carrier", "Tracking", "From Country", "To Country"])
tracking_template = pd.DataFrame(columns=["Carrier", "Tracking Number", "Order ID", "Supplier Order ID", "Status", "Last Update", "Delivered At", "Exception"])
suppliers_template = pd.DataFrame(columns=["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"])
t1, t2, t3 = st.columns(3)
t1.download_button("Shipments template CSV", shipments_template.to_csv(index=False).encode("utf-8"), "shipments_template.csv", "text/csv")
t2.download_button("Tracking template CSV", tracking_template.to_csv(index=False).encode("utf-8"), "tracking_template.csv", "text/csv")
t3.download_button("Suppliers template CSV", suppliers_template.to_csv(index=False).encode("utf-8"), "suppliers_template.csv", "text/csv")


# ---------------------------
# Load inputs
# ---------------------------
has_uploads = (f_orders is not None) and (f_shipments is not None)
if not (use_demo or has_uploads):
    st.info("Upload Orders + Shipments, or click **Try demo data** to begin.")
    st.stop()

if not use_demo:
    raw_orders = pd.read_csv(f_orders)
    raw_shipments = pd.read_csv(f_shipments)
    raw_tracking = pd.read_csv(f_tracking) if f_tracking else pd.DataFrame()


# ---------------------------
# Normalize
# ---------------------------
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
if isinstance(raw_tracking, pd.DataFrame) and not raw_tracking.empty:
    tracking, meta_t = MOD["normalize_tracking"](raw_tracking, account_id=account_id, store_id=store_id)

errs = (meta_o or {}).get("validation_errors", []) + (meta_s or {}).get("validation_errors", []) + (meta_t or {}).get("validation_errors", [])
if errs:
    st.warning("Schema issues found (best-effort):")
    for e in errs:
        st.write("- ", e)
else:
    st.success("Looks good ✅")


# ---------------------------
# Reconcile
# ---------------------------
st.divider()
st.subheader("Running reconciliation")
line_status_df, exceptions, followups, order_rollup, kpis = MOD["reconcile_all"](orders, shipments, tracking)

if MOD["enhance_explanations"] is not None:
    try:
        exceptions = MOD["enhance_explanations"](exceptions)
    except Exception:
        pass

# Enrich with CRM
if MOD["suppliers_crm"] is not None:
    try:
        followups = MOD["suppliers_crm"].enrich_followups_with_suppliers(followups, suppliers_df)
        exceptions = MOD["suppliers_crm"].add_missing_supplier_contact_exceptions(exceptions, followups)
    except Exception:
        pass


# ---------------------------
# SLA escalations (updates followups)
# ---------------------------
followups_full = followups
followups_open = followups
escalations_df = pd.DataFrame()

if MOD["render_sla_escalations"] is not None:
    out = MOD["render_sla_escalations"](
        line_status_df=line_status_df,
        followups=followups,
        promised_ship_days=int(default_promised_ship_days),
    )
    # Support both (escalations, full, open) and (escalations, followups)
    if isinstance(out, tuple):
        escalations_df = out[0] if len(out) > 0 else pd.DataFrame()
        followups_full = out[1] if len(out) > 1 else followups
        followups_open = out[2] if len(out) > 2 else followups_full
        followups = followups_open
    else:
        followups = out


# ---------------------------
# Workspaces (optional)
# ---------------------------
runs = []
ws = MOD["workspaces"]
if ws is not None:
    ws_root = ws.workspace_root(WORKSPACES_DIR, account_id, store_id)
    ws_root.mkdir(parents=True, exist_ok=True)
    if "loaded_run" not in st.session_state:
        st.session_state["loaded_run"] = None

    with st.sidebar:
        st.divider()
        st.header("Workspaces")
        workspace_name = st.text_input("Workspace name", value="default", key="ws_name")
        if st.button("💾 Save this run", key="btn_save_run"):
            run_dir = ws.save_run(
                ws_root=ws_root,
                workspace_name=workspace_name,
                account_id=account_id,
                store_id=store_id,
                platform_hint=platform_hint,
                orders=orders,
                shipments=shipments,
                tracking=tracking,
                exceptions=exceptions,
                followups=followups_full,
                order_rollup=order_rollup,
                line_status_df=line_status_df,
                kpis=kpis,
                suppliers_df=suppliers_df,
            )
            st.success(f"Saved ✅ {workspace_name}/{run_dir.name}")
            st.session_state["loaded_run"] = str(run_dir)

        runs = ws.list_runs(ws_root)
        if runs:
            labels = [f"{r['workspace_name']} / {r['run_id']}" for r in runs]
            idx = st.selectbox("Load previous run", list(range(len(runs))), format_func=lambda i: labels[i], key="ws_load_select")
            cL1, cL2 = st.columns(2)
            with cL1:
                if st.button("📂 Load", key="btn_load_run"):
                    st.session_state["loaded_run"] = str(runs[idx]["path"])
                    st.success("Loaded ✅")
            with cL2:
                if st.session_state["loaded_run"]:
                    run_dir = Path(st.session_state["loaded_run"])
                    st.download_button("⬇️ Run Pack", ws.make_run_zip_bytes(run_dir), f"runpack_{run_dir.name}.zip", "application/zip", key="btn_zip_runpack")

            with st.expander("Run history", expanded=False):
                st.dataframe(ws.build_run_history_df(runs), use_container_width=True, height=220)

        if st.session_state.get("loaded_run"):
            loaded = ws.load_run(Path(st.session_state["loaded_run"]))
            exceptions = loaded.get("exceptions", exceptions)
            followups_full = loaded.get("followups", followups_full)
            order_rollup = loaded.get("order_rollup", order_rollup)
            line_status_df = loaded.get("line_status_df", line_status_df)

            loaded_suppliers = loaded.get("suppliers_df", pd.DataFrame())
            if loaded_suppliers is not None and not loaded_suppliers.empty:
                suppliers_df = loaded_suppliers
                st.session_state["suppliers_df"] = loaded_suppliers

            # Re-derive OPEN followups using issue tracker resolved flags (if followups have issue_id)
            store = IssueTrackerStore()
            issue_map = store.load()
            followups_open = followups_full.copy() if followups_full is not None else pd.DataFrame()
            if not followups_open.empty and "issue_id" in followups_open.columns:
                followups_open["_resolved_tmp"] = followups_open["issue_id"].astype(str).map(lambda k: bool(issue_map.get(str(k), {}).get("resolved", False)))
                followups_open = followups_open[followups_open["_resolved_tmp"] == False].drop(columns=["_resolved_tmp"], errors="ignore")
            followups = followups_open

            meta = loaded.get("meta", {}) or {}
            st.info(f"Viewing saved run: **{meta.get('workspace_name','')} / {meta.get('created_at','')}**")


# ---------------------------
# Urgency (optional)
# ---------------------------
if MOD["add_urgency_column"] is not None and exceptions is not None and not exceptions.empty and "Urgency" not in exceptions.columns:
    try:
        exceptions = MOD["add_urgency_column"](exceptions)
    except Exception:
        pass


# ---------------------------
# Scorecards + Ops pack (optional)
# ---------------------------
scorecard = pd.DataFrame()
if MOD["scorecards"] is not None:
    try:
        scorecard = MOD["scorecards"].build_supplier_scorecard_from_run(line_status_df, exceptions)
    except Exception:
        scorecard = pd.DataFrame()

if MOD["make_daily_ops_pack_bytes"] is not None:
    try:
        pack_date = datetime.now().strftime("%Y%m%d")
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
            st.download_button("⬇️ Download Daily Ops Pack ZIP", ops_pack_bytes, f"daily_ops_pack_{pack_date}.zip", "application/zip", use_container_width=True, key="btn_ops_pack")
    except Exception:
        pass


# ---------------------------
# Dashboard KPIs
# ---------------------------
st.divider()
st.subheader("Dashboard")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Order lines", int((kpis or {}).get("total_order_lines", 0)))
k2.metric("% Shipped/Delivered", f"{(kpis or {}).get('pct_shipped_or_delivered', 0)}%")
k3.metric("% Delivered", f"{(kpis or {}).get('pct_delivered', 0)}%")
k4.metric("% Unshipped", f"{(kpis or {}).get('pct_unshipped', 0)}%")
k5.metric("% Late Unshipped", f"{(kpis or {}).get('pct_late_unshipped', 0)}%")


# ---------------------------
# Daily Action List
# ---------------------------
if MOD["build_daily_action_list"] is not None and MOD["render_daily_action_list"] is not None:
    actions = MOD["build_daily_action_list"](exceptions=exceptions, followups=followups_open if followups_open is not None else followups, max_items=10)
    MOD["render_daily_action_list"](actions)


# ---------------------------
# KPI Trends
# ---------------------------
if MOD["render_kpi_trends"] is not None:
    try:
        MOD["render_kpi_trends"](workspaces_dir=WORKSPACES_DIR, account_id=account_id, store_id=store_id)
    except Exception:
        pass


# ---------------------------
# Customer impact + Customer drafts + Comms pack
# ---------------------------
customer_impact = pd.DataFrame()
if MOD["build_customer_impact_view"] is not None:
    try:
        customer_impact = MOD["build_customer_impact_view"](exceptions=exceptions, max_items=50)
    except Exception:
        customer_impact = pd.DataFrame()

if MOD["render_customer_impact_view"] is not None:
    try:
        MOD["render_customer_impact_view"](customer_impact)
    except Exception:
        pass

# Always show customer email drafts if we have drafts
st.divider()
st.subheader("Customer Email Drafts (Copy/Paste Ready)")
if customer_impact is None or customer_impact.empty:
    st.info("No customer-impact items found.")
else:
    draft_col = next((c for c in ["customer_message_draft", "customer_email_draft", "message_draft"] if c in customer_impact.columns), None)
    if not draft_col:
        st.warning("Customer impact is missing a draft column (expected `customer_message_draft`).")
    else:
        idx = st.selectbox(
            "Choose a customer draft",
            list(range(len(customer_impact))),
            format_func=lambda i: f"Order {customer_impact.iloc[i].get('order_id','')}" if "order_id" in customer_impact.columns else f"Row {i}",
            key="customer_email_preview_select",
        )
        r = customer_impact.iloc[int(idx)].to_dict()
        subject = "Update on your order"
        cat = str(r.get("impact_category", "") or "").strip()
        if cat:
            subject = f"Update on your order ({cat})"
        body = str(r.get(draft_col, "") or "")
        if MOD["copy_button"] is not None:
            c1, c2 = st.columns(2)
            c1.button(" ", disabled=True)  # visual spacing on mobile
            with c1:
                MOD["copy_button"](subject, "Copy subject", key=f"copy_customer_subject_{idx}")
            with c2:
                MOD["copy_button"](body, "Copy body", key=f"copy_customer_body_{idx}")
        st.text_input("Subject", value=subject, key="customer_email_subject_preview")
        st.text_area("Body", value=body, height=240, key="customer_email_body_preview")
        oid = str(r.get("order_id", "") or "").strip()
        st.download_button(
            "Download this customer email as .txt",
            data=(f"Subject: {subject}\n\n{body}").encode("utf-8"),
            file_name=f"customer_email_{oid or idx}.txt".replace(" ", "_").lower(),
            mime="text/plain",
            key="btn_customer_email_txt",
        )

if MOD["render_comms_pack_download"] is not None:
    try:
        MOD["render_comms_pack_download"](followups=followups_open if followups_open is not None else followups, customer_impact=customer_impact)
    except Exception:
        pass


# ---------------------------
# Supplier accountability
# ---------------------------
if MOD["build_supplier_accountability_view"] is not None and MOD["render_supplier_accountability"] is not None:
    try:
        view = MOD["build_supplier_accountability_view"](scorecard=scorecard, exceptions=exceptions)
        MOD["render_supplier_accountability"](view)
    except Exception:
        pass


# ---------------------------
# Exceptions queue
# ---------------------------
st.divider()
st.subheader("Exceptions Queue (Action this first)")
if exceptions is None or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        issue_types = sorted(exceptions["issue_type"].dropna().unique().tolist()) if "issue_type" in exceptions.columns else []
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types)
    with c2:
        countries = sorted([c for c in exceptions.get("customer_country", pd.Series([], dtype="object")).dropna().unique().tolist() if str(c).strip()])
        country_filter = st.multiselect("Customer country", countries, default=countries)
    with c3:
        suppliers = sorted([s for s in exceptions.get("supplier_name", pd.Series([], dtype="object")).dropna().unique().tolist() if str(s).strip()])
        supplier_filter = st.multiselect("Supplier", suppliers, default=suppliers)
    with c4:
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

    show_cols = [c for c in [
        "Urgency", "order_id", "sku", "issue_type", "customer_country", "supplier_name",
        "quantity_ordered", "quantity_shipped", "line_status", "explanation", "next_action", "customer_risk"
    ] if c in filtered.columns]
    if "Urgency" in filtered.columns and "order_id" in filtered.columns:
        filtered = filtered.sort_values(["Urgency", "order_id"], ascending=True)

    if MOD["style_exceptions_table"] is not None:
        try:
            st.dataframe(MOD["style_exceptions_table"](filtered[show_cols]), use_container_width=True, height=420)
        except Exception:
            st.dataframe(filtered[show_cols], use_container_width=True, height=420)
    else:
        st.dataframe(filtered[show_cols], use_container_width=True, height=420)

    st.download_button("Download Exceptions CSV", filtered.to_csv(index=False).encode("utf-8"), "exceptions_queue.csv", "text/csv")


# ---------------------------
# Supplier follow-ups + email composer (always visible)
# ---------------------------
st.divider()
st.subheader("Supplier Follow-ups (Copy/Paste Ready)")
followups_for_ops = followups_open if followups_open is not None else followups

if followups_for_ops is None or followups_for_ops.empty:
    st.info("No follow-ups needed.")
else:
    summary_cols = [c for c in ["supplier_name", "supplier_email", "worst_escalation", "urgency", "item_count", "order_ids"] if c in followups_for_ops.columns]
    st.dataframe(followups_for_ops[summary_cols] if summary_cols else followups_for_ops, use_container_width=True, height=220)

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button("Download OPEN Follow-ups CSV", followups_for_ops.to_csv(index=False).encode("utf-8"), "supplier_followups_open.csv", "text/csv")
    with dl2:
        if followups_full is not None and not followups_full.empty:
            st.download_button("Download FULL Follow-ups CSV", followups_full.to_csv(index=False).encode("utf-8"), "supplier_followups_full.csv", "text/csv")

    if "supplier_name" in followups_for_ops.columns:
        st.divider()
        st.markdown("### Email preview (select a supplier)")
        chosen = st.selectbox("Supplier", followups_for_ops["supplier_name"].astype(str).tolist(), key="supplier_email_preview_select")
        row = followups_for_ops[followups_for_ops["supplier_name"] == chosen].iloc[0]

        supplier_email = str(row.get("supplier_email", "") or "")
        subject = str(row.get("subject", "Action required: outstanding shipments") or "")
        body = str(row.get("body", "") or "")

        if MOD["copy_button"] is not None:
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

        st.download_button(
            "Download this supplier email as .txt",
            data=(f"To: {supplier_email}\nSubject: {subject}\n\n{body}").encode("utf-8"),
            file_name=f"supplier_email_{str(chosen).replace(' ', '_').lower()}.txt",
            mime="text/plain",
            key="btn_supplier_email_txt",
        )


# ---------------------------
# Rollup + all lines
# ---------------------------
st.divider()
st.subheader("Order-Level Rollup (One row per order)")
st.dataframe(order_rollup, use_container_width=True, height=320)
st.download_button("Download Order Rollup CSV", order_rollup.to_csv(index=False).encode("utf-8"), "order_rollup.csv", "text/csv")

st.divider()
st.subheader("All Order Lines (Normalized + Status)")
st.dataframe(line_status_df, use_container_width=True, height=380)
st.download_button("Download Line Status CSV", line_status_df.to_csv(index=False).encode("utf-8"), "order_line_status.csv", "text/csv")

st.caption("MVP note: This version uses CSV uploads. Integrations + automation can be added after early-user feedback.")
