# ui/issue_tracker_ui.py
from __future__ import annotations

from datetime import datetime
from typing import Tuple

import pandas as pd
import streamlit as st

# ✅ FIXED: top-level import
from core.issue_tracker import IssueTrackerStore


def apply_issue_tracker_fields(df: pd.DataFrame, store: IssueTrackerStore) -> pd.DataFrame:
    if df is None or df.empty or "issue_id" not in df.columns:
        return df

    issue_map = store.load()
    out = df.copy()
    out["Resolved"] = out["issue_id"].map(lambda k: bool(issue_map.get(str(k), {}).get("resolved", False)))
    out["Notes"] = out["issue_id"].map(lambda k: str(issue_map.get(str(k), {}).get("notes", "") or ""))
    return out


def filter_unresolved(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "Resolved" not in df.columns:
        return df
    return df[df["Resolved"] == False].copy()


def render_issue_tracker_editor(
    df: pd.DataFrame,
    title: str = "Resolved + Notes (Issue Tracker)",
    key: str = "issue_tracker_editor",
) -> Tuple[pd.DataFrame, bool]:
    store = IssueTrackerStore()
    df = apply_issue_tracker_fields(df, store)

    st.subheader(title)

    if df is None or df.empty:
        st.info("No exception rows to track right now.")
        return df, False

    if "issue_id" not in df.columns:
        st.warning("Issue tracking requires an issue_id column, but none was found.")
        return df, False

    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        hide_resolved = st.toggle("Hide resolved", value=True, key=f"{key}_hide")
    with c2:
        only_open = st.toggle("Only open", value=True, key=f"{key}_only_open")

    view = df.copy()
    if hide_resolved or only_open:
        view = view[view["Resolved"] == False].copy()

    front = ["Resolved", "Notes", "issue_id"]
    cols = front + [c for c in view.columns if c not in front]

    edited = st.data_editor(
        view[cols],
        use_container_width=True,
        hide_index=True,
        disabled=[c for c in cols if c not in ["Resolved", "Notes"]],
        column_config={
            "Resolved": st.column_config.CheckboxColumn("Resolved"),
            "Notes": st.column_config.TextColumn("Notes", width="large"),
            "issue_id": st.column_config.TextColumn("issue_id", width="medium"),
        },
        key=key,
    )

    saved = False
    if st.button("Save Issue Updates", type="primary", key=f"{key}_save"):
        issue_map = store.load()
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        for _, r in edited.iterrows():
            iid = str(r.get("issue_id", "")).strip()
            if not iid:
                continue
            issue_map[iid] = {
                "resolved": bool(r.get("Resolved", False)),
                "notes": str(r.get("Notes", "") or ""),
                "updated_at": now,
            }

        store.save(issue_map)
        st.success("Saved issue tracker updates.")
        saved = True

    return edited, saved
