# ui/dashboard_ui.py
from __future__ import annotations

import pandas as pd
import streamlit as st
from pathlib import Path
from typing import Callable, Optional


def render_dashboard(
    *,
    kpis: dict,
    exceptions: pd.DataFrame | None = None,
    followups_open: pd.DataFrame | None = None,
    build_daily_action_list: Optional[Callable] = None,
    render_daily_action_list: Optional[Callable] = None,
    render_kpi_trends: Optional[Callable] = None,
    workspaces_dir: Optional[Path] = None,
    account_id: str = "",
    store_id: str = "",
    title: str = "Dashboard",
) -> None:
    st.subheader(title)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Order lines", int((kpis or {}).get("total_order_lines", 0)))
    k2.metric("% Shipped/Delivered", f"{(kpis or {}).get('pct_shipped_or_delivered', 0)}%")
    k3.metric("% Delivered", f"{(kpis or {}).get('pct_delivered', 0)}%")
    k4.metric("% Unshipped", f"{(kpis or {}).get('pct_unshipped', 0)}%")
    k5.metric("% Late Unshipped", f"{(kpis or {}).get('pct_late_unshipped', 0)}%")

    if build_daily_action_list is not None and render_daily_action_list is not None:
        try:
            actions = build_daily_action_list(
                exceptions=exceptions,
                followups=followups_open,
                max_items=10,
            )
            render_daily_action_list(actions)
        except Exception:
            pass

    if render_kpi_trends is not None and workspaces_dir is not None:
        try:
            render_kpi_trends(
                workspaces_dir=workspaces_dir,
                account_id=account_id,
                store_id=store_id,
            )
        except Exception:
            pass
