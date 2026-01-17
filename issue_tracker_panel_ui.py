from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from ui.issue_tracker_maintenance_ui import render_issue_tracker_maintenance
from ui.issue_tracker_ownership_ui import render_issue_ownership_panel

def render_issue_tracker_panel(
    followups_full: pd.DataFrame,
    issue_tracker_path: Optional[Path] = None,
    title: str = "Issue Tracker (Resolved + Notes)",
    key_prefix: str = "issue_tracker",
) -> pd.DataFrame:
    """
    Renders a resolved/notes editor and returns followups_full enriched with:
      - resolved (bool)
      - notes (str)

    Requirements:
      - followups_full must contain 'issue_id' column
    """
    st.subheader(title)

    if followups_full is None or followups_full.empty:
        st.caption("No follow-ups to track.")
        return followups_full

    if "issue_id" not in followups_full.columns:
        st.warning("Issue Tracker requires `issue_id` in followups_full.")
        return followups_full

    store = _get_store(issue_tracker_path)
    issue_map = store.load() or {}

    df = followups_full.copy()
    df["issue_id"] = df["issue_id"].astype(str)

    df["resolved"] = df["issue_id"].map(lambda k: bool((issue_map.get(str(k), {}) or {}).get("resolved", False)))
    df["notes"] = df["issue_id"].map(lambda k: str((issue_map.get(str(k), {}) or {}).get("notes", "")))

    resolved_count = int(df["resolved"].sum())
    open_count = int(len(df) - resolved_count)

    a, b, c = st.columns(3)
    a.metric("Open", open_count)
    b.metric("Resolved", resolved_count)
    c.metric("Total", int(len(df)))

    with st.expander("Update resolved status + notes", expanded=False):
        cols_pref = [
            "issue_id",
            "supplier_name",
            "supplier_email",
            "order_id",
            "order_ids",
            "item_count",
            "worst_escalation",
            "urgency",
            "resolved",
            "notes",
        ]
        cols_show = [c for c in cols_pref if c in df.columns]
        work = df[cols_show].copy()

        sort_cols = []
        if "resolved" in work.columns:
            sort_cols.append("resolved")
        if "supplier_name" in work.columns:
            sort_cols.append("supplier_name")
        if sort_cols:
            work = work.sort_values(sort_cols)

        edited = st.data_editor(
            work,
            use_container_width=True,
            height=320,
            num_rows="fixed",
            key=f"{key_prefix}_editor",
            column_config={
                "resolved": st.column_config.CheckboxColumn("resolved"),
                "notes": st.column_config.TextColumn("notes"),
            },
        )

        save1, save2 = st.columns([1, 3])
        with save1:
            if st.button("💾 Save changes", use_container_width=True, key=f"{key_prefix}_btn_save"):
                try:
                    for _, r in edited.iterrows():
                        iid = str(r.get("issue_id", "")).strip()
                        if not iid:
                            continue
                        ctx = _row_context(r)

                        try:
                            store.upsert(
                                issue_id=iid,
                                resolved=bool(r.get("resolved", False)),
                                notes=str(r.get("notes", "") or ""),
                                context=ctx,
                            )
                        except Exception:
                            store.upsert(
                                issue_id=iid,
                                resolved=bool(r.get("resolved", False)),
                                notes=str(r.get("notes", "") or ""),
                            )

                    st.success("Saved ✅")
                    st.rerun()
                except Exception as e:
                    st.error("Failed to save issue tracker updates.")
                    st.code(str(e))

        with save2:
            st.caption("Tip: Use this to hide resolved items from OPEN follow-ups while keeping history.")

    # Merge latest state back into df (covers same-run edits)
    latest_map = store.load() or {}
    df["resolved"] = df["issue_id"].map(lambda k: bool((latest_map.get(str(k), {}) or {}).get("resolved", False)))
    df["notes"] = df["issue_id"].map(lambda k: str((latest_map.get(str(k), {}) or {}).get("notes", "")))
    return df


