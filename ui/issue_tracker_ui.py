# ui/issue_tracker_ui.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from core.issue_tracker import IssueTrackerStore


def _get_store(issue_tracker_path: Optional[Path] = None) -> IssueTrackerStore:
    """
    Ensures we always use the per-tenant store file when provided.
    Falls back to IssueTrackerStore() default behavior if no path is given.
    """
    try:
        return IssueTrackerStore(issue_tracker_path) if issue_tracker_path else IssueTrackerStore()
    except TypeError:
        # Backward compatibility if IssueTrackerStore() signature differs
        return IssueTrackerStore()


def derive_followups_open(
    followups_full: pd.DataFrame,
    issue_tracker_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Returns OPEN followups only (filters out resolved items), using issue tracker state.
    Safe no-op if followups_full missing/empty or missing issue_id.
    """
    if followups_full is None or followups_full.empty:
        return followups_full

    if "issue_id" not in followups_full.columns:
        return followups_full

    store = _get_store(issue_tracker_path)
    issue_map = store.load() or {}

    df = followups_full.copy()
    df["issue_id"] = df["issue_id"].astype(str)

    resolved = df["issue_id"].map(lambda k: bool((issue_map.get(str(k), {}) or {}).get("resolved", False)))
    df = df[resolved == False].copy()  # noqa: E712
    return df


def enrich_followups_with_contact_fields(
    followups_df: pd.DataFrame,
    issue_tracker_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Adds:
      - contact_status (str)
      - follow_up_count (int)
    based on issue tracker 'contact' object per issue_id.

    Safe no-op if followups_df missing/empty or missing issue_id.
    """
    if followups_df is None or followups_df.empty:
        return followups_df
    if "issue_id" not in followups_df.columns:
        return followups_df

    store = _get_store(issue_tracker_path)
    issue_map = store.load() or {}

    df = followups_df.copy()
    df["issue_id"] = df["issue_id"].astype(str)

    def _contact_status(iid: str) -> str:
        rec = issue_map.get(str(iid), {}) or {}
        contact = rec.get("contact", {}) or {}
        return str(contact.get("status", "Not Contacted") or "Not Contacted")

    def _followups(iid: str) -> int:
        rec = issue_map.get(str(iid), {}) or {}
        contact = rec.get("contact", {}) or {}
        try:
            return int(contact.get("follow_up_count", 0) or 0)
        except Exception:
            return 0

    df["contact_status"] = df["issue_id"].map(_contact_status)
    df["follow_up_count"] = df["issue_id"].map(_followups)
    return df


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


def apply_issue_tracker(
    *,
    ws_root: Path,
    followups_full: pd.DataFrame,
) -> dict:
    """
    Convenience wrapper to keep app.py tiny.

    Returns:
      {
        "issue_tracker_path": Path,
        "followups_full": pd.DataFrame,
        "followups_open": pd.DataFrame,
        "followups_open_with_contact": pd.DataFrame,
      }
    """
    issue_tracker_path = Path(ws_root) / "issue_tracker.json"

    followups_open = derive_followups_open(
        followups_full=followups_full,
        issue_tracker_path=issue_tracker_path,
    )

    followups_open_with_contact = enrich_followups_with_contact_fields(
        followups_df=followups_open,
        issue_tracker_path=issue_tracker_path,
    )

    return {
        "issue_tracker_path": issue_tracker_path,
        "followups_full": followups_full,
        "followups_open": followups_open,
        "followups_open_with_contact": followups_open_with_contact,
    }
