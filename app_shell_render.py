from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from ui.app_shell_boot import _safe_imports

def render_app() -> None:
    """
    The main app body AFTER access gates.
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

    # Uploads + templates (fail-safe)
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

    # Run pipeline
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

    # Backward-compat mapping
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
        try:
            _call_with_accepted_kwargs(
                deps.render_dashboard,
                kpis=view.get("kpis", {}),
                run_history_df=view.get("run_history_df", pd.DataFrame()),
                view=view,
            )
        except Exception as e:
            st.warning("Dashboard failed to render (non-critical).")
            st.code(str(e))

    with tabs[1]:
        try:
            _call_with_accepted_kwargs(
                deps.render_ops_triage,
                exceptions=view.get("exceptions", pd.DataFrame()),
                followups_open=view.get("followups_open", pd.DataFrame()),
                view=view,
            )
        except Exception as e:
            st.warning("Ops triage failed to render (non-critical).")
            st.code(str(e))

    with tabs[2]:
        try:
            _call_with_accepted_kwargs(
                deps.render_exceptions_queue_section,
                exceptions=view.get("exceptions", pd.DataFrame()),
                view=view,
            )
        except Exception as e:
            st.warning("Exceptions queue failed to render (non-critical).")
            st.code(str(e))

    with tabs[3]:
        try:
            _call_with_accepted_kwargs(
                deps.render_supplier_scorecards,
                supplier_scorecards=view.get("supplier_scorecards", pd.DataFrame()),
                scorecard=view.get("scorecard", pd.DataFrame()),
                view=view,
            )
        except Exception as e:
            st.warning("Supplier scorecards failed to render (non-critical).")
            st.code(str(e))

    with tabs[4]:
        try:
            _call_with_accepted_kwargs(
                deps.render_ops_outreach_comms,
                followups_open=view.get("followups_open", pd.DataFrame()),
                customer_impact=view.get("customer_impact", pd.DataFrame()),
                mailto_link=view.get("mailto_link", ""),
                view=view,
            )
        except Exception as e:
            st.warning("Ops outreach failed to render (non-critical).")
            st.code(str(e))

    with tabs[5]:
        try:
            if callable(deps.render_sla_escalations_panel):
                _call_with_accepted_kwargs(
                    deps.render_sla_escalations_panel,
                    escalations_df=view.get("escalations_df", pd.DataFrame()),
                    view=view,
                )
            else:
                df = view.get("escalations_df", pd.DataFrame())
                if isinstance(df, pd.DataFrame) and not df.empty:
                    st.dataframe(df, use_container_width=True)
                else:
                    st.caption("SLA escalations UI not available.")
        except Exception as e:
            st.warning("SLA escalations failed to render (non-critical).")
            st.code(str(e))

    with tabs[6]:
        try:
            issue_tracker_path = view.get("issue_tracker_path", None)
            if callable(deps.render_issue_tracker_ui) and issue_tracker_path:
                _call_with_accepted_kwargs(
                    deps.render_issue_tracker_ui,
                    issue_tracker_path=issue_tracker_path,
                    view=view,
                )
            else:
                st.caption("Follow-up tracker UI not available.")
        except Exception as e:
            st.warning("Follow-up tracker failed to render (non-critical).")
            st.code(str(e))

    with tabs[7]:
        if callable(deps.render_kpi_trends):
            try:
                _call_with_accepted_kwargs(
                    deps.render_kpi_trends,
                    workspaces_dir=workspaces_dir,
                    account_id=account_id,
                    store_id=store_id,
                    view=view,
                )
            except Exception as e:
                st.warning("KPI trends UI failed to render (non-critical).")
                st.code(str(e))
        else:
            st.caption("KPI trends UI not available.")
