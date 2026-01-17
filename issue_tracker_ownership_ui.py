from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from core.timeline_store import TimelineStore

from ui.issue_tracker_ui_helpers import ISSUE_STATUSES, _get_store, _row_context

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


