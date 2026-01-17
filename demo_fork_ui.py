# ui/demo_fork_ui.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.workspaces import save_raw_inputs_snapshot, workspace_root


def _infer_workspaces_dir() -> Path:
    # Matches app.py convention: BASE_DIR/data/workspaces
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    workspaces_dir = data_dir / "workspaces"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    return workspaces_dir


def _infer_tenant_from_session() -> tuple[str, str, str]:
    # Your sidebar uses key_prefix="sb"
    account_id = str(st.session_state.get("sb_account_id", "demo_account"))
    store_id = str(st.session_state.get("sb_store_id", "demo_store"))
    platform_hint = str(st.session_state.get("sb_platform_hint", "shopify"))
    return account_id, store_id, platform_hint


def render_demo_fork_controls(
    *,
    raw_orders: pd.DataFrame,
    raw_shipments: pd.DataFrame,
    raw_tracking: pd.DataFrame | None = None,
    key_prefix: str = "demo_fork",
) -> None:
    """
    Renders UI to snapshot current demo edits into a workspace folder as RAW CSVs.
    Does not require app.py changes.
    """
    st.markdown("### Fork demo edits → Workspace snapshot")
    st.caption(
        "Saves your current demo tables (raw_orders/raw_shipments/raw_tracking) into Workspaces as a RAW snapshot "
        "so you can always restore or share this exact demo scenario."
    )

    account_id, store_id, platform_hint = _infer_tenant_from_session()
    workspaces_dir = _infer_workspaces_dir()
    ws_root = workspace_root(workspaces_dir, account_id, store_id)
    ws_root.mkdir(parents=True, exist_ok=True)

    workspace_name = st.text_input(
        "Snapshot workspace name",
        value="demo_forks",
        key=f"{key_prefix}_workspace_name",
        help="This becomes a workspace folder under your tenant.",
    )
    note = st.text_input(
        "Snapshot note (optional)",
        value="",
        key=f"{key_prefix}_note",
        help="Short note describing what this demo scenario is meant to showcase.",
    )

    c1, c2 = st.columns([1, 2])
    with c1:
        do_save = st.button("📌 Save RAW snapshot", key=f"{key_prefix}_btn_save", use_container_width=True)
    with c2:
        st.caption(f"Tenant: {account_id} / {store_id} • Platform: {platform_hint}")

    if do_save:
        if raw_orders is None or not isinstance(raw_orders, pd.DataFrame) or raw_orders.empty:
            st.error("Cannot snapshot: demo raw_orders is empty.")
            return
        if raw_shipments is None or not isinstance(raw_shipments, pd.DataFrame) or raw_shipments.empty:
            st.error("Cannot snapshot: demo raw_shipments is empty.")
            return

        run_dir = save_raw_inputs_snapshot(
            ws_root=ws_root,
            workspace_name=workspace_name,
            account_id=account_id,
            store_id=store_id,
            platform_hint=platform_hint,
            raw_orders=raw_orders,
            raw_shipments=raw_shipments,
            raw_tracking=raw_tracking if isinstance(raw_tracking, pd.DataFrame) else pd.DataFrame(),
            note=note,
            source="demo_fork",
        )
        st.success(f"Saved RAW snapshot ✅ {workspace_name}/{run_dir.name}")
        st.caption(f"Path: {run_dir.as_posix()}")
