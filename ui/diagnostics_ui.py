# ui/diagnostics_ui.py
from __future__ import annotations

from pathlib import Path
import streamlit as st

from core.workspaces import list_runs, workspace_root


def render_diagnostics(
    *,
    workspaces_dir: Path,
    account_id: str,
    store_id: str,
    diag: dict,
    title: str = "ClearOps Diagnostics",
    expanded: bool = False,
) -> None:
    """
    Renders the diagnostics expander:
      - bool flags for optional modules/features
      - workspace root path
      - saved run count

    This panel is intended for troubleshooting and verification only.
    """
    with st.expander(title, expanded=expanded):
        st.caption("System health and optional feature availability.")
        st.json(diag)

        ws_root_diag = workspace_root(workspaces_dir, account_id, store_id)
        st.write(f"workspace root: `{ws_root_diag.as_posix()}`")
        try:
            st.write(f"saved runs: {len(list_runs(ws_root_diag))}")
        except Exception:
            st.write("saved runs: (unable to count)")
