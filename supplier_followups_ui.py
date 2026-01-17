# ui/supplier_followups_ui.py
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import streamlit as st

from core.styling import copy_button
from core.issue_tracker_apply import enrich_followups_with_contact_fields, enrich_followups_with_issue_fields


def _mailto_fallback(to: str, subject: str, body: str) -> str:
    from urllib.parse import quote
    return f"mailto:{quote(to or '')}?subject={quote(subject or '')}&body={quote(body or '')}"


def _first_row_for_supplier(df: pd.DataFrame, supplier_name: str) -> dict:
    try:
        row = df[df["supplier_name"] == supplier_name].iloc[0]
        return row.to_dict()
    except Exception:
        return {}


def render_supplier_followups_tab(
    followups_open: pd.DataFrame,
    *,
    issue_tracker_path: Path,
    contact_statuses: list[str],
    mailto_link_fn: Optional[Callable[[str, str, str], str]] = None,
    scorecard: Optional[pd.DataFrame] = None,
    build_supplier_accountability_view: Optional[Callable[..., object]] = None,
    render_supplier_accountability: Optional[Callable[..., None]] = None,
    key_prefix: str = "supplier_followups",
) -> None:
    """
    Supplier Follow-ups (unresolved only).

    Preserves:
      - OPEN followups preview
      - contact_status + follow_up_count
      - Supplier email generator (3 questions)
      - Copy buttons + Download .txt + One-click compose (mailto)
      - Mark contacted + Follow-up +1 + bulk contact status set
      - Supplier Accountability (Auto) panel if hooks provided

    Adds (Ownership & Follow-through):
      - owner / issue_status / next_action_at in preview
      - bulk set owner / issue status / next action

    Adds (Timeline):
      - supplier-filtered timeline panel for visibility + audit
    """
    st.caption("Supplier-facing outreach based on OPEN follow-ups (unresolved only).")

    if followups_open is None or followups_open.empty:
        st.info("No supplier follow-ups needed.")
        return

    # ----------------------------
    # Preview table (enriched)
    # ----------------------------
    show_df = followups_open.copy()

    try:
        show_df = enrich_followups_with_contact_fields(show_df, issue_tracker_path=issue_tracker_path)
    except Exception:
        pass

    try:
        show_df = enrich_followups_with_issue_fields(show_df, issue_tracker_path=issue_tracker_path)
    except Exception:
        pass

    summary_cols = [
        c
        for c in [
            "supplier_name",
            "supplier_email",
            "worst_escalation",
            "urgency",
            "item_count",
            "order_ids",
            "owner",
            "issue_status",
            "next_action_at",
            "contact_status",
            "follow_up_count",
        ]
        if c in show_df.columns
    ]
    st.dataframe(show_df[summary_cols] if summary_cols else show_df, use_container_width=True, height=220)

    # ----------------------------
    # Supplier selection
    # ----------------------------
    if "supplier_name" not in followups_open.columns or len(followups_open) == 0:
        st.info("Follow-ups are missing supplier_name, so email generation is unavailable.")
        return

    suppliers = followups_open["supplier_name"].fillna("").astype(str).tolist()
    suppliers = [s for s in suppliers if s.strip() != ""]
    if not suppliers:
        st.info("No suppliers available to email.")
        return

    chosen = st.selectbox("Supplier", suppliers, key=f"{key_prefix}_supplier_select")
    row = _first_row_for_supplier(followups_open, chosen)

    # ----------------------------
    # Supplier-specific Timeline (NEW)
    # ----------------------------
    try:
        from ui.timeline_ui import render_timeline_panel
        from core.timeline_store import timeline_path_for_issue_tracker_path

        render_timeline_panel(
            timeline_path=timeline_path_for_issue_tracker_path(issue_tracker_path),
            title=f"Timeline — {chosen}",
            supplier_name=chosen,
            limit=75,
            key_prefix=f"{key_prefix}_timeline_{chosen}",
        )
    except Exception:
        pass

    # ----------------------------
    # Email generator
    # ----------------------------
    supplier_email = str(row.get("supplier_email", "")).strip()
    order_ids = str(row.get("order_ids", "")).strip()

    default_subject = str(row.get("subject", "")).strip()
    if not default_subject:
        default_subject = f"Urgent: shipment status update needed ({chosen})"

    st.markdown("#### Supplier Email Generator (3 questions)")
    subj = st.text_input("Subject", value=default_subject, key=f"{key_prefix}_subject")

    bullets = [
        "Can you confirm what’s causing the delay / issue on these shipments?",
        "What is the updated ship date (or delivery ETA) for each impacted order?",
        "Please share tracking numbers (or confirm next step + timeline if tracking is not available yet).",
    ]
    bullet_text = "\n".join([f"• {b}" for b in bullets])

    body_default = "\n".join(
        [
            f"Hi {chosen},",
            "",
            "We’re seeing issues on the following order(s):",
            f"{order_ids if order_ids else '(order list unavailable)'}",
            "",
            "Can you help with the following:",
            bullet_text,
            "",
            "Thanks,",
        ]
    )
    body = st.text_area("Body", value=body_default, height=240, key=f"{key_prefix}_body")

    c1, c2, c3 = st.columns(3)
    with c1:
        copy_button(supplier_email, "Copy supplier email", key=f"{key_prefix}_copy_email_{chosen}")
    with c2:
        copy_button(subj, "Copy subject", key=f"{key_prefix}_copy_subject_{chosen}")
    with c3:
        copy_button(body, "Copy body", key=f"{key_prefix}_copy_body_{chosen}")

    st.download_button(
        "Download supplier email as .txt",
        data=(f"To: {supplier_email}\nSubject: {subj}\n\n{body}").encode("utf-8"),
        file_name=f"supplier_email_{str(chosen)}".replace(" ", "_").lower() + ".txt",
        mime="text/plain",
        key=f"{key_prefix}_download_txt",
    )

    # ----------------------------
    # One-click compose + Follow-up tracking
    # ----------------------------
    store = IssueTrackerStore(issue_tracker_path)

    issue_ids: list[str] = []
    if "issue_id" in followups_open.columns:
        issue_ids = (
            followups_open.loc[followups_open["supplier_name"] == chosen, "issue_id"]
            .dropna()
            .astype(str)
            .tolist()
        )

    _ml = mailto_link_fn if callable(mailto_link_fn) else _mailto_fallback
    compose_url = _ml(supplier_email, subj, body)


    # Actions + tracking + bulk updates (split to keep file small)
    from ui.supplier_followups_actions_ui import render_followups_tracking_and_bulk_actions

    render_followups_tracking_and_bulk_actions(
        issue_tracker_path=issue_tracker_path,
        chosen=chosen,
        issue_ids=issue_ids,
        supplier_email=supplier_email,
        compose_url=compose_url,
        contact_statuses=contact_statuses,
        key_prefix=key_prefix,
        scorecard=scorecard,
        build_supplier_accountability_view=build_supplier_accountability_view,
        render_supplier_accountability=render_supplier_accountability,
    )
