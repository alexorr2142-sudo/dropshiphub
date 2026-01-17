from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from core.issue_tracker import IssueTrackerStore
from ui.issue_tracker_ui_helpers import _get_store

def render_issue_tracker_maintenance(
    issue_tracker_path: Path,
    title: str = "Issue Tracker Maintenance",
    default_prune_days: int = 30,
    key_prefix: str = "issue_maint",
):
    """
    Sidebar-friendly maintenance panel:
      - prune resolved older than N days
      - clear ALL resolved
    """
    store = _get_store(issue_tracker_path)

    with st.expander(title, expanded=False):
        prune_days = st.number_input(
            "Prune resolved older than (days)",
            min_value=1,
            max_value=365,
            value=int(default_prune_days),
            step=1,
            key=f"{key_prefix}_prune_days",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🧹 Prune old resolved", use_container_width=True, key=f"{key_prefix}_btn_prune"):
                try:
                    removed = store.prune_resolved_older_than_days(int(prune_days))
                    st.success(f"Pruned {removed} resolved item(s).")
                    st.rerun()
                except Exception as e:
                    st.error("Failed to prune resolved items.")
                    st.code(str(e))

        with c2:
            if st.button("🗑️ Clear ALL resolved", use_container_width=True, key=f"{key_prefix}_btn_clear"):
                try:
                    removed = store.clear_resolved()
                    st.success(f"Cleared {removed} resolved item(s).")
                    st.rerun()
                except Exception as e:
                    st.error("Failed to clear resolved items.")
                    st.code(str(e))


