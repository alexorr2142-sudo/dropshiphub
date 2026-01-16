"""Normalize + reconcile pipeline orchestration.

This is the 'middle' of the app: it takes raw inputs and produces
exceptions, followups, rollups, KPIs, scorecards, and pack bytes.

It contains the same try/except guards and best-effort behavior as the
original app.py.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

from ui.app_helpers import is_empty_df


def run_pipeline(
    *,
    raw_orders: pd.DataFrame,
    raw_shipments: pd.DataFrame,
    raw_tracking: pd.DataFrame,
    account_id: str,
    store_id: str,
    platform_hint: str,
    default_currency: str,
    default_promised_ship_days: int,
    suppliers_df: pd.DataFrame,
    workspaces_dir: Path,
    # Required pipeline fns
    normalize_orders: Callable[..., Any],
    normalize_shipments: Callable[..., Any],
    normalize_tracking: Callable[..., Any],
    reconcile_all: Callable[..., Any],
    enhance_explanations: Callable[..., Any],
    # Core helpers
    enrich_followups_with_suppliers: Callable[..., Any],
    add_missing_supplier_contact_exceptions: Callable[..., Any],
    add_urgency_column: Callable[..., Any],
    build_supplier_scorecard_from_run: Callable[..., Any],
    make_daily_ops_pack_bytes: Callable[..., Any],
    workspace_root: Callable[..., Any],
    # Optional modules / funcs
    render_sla_escalations: Optional[Callable[..., Any]] = None,
    apply_issue_tracker: Optional[Callable[..., Any]] = None,
    render_issue_tracker_maintenance: Optional[Callable[..., Any]] = None,
    IssueTrackerStore: Optional[Any] = None,
    build_customer_impact_view: Optional[Callable[..., Any]] = None,
    mailto_link: Optional[Callable[..., Any]] = None,
    render_workspaces_sidebar_and_maybe_override_outputs: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Run normalization + reconciliation and return a dict of artifacts."""

    # -----------------------
    # Stop early if raw inputs are empty
    # -----------------------
    if is_empty_df(raw_orders) or is_empty_df(raw_shipments):
        st.divider()
        st.subheader("Data checks")
        st.warning(
            "We found some schema issues. You can still proceed, but fixing these improves accuracy:"
        )
        if is_empty_df(raw_orders):
            st.write("- [orders] Input orders dataframe is empty.")
        if is_empty_df(raw_shipments):
            st.write("- [shipments] Input shipments dataframe is empty.")

        st.error(
            "Cannot run reconciliation without Orders + Shipments data (missing required columns like order_id and sku)."
        )

        with st.expander("Debug (raw input shapes / columns)", expanded=False):
            if isinstance(raw_orders, pd.DataFrame):
                st.write("raw_orders shape:", raw_orders.shape)
                st.write("raw_orders columns:", list(raw_orders.columns))
            if isinstance(raw_shipments, pd.DataFrame):
                st.write("raw_shipments shape:", raw_shipments.shape)
                st.write("raw_shipments columns:", list(raw_shipments.columns))
            if isinstance(raw_tracking, pd.DataFrame):
                st.write("raw_tracking shape:", raw_tracking.shape)
                st.write("raw_tracking columns:", list(raw_tracking.columns))

        st.stop()

    # -----------------------
    # Normalize
    # -----------------------
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

    errs = meta_o.get("validation_errors", []) + meta_s.get("validation_errors", []) + meta_t.get(
        "validation_errors", []
    )
    if errs:
        st.warning("We found some schema issues. You can still proceed, but fixing these improves accuracy:")
        for e in errs:
            st.write("- ", e)
    else:
        st.success("Looks good ✅")

    # -----------------------
    # Reconcile (with debug)
    # -----------------------
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

    # -----------------------
    # SLA escalations (optional UI)
    # -----------------------
    followups_full = followups.copy() if isinstance(followups, pd.DataFrame) else pd.DataFrame()
    followups_open = followups_full.copy()
    followups_open_enriched = followups_open.copy()
    escalations_df = pd.DataFrame()

    if callable(render_sla_escalations):
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

    # -----------------------
    # Workspace root + issue tracker
    # -----------------------
    ws_root = workspace_root(workspaces_dir, account_id, store_id)
    ws_root.mkdir(parents=True, exist_ok=True)
    issue_tracker_path = Path(ws_root) / "issue_tracker.json"

    with st.sidebar:
        if callable(render_issue_tracker_maintenance) and (IssueTrackerStore is not None):
            render_issue_tracker_maintenance(issue_tracker_path, default_prune_days=30)

    if callable(apply_issue_tracker):
        try:
            it = apply_issue_tracker(ws_root=ws_root, followups_full=followups_full)
            followups_full = it["followups_full"]
            followups_open = it["followups_open"]
            followups_open_enriched = it.get("followups_open_enriched", followups_open)
        except Exception:
            followups_open = followups_full.copy()
            followups_open_enriched = followups_open.copy()

    # -----------------------
    # Customer impact (optional)
    # -----------------------
    customer_impact = pd.DataFrame()
    if callable(build_customer_impact_view):
        try:
            customer_impact = build_customer_impact_view(exceptions=exceptions, max_items=50)
        except Exception:
            customer_impact = pd.DataFrame()

    # -----------------------
    # Daily ops pack
    # -----------------------
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

    # -----------------------
    # Workspaces UI override (optional)
    # -----------------------
    if callable(render_workspaces_sidebar_and_maybe_override_outputs):
        exceptions, followups_ws, order_rollup, line_status_df, suppliers_df = render_workspaces_sidebar_and_maybe_override_outputs(
            workspaces_dir=workspaces_dir,
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

        if isinstance(followups_ws, pd.DataFrame):
            followups_full = followups_ws.copy()
            if callable(apply_issue_tracker):
                try:
                    it = apply_issue_tracker(ws_root=ws_root, followups_full=followups_full)
                    followups_full = it["followups_full"]
                    followups_open = it["followups_open"]
                    followups_open_enriched = it.get("followups_open_enriched", followups_open)
                except Exception:
                    followups_open = followups_full.copy()
                    followups_open_enriched = followups_open.copy()
            else:
                followups_open = followups_full.copy()
                followups_open_enriched = followups_open.copy()

    return {
        "orders": orders,
        "shipments": shipments,
        "tracking": tracking,
        "meta_orders": meta_o,
        "meta_shipments": meta_s,
        "meta_tracking": meta_t,
        "line_status_df": line_status_df,
        "exceptions": exceptions,
        "followups_full": followups_full,
        "followups_open": followups_open,
        "followups_open_enriched": followups_open_enriched,
        "order_rollup": order_rollup,
        "kpis": kpis,
        "scorecard": scorecard,
        "escalations_df": escalations_df,
        "customer_impact": customer_impact,
        "ops_pack_bytes": ops_pack_bytes,
        "pack_name": pack_name,
        "ws_root": ws_root,
        "issue_tracker_path": issue_tracker_path,
        "suppliers_df": suppliers_df,
        "mailto_link": mailto_link,
    }
