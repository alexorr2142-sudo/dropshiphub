from __future__ import annotations

import inspect
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import streamlit as st

from core.issue_tracker import IssueTrackerStore

ISSUE_STATUSES = ["Open", "Waiting", "Resolved"]

def render_followups_tracking_and_bulk_actions(
    *,
    issue_tracker_path: Path,
    chosen: str,
    issue_ids: list[str],
    supplier_email: str,
    compose_url: str,
    contact_statuses: list[str],
    key_prefix: str,
    scorecard: Optional[pd.DataFrame] = None,
    build_supplier_accountability_view: Optional[Callable[..., object]] = None,
    render_supplier_accountability: Optional[Callable[..., None]] = None,
) -> None:
    """Renders contacted/follow-up tracking + bulk ownership/actions + optional accountability panel."""
    store = IssueTrackerStore(issue_tracker_path)

    ccA, ccB, ccC = st.columns(3)

    with ccA:
        try:
            st.link_button("📧 One-click compose email", compose_url, use_container_width=True)
        except Exception:
            st.markdown(f"[📧 One-click compose email]({compose_url})")
        st.caption("Opens your email app with To/Subject/Body filled")

    with ccB:
        if st.button("✅ Mark contacted", key=f"{key_prefix}_btn_mark_contacted_{chosen}"):
            for iid in issue_ids:
                try:
                    store.mark_contacted(
                        iid,
                        channel="email",
                        note=f"Supplier email composed/sent to {supplier_email}",
                        new_status="Contacted",
                    )
                except Exception:
                    pass
            for iid in issue_ids:
                try:
                    store.set_issue_status(iid, "Waiting")
                except Exception:
                    pass
            st.success(f"Recorded contacted for {len(issue_ids)} issue(s).")
            st.rerun()

    with ccC:
        if st.button("🔁 Follow-up +1", key=f"{key_prefix}_btn_followup_plus1_{chosen}"):
            for iid in issue_ids:
                try:
                    store.increment_followup(iid, channel="email", note="Follow-up sent")
                except Exception:
                    pass
            for iid in issue_ids:
                try:
                    store.set_issue_status(iid, "Waiting")
                except Exception:
                    pass
            st.success(f"Recorded follow-up for {len(issue_ids)} issue(s).")
            st.rerun()

    # ----------------------------
    # Bulk contact status set
    # ----------------------------
    if contact_statuses:
        default_idx = contact_statuses.index("Waiting") if "Waiting" in contact_statuses else 0
        new_status = st.selectbox(
            "Set supplier contact status",
            contact_statuses,
            index=default_idx,
            key=f"{key_prefix}_status_bulk_{chosen}",
        )
        if st.button("Save contact status for all supplier issues", key=f"{key_prefix}_btn_status_bulk_{chosen}"):
            for iid in issue_ids:
                try:
                    store.set_contact_status(iid, new_status)
                except Exception:
                    pass
            st.success(f"Set contact status to {new_status} for {len(issue_ids)} issue(s).")
            st.rerun()

    # ----------------------------
    # Ownership & Follow-through bulk actions
    # ----------------------------
    st.divider()
    st.markdown("#### Ownership & Next Action (Bulk)")

    o1, o2, o3 = st.columns(3)
    with o1:
        owner_val = st.text_input(
            "Owner",
            value="",
            placeholder="e.g., Alex / Ops Team",
            key=f"{key_prefix}_owner_bulk_{chosen}",
        )
    with o2:
        issue_status_val = st.selectbox(
            "Issue status",
            options=ISSUE_STATUSES,
            index=1,
            key=f"{key_prefix}_issue_status_bulk_{chosen}",
        )
    with o3:
        next_action_val = st.text_input(
            "Next action (ISO or free text)",
            value="",
            placeholder="e.g., 2026-01-18T18:00:00Z or 'Tomorrow 10am'",
            key=f"{key_prefix}_next_action_bulk_{chosen}",
        )

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("💾 Save owner", use_container_width=True, key=f"{key_prefix}_btn_owner_save_{chosen}"):
            saved = 0
            for iid in issue_ids:
                try:
                    store.set_owner(iid, owner_val)
                    saved += 1
                except Exception:
                    pass
            st.success(f"Saved owner for {saved}/{len(issue_ids)} issue(s).")
            st.rerun()

    with b2:
        if st.button("💾 Save issue status", use_container_width=True, key=f"{key_prefix}_btn_issue_status_save_{chosen}"):
            saved = 0
            for iid in issue_ids:
                try:
                    store.set_issue_status(iid, issue_status_val)
                    saved += 1
                except Exception:
                    if issue_status_val == "Resolved":
                        try:
                            store.set_resolved(iid, True)
                            saved += 1
                        except Exception:
                            pass
            st.success(f"Saved issue status for {saved}/{len(issue_ids)} issue(s).")
            st.rerun()

    with b3:
        if st.button("💾 Save next action", use_container_width=True, key=f"{key_prefix}_btn_next_action_save_{chosen}"):
            saved = 0
            for iid in issue_ids:
                try:
                    store.set_next_action_at(iid, next_action_val)
                    saved += 1
                except Exception:
                    pass
            st.success(f"Saved next action for {saved}/{len(issue_ids)} issue(s).")
            st.rerun()

    # ----------------------------
    # Supplier accountability (optional)
    # ----------------------------
    if (
        build_supplier_accountability_view is not None
        and render_supplier_accountability is not None
        and scorecard is not None
    ):
        st.divider()
        st.markdown("#### Supplier Accountability (Auto)")
        try:
            import inspect

            sig = inspect.signature(build_supplier_accountability_view)
            params = list(sig.parameters.keys())

            if "scorecard" in params:
                accountability = build_supplier_accountability_view(scorecard=scorecard, top_n=10)
            else:
                if len(params) >= 2:
                    accountability = build_supplier_accountability_view(scorecard, 10)
                else:
                    accountability = build_supplier_accountability_view(scorecard)

            if isinstance(accountability, pd.DataFrame):
                render_supplier_accountability(accountability)
            else:
                render_supplier_accountability(pd.DataFrame(accountability))
        except Exception as e:
            st.warning("Supplier accountability failed to render.")
            st.code(str(e))
