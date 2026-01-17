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


