# ui/app_shell.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Callable
import inspect
import re

import pandas as pd
import streamlit as st


@dataclass
class _ShellDeps:
    # sidebar + onboarding
    render_sidebar_context: Callable[..., dict]
    render_onboarding_checklist: Optional[Callable[..., Any]]

    # inputs (sections)
    render_upload_and_templates: Callable[..., Any]
    resolve_raw_inputs: Callable[..., Any]
    stop_if_missing_required_inputs: Callable[..., Any]

    # pipeline runner (raw -> everything)
    run_pipeline: Callable[..., Any]

    # required pipeline callables
    normalize_orders: Callable[..., Any]
    normalize_shipments: Callable[..., Any]
    normalize_tracking: Callable[..., Any]
    reconcile_all: Callable[..., Any]
    enhance_explanations: Callable[..., Any]

    enrich_followups_with_suppliers: Callable[..., Any]
    add_missing_supplier_contact_exceptions: Callable[..., Any]
    add_urgency_column: Callable[..., Any]
    build_supplier_scorecard_from_run: Callable[..., Any]
    make_daily_ops_pack_bytes: Callable[..., Any]

    workspace_root: Callable[..., Path]

    # optional pipeline callables
    render_sla_escalations: Optional[Callable[..., Any]]
    apply_issue_tracker: Optional[Callable[..., Any]]
    render_issue_tracker_maintenance: Optional[Callable[..., Any]]
    IssueTrackerStore: Optional[Any]
    build_customer_impact_view: Optional[Callable[..., Any]]
    mailto_link: Optional[Callable[..., Any]]
    render_workspaces_sidebar_and_maybe_override_outputs: Optional[Callable[..., Any]]

    # views
    render_dashboard: Callable[..., Any]
    render_ops_triage: Callable[..., Any]
    render_exceptions_queue_section: Callable[..., Any]
    render_supplier_scorecards: Callable[..., Any]
    render_ops_outreach_comms: Callable[..., Any]

    # optional tab UIs
    render_sla_escalations_panel: Optional[Callable[..., Any]]
    render_issue_tracker_ui: Optional[Callable[..., Any]]
    render_kpi_trends: Optional[Callable[..., Any]]
    render_workspaces_sidebar: Optional[Callable[..., Any]]

    # paths init (yes, currently in core/)
    init_paths: Callable[..., tuple[Path, Path, Path, Path]]


_UNEXPECTED_KW_RE = re.compile(r"unexpected keyword argument '([^']+)'")


def _call_with_accepted_kwargs(fn: Callable[..., Any], **kwargs):
    """
    Backward-compat call helper:

    1) Prefer signature-based filtering when possible.
    2) If signature introspection fails OR the function still raises
       "unexpected keyword argument", iteratively drop the offending kw
       and retry a few times.

    This keeps old/new API surfaces compatible without hiding real errors.
    """
    filtered = dict(kwargs)
    try:
        sig = inspect.signature(fn)
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return fn(**filtered)
    except TypeError as e:
        msg = str(e)
        m = _UNEXPECTED_KW_RE.search(msg)
        if not m:
            raise
        filtered = dict(kwargs)
    except Exception:
        filtered = dict(kwargs)

    max_retries = 12
    last_err: Optional[Exception] = None
    for _ in range(max_retries):
        try:
            return fn(**filtered)
        except TypeError as e:
            msg = str(e)
            m = _UNEXPECTED_KW_RE.search(msg)
            if not m:
                raise
            bad_kw = m.group(1)
            if bad_kw not in filtered:
                raise
            filtered.pop(bad_kw, None)
            last_err = e

    if last_err:
        raise last_err
    return fn(**filtered)


def _require_import(name: str, import_attempts: list[Callable[[], Any]]) -> Any:
    """
    Try a list of import attempt callables. If none work, stop with a clear error.
    This avoids guessing paths silently and keeps the failure obvious.
    """
    last: Optional[Exception] = None
    for attempt in import_attempts:
        try:
            v = attempt()
            if v is not None:
                return v
        except Exception as e:
            last = e

    st.error(f"Import error: required dependency '{name}' could not be imported.")
    if last:
        st.code(str(last))
    st.stop()


