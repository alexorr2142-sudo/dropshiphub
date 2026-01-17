from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.workspaces import load_run, make_run_zip_bytes
from ui.workspaces_sidebar_ui import render_workspaces_sidebar

def render_workspaces_sidebar_and_maybe_override_outputs(
    workspaces_dir: Path,
    account_id: str,
    store_id: str,
    platform_hint: str,
    orders: pd.DataFrame,
    shipments: pd.DataFrame,
    tracking: pd.DataFrame,
    exceptions: pd.DataFrame,
    followups: pd.DataFrame,
    order_rollup: pd.DataFrame,
    line_status_df: pd.DataFrame,
    kpis: dict,
    suppliers_df: pd.DataFrame,
):
    res = render_workspaces_sidebar(
        workspaces_dir=workspaces_dir,
        account_id=account_id,
        store_id=store_id,
        platform_hint=platform_hint,
        orders=orders,
        shipments=shipments,
        tracking=tracking,
        exceptions=exceptions,
        followups_full=followups,
        order_rollup=order_rollup,
        line_status_df=line_status_df,
        kpis=kpis,
        suppliers_df=suppliers_df,
        issue_tracker_path=None,
        key_prefix="ws",
    )
    return res.exceptions, res.followups_full, res.order_rollup, res.line_status_df, res.suppliers_df
