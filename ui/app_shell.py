# ui/app_shell.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Callable

import pandas as pd
import streamlit as st


@dataclass
class _ShellDeps:
    # sidebar + onboarding
    render_sidebar_context: Callable[..., dict]
    render_onboarding_checklist: Optional[Callable[..., Any]]

    # inputs + pipeline
    render_upload_and_templates: Callable[..., dict]
    resolve_raw_inputs: Callable[..., tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]
    stop_if_missing_required_inputs: Callable[..., None]
    normalize_inputs: Callable[..., tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]
    reconcile_with_debug: Callable[..., tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]]
    run_pipeline: Callable[..., dict]

    # workspaces + issue tracker path helper
    render_workspaces_sidebar: Optional[Callable[..., Any]]
    workspace_root: Callable[..., Path]
    issue_tracker_path_for_ws_root: Callable[..., Path]

    # views
    render_dashboard: Callable[..., Any]
    render_ops_triage: Callable[..., Any]
    render_exceptions_queue_section: Callable[..., Any]
    render_supplier_scorecards: Callable[..., Any]
    render_ops_outreach_comms: Callable[..., Any]

    # optional UIs
    render_sla_escalations_panel: Optional[Callable[..., Any]]
    render_issue_tracker_ui: Optional[Callable[..., Any]]
    render_kpi_trends: Optional[Callable[..., Any]]

    # paths init (yes, currently in core/)
    init_paths: Callable[..., tuple[Path, Path, Path, Path]]


def _safe_imports() -> _ShellDeps:
    # Sidebar + onboarding
    from ui.sidebar import render_sidebar_context
    try:
        from ui.onboarding_ui import render_onboarding_checklist
    except Exception:
        render_onboarding_checklist = None

    # Inputs + sections
    from ui.app_sections import (
        render_upload_and_templates,
        resolve_raw_inputs,
        stop_if_missing_required_inputs,
        normalize_inputs,
        reconcile_with_debug,
    )
    from ui.app_pipeline import run_pipeline

    # Workspaces + core helpers
    try:
        from ui.workspaces_ui import render_workspaces_sidebar
    except Exception:
        render_workspaces_sidebar = None

    from core.workspaces import workspace_root
    from core.issue_tracker import issue_tracker_path_for_ws_root
    from core.paths import init_paths

    # Views (main tabs)
    from ui.app_views import (
        render_dashboard,
        render_ops_triage,
        render_exceptions_queue_section,
        render_supplier_scorecards,
        render_ops_outreach_comms,
    )

    # Optional views
    try:
        from ui.app_views import render_sla_escalations_panel
    except Exception:
        render_sla_escalations_panel = None

    try:
        from ui.issue_tracker_ui import render_issue_tracker
        render_issue_tracker_ui = render_issue_tracker
    except Exception:
        render_issue_tracker_ui = None

    try:
        from ui.kpi_trends_ui import render_kpi_trends
    except Exception:
        render_kpi_trends = None

    return _ShellDeps(
        render_sidebar_context=render_sidebar_context,
        render_onboarding_checklist=render_onboarding_checklist,
        render_upload_and_templates=render_upload_and_templates,
        resolve_raw_inputs=resolve_raw_inputs,
        stop_if_missing_required_inputs=stop_if_missing_required_inputs,
        normalize_inputs=normalize_inputs,
        reconcile_with_debug=reconcile_with_debug,
        run_pipeline=run_pipeline,
        render_workspaces_sidebar=render_workspaces_sidebar,
        workspace_root=workspace_root,
        issue_tracker_path_for_ws_root=issue_tracker_path_for_ws_root,
        init_paths=init_paths,
        render_dashboard=render_dashboard,
        render_ops_triage=render_ops_triage,
        render_exceptions_queue_section=render_exceptions_queue_section,
        render_supplier_scorecards=render_supplier_scorecards,
        render_ops_outreach_comms=render_ops_outreach_comms,
        render_sla_escalations_panel=render_sla_escalations_panel,
        render_issue_tracker_ui=render_issue_tracker_ui,
        render_kpi_trends=render_kpi_trends,
    )


