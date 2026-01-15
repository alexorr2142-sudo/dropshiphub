# ui/issue_tracker_ui.py
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.issue_tracker import IssueTrackerStore


def render_issue_tracker_panel(
    followups_full: pd.DataFrame,
    title: str = "Issue Tracker (Resolved + Notes)",
) -> pd.DataFrame:
    """
    Renders a resolved/notes editor and returns followups_full enriched with:
      - resolved (bool)
      - notes (str)

    Requirements:
      - followups_full must contain 'issue_id' column
    """

    if followups_full is None or followups_full.empty:
        st.subheader(title)
        st.caption("No follow-ups to track.")
        return followups_full

    if "issue_id" not in followups_full.columns:
        st.subheader(title)
        st.warning("Issue Tracker requires `issue_id` in followups_full.")
        return followups_full

    store = IssueTrackerStore()
    issue_map = store.load() or {}

    df = followups_full.copy()
    df["issue_id"] = df["issue_id"].astype(str)

    df["resolved"] = df["issue_id"].map(lambda k: bool((issue_map.get(str(k), {}) or {}).get("resolved", False)))
    df["notes"] = df["issue_id"].map(lambda k: str((issue_map.get(str(k), {}) or {}).get("notes", "")))

    resolved_count = int(df["resolved"].sum())
    open_count = int(len(df) - resolved_count)

    st.subheader(title)
    a, b, c = st.columns(3)
    a.metric("Open", open_count)
    b.metric("Resolved", resolved_count)
    c.metric("Total", int(len(df)))

    with st.expander("Update resolved status + notes", expanded=False):
        cols_pref = [
            "issue_id",
            "supplier_name",
            "supplier_email",
            "order_ids",
            "item_count",
            "worst_escalation",
            "urgency",
            "resolved",
            "notes",
        ]
        cols_show = [c for c in cols_pref if c in df.columns]
        work = df[cols_show].copy()

        # Keep editor stable
        work = work.sort_values(["resolved", "supplier_name"] if "supplier_name" in work.columns else ["resolved"])

        edited = st.data_editor(
            work,
            use_container_width=True,
            height=320,
            num_rows="fixed",
            key="issue_tracker_editor",
            column_config={
                "resolved": st.column_config.CheckboxColumn("resolved"),
                "notes": st.column_config.TextColumn("notes"),
            },
        )

        save1, save2 = st.columns([1, 3])
        with save1:
            if st.button("💾 Save changes", use_container_width=True, key="btn_issue_tracker_save"):
                try:
                    for _, r in edited.iterrows():
                        iid = str(r.get("issue_id", "")).strip()
                        if not iid:
                            continue
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

    # Merge the latest resolved/notes back into full df
    # (In case user edited in the same render pass)
    latest_map = store.load() or {}
    df["resolved"] = df["issue_id"].map(lambda k: bool((latest_map.get(str(k), {}) or {}).get("resolved", False)))
    df["notes"] = df["issue_id"].map(lambda k: str((latest_map.get(str(k), {}) or {}).get("notes", "")))
    return df
