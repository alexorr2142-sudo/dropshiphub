# ui/issue_tracker_ui.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import streamlit as st

from core.issue_tracker import IssueTrackerStore

# Local constants (UI-level, safe)
ISSUE_STATUSES = ["Open", "Waiting", "Resolved"]


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


def _row_context(r: pd.Series) -> Dict[str, Any]:
    """
    Best-effort context extraction for timeline + filtering.
    Only includes keys that exist / are non-empty.
    """
    ctx: Dict[str, Any] = {}

    def _pick(col: str) -> str:
        try:
            return str(r.get(col, "") or "").strip()
        except Exception:
            return ""

    supplier_name = _pick("supplier_name")
    supplier_email = _pick("supplier_email")
    order_id = _pick("order_id")
    order_ids = _pick("order_ids")

    if supplier_name:
        ctx["supplier_name"] = supplier_name
    if supplier_email:
        ctx["supplier_email"] = supplier_email
    if order_id:
        ctx["order_id"] = order_id
    if order_ids:
        ctx["order_ids"] = order_ids

    return ctx


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


def enrich_followups_with_issue_fields(
    followups_df: pd.DataFrame,
    issue_tracker_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Adds:
      - owner (str)
      - issue_status (str)
      - next_action_at (str)
    based on issue tracker issue-level fields per issue_id.

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

    def _owner(iid: str) -> str:
        rec = issue_map.get(str(iid), {}) or {}
        return str(rec.get("owner", "") or "")

    def _status(iid: str) -> str:
        rec = issue_map.get(str(iid), {}) or {}
        s = str(rec.get("status", "") or "").strip()
        if not s:
            # best-effort derivation (matches core)
            if bool(rec.get("resolved", False)):
                return "Resolved"
            contact = rec.get("contact", {}) or {}
            cstat = str(contact.get("status", "") or "").strip()
            if cstat in ("Waiting", "Escalated"):
                return "Waiting"
            return "Open"
        if s not in ISSUE_STATUSES:
            return "Open"
        return s

    def _next_action(iid: str) -> str:
        rec = issue_map.get(str(iid), {}) or {}
        return str(rec.get("next_action_at", "") or "")

    df["owner"] = df["issue_id"].map(_owner)
    df["issue_status"] = df["issue_id"].map(_status)
    df["next_action_at"] = df["issue_id"].map(_next_action)
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


def render_issue_ownership_panel(
    followups_df: pd.DataFrame,
    issue_tracker_path: Optional[Path] = None,
    title: str = "Ownership & Follow-through",
    key_prefix: str = "issue_owner",
) -> None:
    """
    UI panel to enforce:
      - owner
      - issue status
      - next action date
      - follow-up logging

    Safe no-op if missing/empty/issue_id missing.
    """
    st.subheader(title)

    if followups_df is None or followups_df.empty:
        st.caption("No open issues to assign.")
        return
    if "issue_id" not in followups_df.columns:
        st.warning("Ownership panel requires `issue_id` in followups.")
        return

    store = _get_store(issue_tracker_path)

    # Enrich locally for display
    try:
        work = enrich_followups_with_issue_fields(followups_df, issue_tracker_path=issue_tracker_path)
        work = enrich_followups_with_contact_fields(work, issue_tracker_path=issue_tracker_path)
    except Exception:
        work = followups_df.copy()

    cols_pref = [
        "issue_id",
        "supplier_name",
        "supplier_email",
        "order_id",
        "order_ids",
        "worst_escalation",
        "urgency",
        "owner",
        "issue_status",
        "next_action_at",
        "contact_status",
        "follow_up_count",
    ]
    cols_show = [c for c in cols_pref if c in work.columns]
    table = work[cols_show].copy()

    # Sort: unowned + critical-ish first if present
    try:
        if "owner" in table.columns:
            table["_unowned"] = table["owner"].astype(str).map(lambda x: 1 if not x.strip() else 0)
        else:
            table["_unowned"] = 0
        sort_cols = ["_unowned"]
        if "worst_escalation" in table.columns:
            sort_cols.append("worst_escalation")
        if "supplier_name" in table.columns:
            sort_cols.append("supplier_name")
        table = table.sort_values(sort_cols, ascending=True)
    except Exception:
        pass
    if "_unowned" in table.columns:
        table = table.drop(columns=["_unowned"])

    with st.expander("Assign owner + set next action + log follow-ups", expanded=True):
        edited = st.data_editor(
            table,
            use_container_width=True,
            height=320,
            num_rows="fixed",
            key=f"{key_prefix}_editor",
            column_config={
                "owner": st.column_config.TextColumn("owner"),
                "issue_status": st.column_config.SelectboxColumn("status", options=ISSUE_STATUSES),
                "next_action_at": st.column_config.TextColumn("next action (ISO or free text)"),
                "contact_status": st.column_config.TextColumn("contact", disabled=True),
                "follow_up_count": st.column_config.NumberColumn("follow-ups", disabled=True),
            },
        )

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button("💾 Save assignments", use_container_width=True, key=f"{key_prefix}_btn_save"):
                try:
                    for _, r in edited.iterrows():
                        iid = str(r.get("issue_id", "")).strip()
                        if not iid:
                            continue

                        ctx = _row_context(r)

                        owner = str(r.get("owner", "") or "").strip()
                        status = str(r.get("issue_status", "") or "").strip()
                        next_action = str(r.get("next_action_at", "") or "").strip()

                        if owner:
                            try:
                                store.set_owner(iid, owner, context=ctx)
                            except Exception:
                                try:
                                    store.set_owner(iid, owner)
                                except Exception:
                                    pass

                        if status in ISSUE_STATUSES:
                            try:
                                store.set_issue_status(iid, status, context=ctx)
                            except Exception:
                                try:
                                    store.set_issue_status(iid, status)
                                except Exception:
                                    # fallback: map resolved to old method
                                    if status == "Resolved":
                                        try:
                                            store.set_resolved(iid, True)
                                        except Exception:
                                            pass

                        if next_action:
                            try:
                                store.set_next_action_at(iid, next_action, context=ctx)
                            except Exception:
                                try:
                                    store.set_next_action_at(iid, next_action)
                                except Exception:
                                    pass

                    st.success("Saved ✅")
                    st.rerun()
                except Exception as e:
                    st.error("Failed to save ownership updates.")
                    st.code(str(e))

        with c2:
            if st.button("⏳ Mark selected as Waiting", use_container_width=True, key=f"{key_prefix}_btn_waiting"):
                st.info("Tip: use the table editor to set status=Waiting, then click Save assignments.")

        with c3:
            st.caption("Workflow: assign an owner, set a next action, then log outreach. Nothing should remain unowned.")

        st.divider()

        # Quick follow-up logger (single issue)
        col_a, col_b = st.columns([2, 3])
        with col_a:
            iid = st.selectbox(
                "Log follow-up for issue",
                options=list(edited["issue_id"].astype(str).unique()),
                key=f"{key_prefix}_log_iid",
            )
            channel = st.selectbox(
                "Channel",
                options=["email", "phone", "chat", "other"],
                index=0,
                key=f"{key_prefix}_log_channel",
            )
        with col_b:
            note = st.text_input("Note (optional)", value="", key=f"{key_prefix}_log_note")

        # Find context for selected iid (best effort)
        ctx_for_iid: Dict[str, Any] = {}
        try:
            sel = edited[edited["issue_id"].astype(str) == str(iid)].iloc[0]
            ctx_for_iid = _row_context(sel)
        except Exception:
            ctx_for_iid = {}

        f1, f2, f3 = st.columns(3)
        with f1:
            if st.button("📨 First outreach", use_container_width=True, key=f"{key_prefix}_btn_contacted"):
                try:
                    try:
                        store.mark_contacted(issue_id=iid, channel=channel, note=note, new_status="Contacted", context=ctx_for_iid)
                    except Exception:
                        store.mark_contacted(issue_id=iid, channel=channel, note=note, new_status="Contacted")
                    try:
                        store.set_issue_status(iid, "Waiting", context=ctx_for_iid)
                    except Exception:
                        try:
                            store.set_issue_status(iid, "Waiting")
                        except Exception:
                            pass
                    st.success("Logged outreach ✅")
                    st.rerun()
                except Exception as e:
                    st.warning("Could not log outreach (optional feature).")
                    st.code(str(e))

        with f2:
            if st.button("🔁 Follow-up", use_container_width=True, key=f"{key_prefix}_btn_followup"):
                try:
                    try:
                        store.increment_followup(issue_id=iid, channel=channel, note=note, context=ctx_for_iid)
                    except Exception:
                        store.increment_followup(issue_id=iid, channel=channel, note=note)
                    try:
                        store.set_issue_status(iid, "Waiting", context=ctx_for_iid)
                    except Exception:
                        try:
                            store.set_issue_status(iid, "Waiting")
                        except Exception:
                            pass
                    st.success("Logged follow-up ✅")
                    st.rerun()
                except Exception as e:
                    st.warning("Could not log follow-up (optional feature).")
                    st.code(str(e))

        with f3:
            if st.button("✅ Resolve", use_container_width=True, key=f"{key_prefix}_btn_resolve"):
                try:
                    try:
                        store.set_issue_status(iid, "Resolved", context=ctx_for_iid)
                    except Exception:
                        try:
                            store.set_issue_status(iid, "Resolved")
                        except Exception:
                            store.set_resolved(iid, True)
                    st.success("Resolved ✅")
                    st.rerun()
                except Exception as e:
                    st.warning("Could not resolve (optional feature).")
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

        # additive keys:
        "followups_open_with_issue": pd.DataFrame,
        "followups_open_enriched": pd.DataFrame,  # issue + contact
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

    followups_open_with_issue = enrich_followups_with_issue_fields(
        followups_df=followups_open,
        issue_tracker_path=issue_tracker_path,
    )

    # Combine both (safe even if one side no-ops)
    followups_open_enriched = followups_open_with_issue.copy()
    try:
        for col in ["contact_status", "follow_up_count"]:
            if col in followups_open_with_contact.columns and col not in followups_open_enriched.columns:
                followups_open_enriched[col] = followups_open_with_contact[col].values
    except Exception:
        pass

    return {
        "issue_tracker_path": issue_tracker_path,
        "followups_full": followups_full,
        "followups_open": followups_open,
        "followups_open_with_contact": followups_open_with_contact,
        "followups_open_with_issue": followups_open_with_issue,
        "followups_open_enriched": followups_open_enriched,
    }