def render_app() -> None:
    """
    The main app body AFTER access gates.

    app.py should remain an orchestrator; this file owns UI composition.
    """
    deps = _safe_imports()

    # Paths
    base_dir = Path(__file__).resolve().parent.parent
    _base_dir, data_dir, workspaces_dir, suppliers_dir = deps.init_paths(base_dir)

    # Sidebar context (tenant/defaults/demo/suppliers)
    sb = deps.render_sidebar_context(
        data_dir=data_dir,
        workspaces_dir=workspaces_dir,
        suppliers_dir=suppliers_dir,
        key_prefix="sb",
    )

    account_id = str(sb.get("account_id", "") or "")
    store_id = str(sb.get("store_id", "") or "")
    platform_hint = str(sb.get("platform_hint", "other") or "other")
    default_currency = str(sb.get("default_currency", "USD") or "USD")
    promised_days = int(sb.get("default_promised_ship_days", 3) or 3)
    suppliers_df = sb.get("suppliers_df", pd.DataFrame())
    demo_mode = bool(sb.get("demo_mode", False))

    # Optional: onboarding checklist
    if callable(deps.render_onboarding_checklist):
        try:
            deps.render_onboarding_checklist(expanded=True)
        except Exception:
            st.warning("Onboarding checklist failed to render (non-critical).")

    # Uploads + templates (must fail-safe; demo must still run)
    files: Dict[str, Any] = {}
    try:
        maybe_files = deps.render_upload_and_templates()
        if maybe_files is None:
            files = {}
        elif isinstance(maybe_files, dict):
            files = maybe_files
        else:
            st.warning("Uploads UI returned an unexpected type; proceeding without uploads (non-critical).")
            files = {}
    except Exception as e:
        st.warning("Uploads / templates UI failed; proceeding without uploads (non-critical).")
        st.code(str(e))
        files = {}

    # Raw inputs (demo-safe)
    raw_orders, raw_shipments, raw_tracking = deps.resolve_raw_inputs(
        data_dir=data_dir,
        uploaded_orders=files.get("orders_file"),
        uploaded_shipments=files.get("shipments_file"),
        uploaded_tracking=files.get("tracking_file"),
        demo_mode=demo_mode,
    )

    # Stop if required inputs are missing (unless demo)
    deps.stop_if_missing_required_inputs(
        orders_df=raw_orders,
        shipments_df=raw_shipments,
        demo_mode=demo_mode,
    )

    # Normalize + reconcile (debug bundle comes from reconcile_with_debug)
    orders, shipments, tracking = deps.normalize_inputs(raw_orders, raw_shipments, raw_tracking)
    exceptions, followups_full, order_rollup, kpis = deps.reconcile_with_debug(
        orders=orders,
        shipments=shipments,
        tracking=tracking,
        platform_hint=platform_hint,
        default_currency=default_currency,
        promised_ship_days=promised_days,
        suppliers_df=suppliers_df,
    )

    # Issue tracker path is per-tenant
    ws_root = deps.workspace_root(workspaces_dir, account_id, store_id)
    issue_tracker_path = deps.issue_tracker_path_for_ws_root(ws_root)

    # Pipeline (customer impact, scorecards, escalations, mailto packs, etc.)
    pipe = deps.run_pipeline(
        account_id=account_id,
        store_id=store_id,
        platform_hint=platform_hint,
        default_currency=default_currency,
        promised_ship_days=promised_days,
        suppliers_df=suppliers_df,
        orders=orders,
        shipments=shipments,
        tracking=tracking,
        exceptions=exceptions,
        followups_full=followups_full,
        order_rollup=order_rollup,
        kpis=kpis,
        issue_tracker_path=issue_tracker_path,
    )

    # Optional: workspaces sidebar (save/load) can override what we show
    # If missing, we just show the current pipeline output.
    view = dict(pipe)
    if callable(deps.render_workspaces_sidebar):
        try:
            ws_result = deps.render_workspaces_sidebar(
                workspaces_dir=workspaces_dir,
                account_id=account_id,
                store_id=store_id,
                platform_hint=platform_hint,
                default_currency=default_currency,
                promised_ship_days=promised_days,
                suppliers_df=suppliers_df,
                orders=orders,
                shipments=shipments,
                tracking=tracking,
                exceptions=pipe.get("exceptions", exceptions),
                followups_full=pipe.get("followups_full", followups_full),
                order_rollup=pipe.get("order_rollup", order_rollup),
                line_status_df=pipe.get("line_status_df", pd.DataFrame()),
                kpis=pipe.get("kpis", kpis),
            )
            # If user loaded a saved run, prefer those outputs for rendering
            if getattr(ws_result, "loaded_run_dir", None):
                view["exceptions"] = ws_result.exceptions
                view["followups_open"] = ws_result.followups
                view["order_rollup"] = ws_result.order_rollup
                view["line_status_df"] = ws_result.line_status_df
                view["kpis"] = ws_result.kpis
                view["suppliers_df"] = ws_result.suppliers_df
        except Exception as e:
            st.warning("Workspaces sidebar failed (non-critical).")
            st.code(str(e))

    # ---------- Main tabs ----------
    tabs = st.tabs(
        [
            "Dashboard",
            "Ops Triage",
            "Exceptions Queue",
            "Supplier Scorecards",
            "Ops Outreach (Comms)",
            "SLA Escalations",
            "Follow-up Tracker",
            "KPI Trends",
        ]
    )

    with tabs[0]:
        deps.render_dashboard(
            kpis=view.get("kpis", {}),
            run_history_df=view.get("run_history_df", pd.DataFrame()),
        )

    with tabs[1]:
        deps.render_ops_triage(
            exceptions=view.get("exceptions", pd.DataFrame()),
            followups_open=view.get("followups_open", pd.DataFrame()),
        )

    with tabs[2]:
        deps.render_exceptions_queue_section(
            exceptions=view.get("exceptions", pd.DataFrame()),
        )

    with tabs[3]:
        deps.render_supplier_scorecards(
            supplier_scorecards=view.get("supplier_scorecards", pd.DataFrame()),
        )

    with tabs[4]:
        deps.render_ops_outreach_comms(
            followups_open=view.get("followups_open", pd.DataFrame()),
            customer_impact=view.get("customer_impact", pd.DataFrame()),
            mailto_link=view.get("mailto_link", ""),
        )

    with tabs[5]:
        if callable(deps.render_sla_escalations_panel):
            deps.render_sla_escalations_panel(escalations_df=view.get("escalations_df", pd.DataFrame()))
        else:
            st.caption("SLA escalations UI not available.")

    with tabs[6]:
        if callable(deps.render_issue_tracker_ui):
            deps.render_issue_tracker_ui(issue_tracker_path=issue_tracker_path)
        else:
            st.caption("Follow-up tracker UI not available.")

    with tabs[7]:
        if callable(deps.render_kpi_trends):
            try:
                deps.render_kpi_trends(workspaces_dir=workspaces_dir, account_id=account_id, store_id=store_id)
            except Exception as e:
                st.warning("KPI trends UI failed to render (non-critical).")
                st.code(str(e))
        else:
            st.caption("KPI trends UI not available.")
