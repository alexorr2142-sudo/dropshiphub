# ui/app_shell.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Callable
import inspect
import re

import pandas as pd
import streamlit as st

from ui.app_shell_utils import _call_with_accepted_kwargs, _require_import


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

    # paths init
    init_paths: Callable[..., tuple[Path, Path, Path, Path]]


_UNEXPECTED_KW_RE = re.compile(r"unexpected keyword argument '([^']+)'")


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

    # core/suppliers.py (confirmed)
    enrich_followups_with_suppliers = _require_import(
        "enrich_followups_with_suppliers",
        [
            lambda: __import__("core.suppliers", fromlist=["enrich_followups_with_suppliers"]).enrich_followups_with_suppliers,
        ],
    )
    add_missing_supplier_contact_exceptions = _require_import(
        "add_missing_supplier_contact_exceptions",
        [
            lambda: __import__("core.suppliers", fromlist=["add_missing_supplier_contact_exceptions"]).add_missing_supplier_contact_exceptions,
        ],
    )

    # Likely in one of these core modules
    add_urgency_column = _require_import(
        "add_urgency_column",
        [
            lambda: __import__("core.sla_escalations", fromlist=["add_urgency_column"]).add_urgency_column,
            lambda: __import__("core.sla_dates", fromlist=["add_urgency_column"]).add_urgency_column,
            lambda: __import__("core.scorecards", fromlist=["add_urgency_column"]).add_urgency_column,
            lambda: __import__("core.actions", fromlist=["add_urgency_column"]).add_urgency_column,
        ],
    )

    build_supplier_scorecard_from_run = _require_import(
        "build_supplier_scorecard_from_run",
        [
            lambda: __import__("core.scorecards", fromlist=["build_supplier_scorecard_from_run"]).build_supplier_scorecard_from_run,
            lambda: __import__("core.supplier_accountability", fromlist=["build_supplier_scorecard_from_run"]).build_supplier_scorecard_from_run,
        ],
    )

    make_daily_ops_pack_bytes = _require_import(
        "make_daily_ops_pack_bytes",
        [
            lambda: __import__("core.ops_pack", fromlist=["make_daily_ops_pack_bytes"]).make_daily_ops_pack_bytes,
            lambda: __import__("core.comms_pack", fromlist=["make_daily_ops_pack_bytes"]).make_daily_ops_pack_bytes,
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

    try:
        from core.issue_tracker_apply import apply_issue_tracker  # type: ignore
    except Exception:
        apply_issue_tracker = None

    try:
        from ui.issue_tracker_maintenance_ui import render_issue_tracker_maintenance  # type: ignore
    except Exception:
        render_issue_tracker_maintenance = None

    try:
        from ui.app_sections import mailto_fallback as mailto_link  # type: ignore
    except Exception:
        mailto_link = None

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


