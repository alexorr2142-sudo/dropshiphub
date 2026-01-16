"""Streamlit renderers for the main views (post-pipeline)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
import streamlit as st

from ui.app_helpers import call_with_accepted_kwargs, mailto_fallback


def render_dashboard(
    *,
    kpis: dict,
    exceptions: pd.DataFrame,
    followups_open: pd.DataFrame,
    workspaces_dir: Path,
    account_id: str,
    store_id: str,
    build_daily_action_list: Optional[Callable[..., Any]] = None,
    render_daily_action_list: Optional[Callable[..., Any]] = None,
    render_kpi_trends: Optional[Callable[..., Any]] = None,
) -> None:
    st.divider()
    st.subheader("Dashboard")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Order lines", int((kpis or {}).get("total_order_lines", 0)))
    k2.metric("% Shipped/Delivered", f"{(kpis or {}).get('pct_shipped_or_delivered', 0)}%")
    k3.metric("% Delivered", f"{(kpis or {}).get('pct_delivered', 0)}%")
    k4.metric("% Unshipped", f"{(kpis or {}).get('pct_unshipped', 0)}%")
    k5.metric("% Late Unshipped", f"{(kpis or {}).get('pct_late_unshipped', 0)}%")

    if callable(build_daily_action_list) and callable(render_daily_action_list):
        try:
            actions = build_daily_action_list(exceptions=exceptions, followups=followups_open, max_items=10)
            render_daily_action_list(actions)
        except Exception:
            # Optional UI must never break the app
            pass

    if callable(render_kpi_trends):
        try:
            render_kpi_trends(workspaces_dir=workspaces_dir, account_id=account_id, store_id=store_id)
        except Exception:
            # Optional UI must never break the app
            pass


def render_ops_triage(
    *,
    exceptions: pd.DataFrame,
    ops_pack_bytes: bytes,
    pack_name: str,
    style_exceptions_table: Optional[Callable[..., Any]] = None,
    render_ops_triage_component: Optional[Callable[..., Any]] = None,
) -> None:
    """
    "Start here" ops triage section.

    This is a thin wrapper that prefers a dedicated triage component when provided.
    IMPORTANT: the injected renderer is named `render_ops_triage_component` to avoid
    shadowing this wrapper function (and causing accidental recursion / TypeErrors).
    """
    st.divider()

    if callable(render_ops_triage_component):
        try:
            # Most triage components use positional args + optional top_n
            render_ops_triage_component(exceptions, ops_pack_bytes, pack_name, top_n=10)
            return
        except TypeError:
            # Some components may be kwargs-only
            call_with_accepted_kwargs(
                render_ops_triage_component,
                exceptions=exceptions,
                ops_pack_bytes=ops_pack_bytes,
                pack_name=pack_name,
                top_n=10,
            )
            return
        except Exception:
            # Optional component must not crash the app; fall back to simple view
            st.warning("Ops triage module had an issue; showing basic triage view instead.")

    st.subheader("Ops Triage (Start here)")
    if exceptions is None or exceptions.empty:
        st.info("No exceptions found 🎉")
        return

    view = exceptions.head(10)
    if callable(style_exceptions_table):
        try:
            st.dataframe(style_exceptions_table(view), use_container_width=True, height=320)
            return
        except Exception:
            pass

    st.dataframe(view, use_container_width=True, height=320)


def render_ops_outreach_comms(
    *,
    followups_open: pd.DataFrame,
    customer_impact: pd.DataFrame,
    scorecard: pd.DataFrame,
    ws_root: Path,
    issue_tracker_path: Path,
    contact_statuses: list,
    mailto_link_fn: Optional[Callable[[str, str, str], str]] = None,
    build_supplier_accountability_view: Optional[Callable[..., Any]] = None,
    render_supplier_accountability: Optional[Callable[..., Any]] = None,
    render_supplier_followups_tab: Optional[Callable[..., Any]] = None,
    render_customer_comms_ui: Optional[Callable[..., Any]] = None,
    render_comms_pack_download: Optional[Callable[..., Any]] = None,
    account_id: str = "",
    store_id: str = "",
) -> None:
    st.divider()
    st.subheader("Ops Outreach (Comms)")
    tab1, tab2, tab3 = st.tabs(["Supplier Follow-ups", "Customer Emails", "Comms Pack"])

    # Supplier Follow-ups
    with tab1:
        if callable(render_supplier_followups_tab) and isinstance(followups_open, pd.DataFrame):
            render_supplier_followups_tab(
                followups_open=followups_open,
                issue_tracker_path=issue_tracker_path,
                contact_statuses=contact_statuses,
                mailto_link_fn=mailto_link_fn if callable(mailto_link_fn) else mailto_fallback,
                scorecard=scorecard if isinstance(scorecard, pd.DataFrame) else None,
                build_supplier_accountability_view=build_supplier_accountability_view if callable(build_supplier_accountability_view) else None,
                render_supplier_accountability=render_supplier_accountability if callable(render_supplier_accountability) else None,
                key_prefix="supplier_followups",
            )
        else:
            st.caption("Supplier follow-ups UI module not available.")
            if followups_open is None or followups_open.empty:
                st.info("No supplier follow-ups needed.")
            else:
                st.dataframe(followups_open, use_container_width=True, height=260)

    # Customer emails
    with tab2:
        st.caption("Customer-facing updates (email-first).")
        if customer_impact is None or customer_impact.empty:
            st.info("No customer-impact items detected for this run.")
        else:
            if callable(render_customer_comms_ui):
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

    # Comms pack download
    with tab3:
        st.caption("Download combined comms artifacts (supplier + customer).")
        if callable(render_comms_pack_download):
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


def render_exceptions_queue_section(
    *,
    exceptions: pd.DataFrame,
    style_exceptions_table: Optional[Callable[..., Any]] = None,
    render_exceptions_queue: Optional[Callable[..., Any]] = None,
) -> None:
    st.divider()
    if callable(render_exceptions_queue):
        render_exceptions_queue(exceptions, key_prefix="exq", height=420)
        return

    st.subheader("Exceptions Queue (Action this first)")
    if exceptions is None or exceptions.empty:
        st.info("No exceptions found 🎉")
        return

    fcol1, fcol2, fcol3, fcol4 = st.columns(4)

    with fcol1:
        issue_types = (
            sorted(exceptions["issue_type"].dropna().unique().tolist()) if "issue_type" in exceptions.columns else []
        )
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types, key="exq_issue_types")

    with fcol2:
        countries = sorted(
            [
                c
                for c in exceptions.get("customer_country", pd.Series([], dtype="object")).dropna().unique().tolist()
                if str(c).strip() != ""
            ]
        )
        country_filter = st.multiselect("Customer country", countries, default=countries, key="exq_countries")

    with fcol3:
        suppliers = sorted(
            [
                s
                for s in exceptions.get("supplier_name", pd.Series([], dtype="object")).dropna().unique().tolist()
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

    if callable(style_exceptions_table) and show_cols:
        st.dataframe(style_exceptions_table(filtered[show_cols]), use_container_width=True, height=420)
    else:
        st.dataframe(filtered[show_cols] if show_cols else filtered, use_container_width=True, height=420)

    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
        key="dl_exceptions_csv",
    )


def render_supplier_scorecards(
    *,
    scorecard: pd.DataFrame,
    ws_root: Path,
    load_recent_scorecard_history: Callable[..., Any],
    list_runs: Optional[Callable[..., Any]] = None,
) -> None:
    st.divider()
    st.subheader("Supplier Scorecards (Performance + Trends)")

    if scorecard is None or scorecard.empty:
        st.info("Scorecards require `supplier_name` in your normalized line status data.")
        return

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
        if callable(list_runs):
            try:
                runs_for_trend = list_runs(ws_root)
            except Exception:
                runs_for_trend = []

        if not runs_for_trend:
            st.caption("No saved runs yet. Click **Save this run** to build trend history.")
            return

        max_runs = st.slider("Use last N saved runs", 5, 50, 25, 5, key="trend_max_runs")
        hist = load_recent_scorecard_history(str(ws_root), max_runs=int(max_runs))

        if hist is None or hist.empty:
            st.caption("No historical scorecards found yet (save a run first).")
            return

        supplier_options = sorted(hist["supplier_name"].dropna().unique().tolist())
        chosen_supplier = st.selectbox("Supplier", supplier_options, key="scorecard_trend_supplier")

        s_hist = hist[hist["supplier_name"] == chosen_supplier].copy().sort_values("run_dt")
        chart_df = s_hist[["run_dt", "exception_rate"]].dropna()
        if not chart_df.empty:
            st.line_chart(chart_df.set_index("run_dt"))

        tcols = ["run_id", "total_lines", "exception_lines", "exception_rate", "critical", "high"]
        tcols = [c for c in tcols if c in s_hist.columns]
        st.dataframe(s_hist[tcols].sort_values("run_id", ascending=False), use_container_width=True, height=220)


def render_sla_escalations_panel(*, escalations_df: pd.DataFrame) -> None:
    if isinstance(escalations_df, pd.DataFrame) and not escalations_df.empty:
        st.divider()
        st.subheader("SLA Escalations (Supplier-level)")
        st.dataframe(escalations_df, use_container_width=True, height=260)
