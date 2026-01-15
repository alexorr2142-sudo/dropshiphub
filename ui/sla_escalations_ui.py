# ui/sla_escalations_ui.py
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.sla_escalations import build_sla_escalations
from core.issue_tracker import IssueTrackerStore
from ui.issue_tracker_ui import render_issue_tracker_editor, apply_issue_tracker_fields, filter_unresolved


def render_sla_escalations(
    line_status_df: pd.DataFrame,
    followups: pd.DataFrame,
    promised_ship_days: int = 3,
    grace_days: int = 0,
    at_risk_hours: int = 72,
):
    st.header("SLA Exceptions")

    escalations_df, updated_followups = build_sla_escalations(
        line_status_df=line_status_df,
        followups=followups,
        promised_ship_days=int(promised_ship_days),
        grace_days=int(grace_days),
        at_risk_hours=int(at_risk_hours),
    )

    st.subheader("Supplier Escalation Summary")
    if escalations_df is None or escalations_df.empty:
        st.info("No open SLA exceptions found.")
    else:
        st.dataframe(escalations_df, use_container_width=True, hide_index=True)

    st.divider()

    # Attach current state (Resolved/Notes) and render editor
    store = IssueTrackerStore()
    updated_followups = apply_issue_tracker_fields(updated_followups, store)

    edited_followups, saved = render_issue_tracker_editor(
        updated_followups if updated_followups is not None else pd.DataFrame(),
        title="Resolved + Notes (Issue Tracker)",
        key="exceptions_issue_tracker",
    )

    if saved:
        edited_followups = apply_issue_tracker_fields(edited_followups, store)

    open_followups = filter_unresolved(edited_followups)

    st.subheader("Open Followups (Unresolved Only)")
    if open_followups is None or open_followups.empty:
        st.success("Nothing open — all exceptions are resolved (or none exist).")
    else:
        st.dataframe(open_followups, use_container_width=True, hide_index=True)
        st.caption(f"Open items: {len(open_followups)}")

    return escalations_df, edited_followups, open_followups