def _safe_imports() -> _ShellDeps:
    # Sidebar + onboarding
    from ui.sidebar import render_sidebar_context
    try:
        from ui.onboarding_ui import render_onboarding_checklist
    except Exception:
        render_onboarding_checklist = None

    # Sections (uploads / raw input resolution)
    from ui import app_sections as sections

    # Pipeline runner
    from ui.app_pipeline import run_pipeline

    # Core paths + workspaces
    from core.paths import init_paths
    from core.workspaces import workspace_root

    # Views (main tabs)
    from ui.app_views import (
        render_dashboard,
        render_ops_triage,
        render_exceptions_queue_section,
        render_supplier_scorecards,
        render_ops_outreach_comms,
    )

    # Optional tab UIs
    try:
        from ui.app_views import render_sla_escalations_panel
    except Exception:
        render_sla_escalations_panel = None

    try:
        from ui.issue_tracker_ui import render_issue_tracker as render_issue_tracker_ui
    except Exception:
        render_issue_tracker_ui = None

    try:
        from ui.kpi_trends_ui import render_kpi_trends
    except Exception:
        render_kpi_trends = None

    # Optional workspaces sidebar (UI)
    try:
        from ui.workspaces_ui import render_workspaces_sidebar
    except Exception:
        render_workspaces_sidebar = None

    # ---------- Required pipeline deps ----------
    normalize_orders = _require_import(
        "normalize_orders",
        [
            lambda: __import__("normalize", fromlist=["normalize_orders"]).normalize_orders,
            lambda: __import__("core.normalize", fromlist=["normalize_orders"]).normalize_orders,
        ],
    )
    normalize_shipments = _require_import(
        "normalize_shipments",
        [
            lambda: __import__("normalize", fromlist=["normalize_shipments"]).normalize_shipments,
            lambda: __import__("core.normalize", fromlist=["normalize_shipments"]).normalize_shipments,
        ],
    )
    normalize_tracking = _require_import(
        "normalize_tracking",
        [
            lambda: __import__("normalize", fromlist=["normalize_tracking"]).normalize_tracking,
            lambda: __import__("core.normalize", fromlist=["normalize_tracking"]).normalize_tracking,
        ],
    )
    reconcile_all = _require_import(
        "reconcile_all",
        [
            lambda: __import__("reconcile", fromlist=["reconcile_all"]).reconcile_all,
            lambda: __import__("core.reconcile", fromlist=["reconcile_all"]).reconcile_all,
        ],
    )
    enhance_explanations = _require_import(
        "enhance_explanations",
        [
            lambda: __import__("explain", fromlist=["enhance_explanations"]).enhance_explanations,
            lambda: __import__("core.explain", fromlist=["enhance_explanations"]).enhance_explanations,
        ],
    )

    # The rest are required by run_pipeline() but project paths vary.
    # We try common locations; if missing, we stop with a clear message.
    enrich_followups_with_suppliers = _require_import(
        "enrich_followups_with_suppliers",
        [
            lambda: __import__("core.followups", fromlist=["enrich_followups_with_suppliers"]).enrich_followups_with_suppliers,
            lambda: __import__("followups", fromlist=["enrich_followups_with_suppliers"]).enrich_followups_with_suppliers,
        ],
    )
    add_missing_supplier_contact_exceptions = _require_import(
        "add_missing_supplier_contact_exceptions",
        [
            lambda: __import__("core.followups", fromlist=["add_missing_supplier_contact_exceptions"]).add_missing_supplier_contact_exceptions,
            lambda: __import__("followups", fromlist=["add_missing_supplier_contact_exceptions"]).add_missing_supplier_contact_exceptions,
        ],
    )
    add_urgency_column = _require_import(
        "add_urgency_column",
        [
            lambda: __import__("core.urgency", fromlist=["add_urgency_column"]).add_urgency_column,
            lambda: __import__("urgency", fromlist=["add_urgency_column"]).add_urgency_column,
        ],
    )
    build_supplier_scorecard_from_run = _require_import(
        "build_supplier_scorecard_from_run",
        [
            lambda: __import__("core.supplier_scorecards", fromlist=["build_supplier_scorecard_from_run"]).build_supplier_scorecard_from_run,
            lambda: __import__("supplier_scorecards", fromlist=["build_supplier_scorecard_from_run"]).build_supplier_scorecard_from_run,
            lambda: __import__("core.supplier_accountability", fromlist=["build_supplier_scorecard_from_run"]).build_supplier_scorecard_from_run,
        ],
    )
    make_daily_ops_pack_bytes = _require_import(
        "make_daily_ops_pack_bytes",
        [
            lambda: __import__("core.ops_pack", fromlist=["make_daily_ops_pack_bytes"]).make_daily_ops_pack_bytes,
            lambda: __import__("ops_pack", fromlist=["make_daily_ops_pack_bytes"]).make_daily_ops_pack_bytes,
            lambda: __import__("core.packs", fromlist=["make_daily_ops_pack_bytes"]).make_daily_ops_pack_bytes,
        ],
    )

    # ---------- Optional pipeline deps ----------
    try:
        from ui.sla_escalations_ui import render_sla_escalations  # type: ignore
    except Exception:
        render_sla_escalations = None

    try:
        from core.issue_tracker import IssueTrackerStore  # type: ignore
    except Exception:
        IssueTrackerStore = None

    try:
        from core.customer_impact import build_customer_impact_view  # type: ignore
    except Exception:
        build_customer_impact_view = None

    # Optional issue tracker integration hook (if your repo has it)
    try:
        from core.issue_tracker_apply import apply_issue_tracker  # type: ignore
    except Exception:
        apply_issue_tracker = None

    try:
        from ui.issue_tracker_maintenance_ui import render_issue_tracker_maintenance  # type: ignore
    except Exception:
        render_issue_tracker_maintenance = None

    # Optional mailto helper (if present)
    try:
        from ui.app_sections import mailto_fallback as mailto_link  # type: ignore
    except Exception:
        mailto_link = None

    # Optional workspaces override hook (if present)
    try:
        from ui.workspaces_ui import render_workspaces_sidebar_and_maybe_override_outputs  # type: ignore
    except Exception:
        render_workspaces_sidebar_and_maybe_override_outputs = None

    return _ShellDeps(
        render_sidebar_context=render_sidebar_context,
        render_onboarding_checklist=render_onboarding_checklist,
        render_upload_and_templates=sections.render_upload_and_templates,
        resolve_raw_inputs=sections.resolve_raw_inputs,
        stop_if_missing_required_inputs=sections.stop_if_missing_required_inputs,
        run_pipeline=run_pipeline,
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
        render_dashboard=render_dashboard,
        render_ops_triage=render_ops_triage,
        render_exceptions_queue_section=render_exceptions_queue_section,
        render_supplier_scorecards=render_supplier_scorecards,
        render_ops_outreach_comms=render_ops_outreach_comms,
        render_sla_escalations_panel=render_sla_escalations_panel,
        render_issue_tracker_ui=render_issue_tracker_ui,
        render_kpi_trends=render_kpi_trends,
        render_workspaces_sidebar=render_workspaces_sidebar,
        init_paths=init_paths,
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
    try:
        uploads = _call_with_accepted_kwargs(deps.render_upload_and_templates)
    except Exception as e:
        st.warning("Uploads / templates UI failed; proceeding without uploads (non-critical).")
        st.code(str(e))
        uploads = None

    # Raw inputs (demo-safe)
    raw_orders, raw_shipments, raw_tracking = _call_with_accepted_kwargs(
        deps.resolve_raw_inputs,
        demo_mode_active=demo_mode,
        data_dir=data_dir,
        uploads=uploads,
    )

    # Stop if required inputs are missing (unless demo)
    _call_with_accepted_kwargs(
        deps.stop_if_missing_required_inputs,
        raw_orders=raw_orders,
        raw_shipments=raw_shipments,
        raw_tracking=raw_tracking,
    )

    # Run the REAL pipeline (raw -> normalize -> reconcile -> artifacts)
    pipe = deps.run_pipeline(
        raw_orders=raw_orders,
        raw_shipments=raw_shipments,
        raw_tracking=raw_tracking,
        account_id=account_id,
        store_id=store_id,
        platform_hint=platform_hint,
        default_currency=default_currency,
        default_promised_ship_days=promised_days,
        suppliers_df=suppliers_df,
        workspaces_dir=workspaces_dir,
        normalize_orders=deps.normalize_orders,
        normalize_shipments=deps.normalize_shipments,
        normalize_tracking=deps.normalize_tracking,
        reconcile_all=deps.reconcile_all,
        enhance_explanations=deps.enhance_explanations,
        enrich_followups_with_suppliers=deps.enrich_followups_with_suppliers,
        add_missing_supplier_contact_exceptions=deps.add_missing_supplier_contact_exceptions,
        add_urgency_column=deps.add_urgency_column,
        build_supplier_scorecard_from_run=deps.build_supplier_scorecard_from_run,
        make_daily_ops_pack_bytes=deps.make_daily_ops_pack_bytes,
        workspace_root=deps.workspace_root,
        render_sla_escalations=deps.render_sla_escalations,
        apply_issue_tracker=deps.apply_issue_tracker,
        render_issue_tracker_maintenance=deps.render_issue_tracker_maintenance,
        IssueTrackerStore=deps.IssueTrackerStore,
        build_customer_impact_view=deps.build_customer_impact_view,
        mailto_link=deps.mailto_link,
        render_workspaces_sidebar_and_maybe_override_outputs=deps.render_workspaces_sidebar_and_maybe_override_outputs,
    )

    view = dict(pipe) if isinstance(pipe, dict) else {}

    # Backward-compat mapping for UI expectations
    if "supplier_scorecards" not in view and "scorecard" in view:
        view["supplier_scorecards"] = view.get("scorecard", pd.DataFrame())

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
            # Fail-safe fallback (do not crash if optional UI is missing)
            df = view.get("escalations_df", pd.DataFrame())
            if isinstance(df, pd.DataFrame) and not df.empty:
                st.dataframe(df, use_container_width=True)
            else:
                st.caption("SLA escalations UI not available.")

    with tabs[6]:
        issue_tracker_path = view.get("issue_tracker_path", None)
        if callable(deps.render_issue_tracker_ui) and issue_tracker_path:
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
