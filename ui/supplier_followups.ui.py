# ui/supplier_followups_ui.py
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import streamlit as st

from core.styling import copy_button
from core.issue_tracker import IssueTrackerStore
from ui.issue_tracker_ui import enrich_followups_with_contact_fields


def _mailto_fallback(to: str, subject: str, body: str) -> str:
    # Local fallback (keeps this file self-contained)
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
    # Optional supplier accountability hook (keeps deps optional)
    build_supplier_accountability_view: Optional[Callable[..., object]] = None,
    render_supplier_accountability: Optional[Callable[..., None]] = None,
    key_prefix: str = "supplier_followups",
) -> None:
    """
    Renders the entire "Supplier Follow-ups" tab.

    Preserves features from app.py:
      - OPEN followups preview
      - contact_status + follow_up_count columns from IssueTrackerStore contact object
      - Supplier email generator (3 questions)
      - Copy buttons for email/subject/body
      - Download .txt of the supplier email
      - One-click compose email (mailto)
      - Mark contacted, Follow-up +1, bulk status set for all issue_ids under supplier
      - Supplier Accountability (Auto) panel if hooks provided
    """
    st.caption("Supplier-facing outreach based on OPEN follow-ups (unresolved only).")

    if followups_open is None or followups_open.empty:
        st.info("No supplier follow-ups needed.")
        return

    # Enrich with contact fields for the preview table
    show_df = enrich_followups_with_contact_fields(
        followups_df=followups_open,
        issue_tracker_path=issue_tracker_path,
    )

    summary_cols = [
        c
        for c in [
            "supplier_name",
            "supplier_email",
            "worst_escalation",
            "urgency",
            "item_count",
            "order_ids",
            "contact_status",
            "follow_up_count",
        ]
        if c in show_df.columns
    ]
    st.dataframe(show_df[summary_cols] if summary_cols else show_df, use_container_width=True, height=220)

    # Supplier email preview + 3 bullet questions generator
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

    # One-click compose + Follow-up tracking
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
            st.success(f"Recorded contacted for {len(issue_ids)} issue(s).")
            st.rerun()

    with ccC:
        if st.button("🔁 Follow-up +1", key=f"{key_prefix}_btn_followup_plus1_{chosen}"):
            for iid in issue_ids:
                try:
                    store.increment_followup(iid, channel="email", note="Follow-up sent")
                except Exception:
                    pass
            st.success(f"Recorded follow-up for {len(issue_ids)} issue(s).")
            st.rerun()

    # Bulk status set
    if contact_statuses:
        default_idx = contact_statuses.index("Waiting") if "Waiting" in contact_statuses else 0
        new_status = st.selectbox(
            "Set supplier issue status",
            contact_statuses,
            index=default_idx,
            key=f"{key_prefix}_status_bulk_{chosen}",
        )
        if st.button("Save status for all supplier issues", key=f"{key_prefix}_btn_status_bulk_{chosen}"):
            for iid in issue_ids:
                try:
                    store.set_contact_status(iid, new_status)
                except Exception:
                    pass
            st.success(f"Set status to {new_status} for {len(issue_ids)} issue(s).")
            st.rerun()

    # Supplier accountability (optional)
    if build_supplier_accountability_view is not None and render_supplier_accountability is not None and scorecard is not None:
        st.divider()
        st.markdown("#### Supplier Accountability (Auto)")
        try:
            # Support multiple signatures
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
