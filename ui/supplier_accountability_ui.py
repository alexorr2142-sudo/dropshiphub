# dropshiphub/ui/sla_escalations_ui.py
from __future__ import annotations

import pandas as pd
import streamlit as st

from dropshiphub.core.sla_escalations import build_sla_escalations
from dropshiphub.core.issue_tracker import IssueTrackerStore
from dropshiphub.ui.issue_tracker_ui import (
    render_issue_tracker_editor,
    apply_issue_tracker_fields,
    filter_unresolved,
)


def render_sla_escalations(
    line_status_df: pd.DataFrame,
    followups: pd.DataFrame,
    promised_ship_days: int = 3,
    grace_days: int = 0,
    at_risk_hours: int = 72,
):
    """
    Step 3B: Wires the Issue Tracker (Resolved + Notes) into the SLA Exceptions UI.

    Inputs:
      - line_status_df: your line-level status table
      - followups: your followups table (row-level preferred; supplier-level still works)
      - promised_ship_days, grace_days, at_risk_hours: SLA settings

    Returns:
      (escalations_df, updated_followups_df, open_followups_df)
        - updated_followups_df includes worst_escalation + issue_id (from Step 2) + Resolved/Notes (from store)
        - open_followups_df filters out Resolved == True for operational use (emails, chasing, etc.)
    """
    st.header("SLA Exceptions")

    # -------------------------------
    # Build escalations + followups
    # -------------------------------
    escalations_df, updated_followups = build_sla_escalations(
        line_status_df=line_status_df,
        followups=followups,
        promised_ship_days=int(promised_ship_days),
        grace_days=int(grace_days),
        at_risk_hours=int(at_risk_hours),
    )

    # -------------------------------
    # Supplier escalation summary
    # -------------------------------
    st.subheader("Supplier Escalation Summary")
    if escalations_df is None or escalations_df.empty:
        st.info("No open SLA exceptions found.")
    else:
        st.dataframe(escalations_df, use_container_width=True, hide_index=True)

    # -------------------------------
    # Step 3B: Issue Tracker (Resolved + Notes)
    # -------------------------------
    st.divider()

    # Ensure folder exists (safe no-op if already exists)
    # (If you already do this in app.py, you can remove this.)
    from pathlib import Path
    Path("data").mkdir(parents=True, exist_ok=True)

    # Attach current saved state (Resolved/Notes) before editor
    store = IssueTrackerStore()
    updated_followups = apply_issue_tracker_fields(updated_followups, store)

    # Render editor that can update Resolved + Notes
    edited_followups, saved = render_issue_tracker_editor(
        updated_followups if updated_followups is not None else pd.DataFrame(),
        title="Resolved + Notes (Issue Tracker)",
        key="exceptions_issue_tracker",
    )

    # Re-apply fields after save (so the page reflects persisted state immediately)
    if saved:
        edited_followups = apply_issue_tracker_fields(edited_followups, store)

    # Operational “open” list for downstream logic (emails, chasing, etc.)
    open_followups = filter_unresolved(edited_followups)

    # -------------------------------
    # Show Open Followups (what you act on)
    # -------------------------------
    st.subheader("Open Followups (Unresolved Only)")
    if open_followups is None or open_followups.empty:
        st.success("Nothing open — all exceptions are resolved (or none exist).")
    else:
        st.dataframe(open_followups, use_container_width=True, hide_index=True)
        st.caption(f"Open items: {len(open_followups)}")

    # Return these so app.py (or other UI sections) can use open_followups for emails/templates
    return escalations_df, edited_followups, open_followups
