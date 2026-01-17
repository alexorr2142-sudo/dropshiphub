from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
import streamlit as st

from ui.app_helpers import call_with_accepted_kwargs, mailto_fallback

def render_ops_outreach_comms(
    *,
    followups_open: pd.DataFrame,
    customer_impact: pd.DataFrame,
    scorecard: pd.DataFrame,
    ws_root: Path,
    issue_tracker_path: Path,
    contact_statuses: list,
    mailto_link_fn: Optional[Callable[[str, str, str], str]] = None,
    build_supplier_accountability_view: Optional[Callable[..., Any]] = None,
    render_supplier_accountability: Optional[Callable[..., Any]] = None,
    render_supplier_followups_tab: Optional[Callable[..., Any]] = None,
    render_customer_comms_ui: Optional[Callable[..., Any]] = None,
    render_comms_pack_download: Optional[Callable[..., Any]] = None,
    account_id: str = "",
    store_id: str = "",
) -> None:
    st.divider()
    st.subheader("Ops Outreach (Comms)")
    tab1, tab2, tab3 = st.tabs(["Supplier Follow-ups", "Customer Emails", "Comms Pack"])

    # Supplier Follow-ups
    with tab1:
        if callable(render_supplier_followups_tab) and isinstance(followups_open, pd.DataFrame):
            render_supplier_followups_tab(
                followups_open=followups_open,
                issue_tracker_path=issue_tracker_path,
                contact_statuses=contact_statuses,
                mailto_link_fn=mailto_link_fn if callable(mailto_link_fn) else mailto_fallback,
                scorecard=scorecard if isinstance(scorecard, pd.DataFrame) else None,
                build_supplier_accountability_view=build_supplier_accountability_view if callable(build_supplier_accountability_view) else None,
                render_supplier_accountability=render_supplier_accountability if callable(render_supplier_accountability) else None,
                key_prefix="supplier_followups",
            )
        else:
            st.caption("Supplier follow-ups UI module not available.")
            if followups_open is None or followups_open.empty:
                st.info("No supplier follow-ups needed.")
            else:
                st.dataframe(followups_open, use_container_width=True, height=260)

    # Customer emails
    with tab2:
        st.caption("Customer-facing updates (email-first).")
        if customer_impact is None or customer_impact.empty:
            st.info("No customer-impact items detected for this run.")
        else:
            if callable(render_customer_comms_ui):
                try:
                    call_with_accepted_kwargs(
                        render_customer_comms_ui,
                        customer_impact=customer_impact,
                        ws_root=ws_root,
                        account_id=account_id,
                        store_id=store_id,
                    )
                except Exception:
                    try:
                        render_customer_comms_ui(customer_impact=customer_impact)
                    except Exception:
                        render_customer_comms_ui(customer_impact)
            else:
                st.dataframe(customer_impact, use_container_width=True, height=320)

    # Comms pack download
    with tab3:
        st.caption("Download combined comms artifacts (supplier + customer).")
        if callable(render_comms_pack_download):
            try:
                call_with_accepted_kwargs(
                    render_comms_pack_download,
                    followups=followups_open,
                    customer_impact=customer_impact,
                    ws_root=ws_root,
                    account_id=account_id,
                    store_id=store_id,
                )
            except Exception:
                try:
                    render_comms_pack_download(followups=followups_open, customer_impact=customer_impact)
                except Exception:
                    render_comms_pack_download()
        else:
            st.info("Comms pack UI module not available.")


