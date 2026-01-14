# ui/sla_escalations_ui.py
import streamlit as st
import pandas as pd

from core.sla_escalations import build_sla_escalations


def render_sla_escalations(line_status_df: pd.DataFrame, followups: pd.DataFrame, promised_ship_days: int):
    st.divider()
    st.subheader("Supplier SLA Escalations (Auto-escalation)")

    c1, c2, c3 = st.columns(3)
    with c1:
        sla_days = st.number_input("Promised ship days (SLA)", min_value=1, max_value=30, value=int(promised_ship_days), step=1)
    with c2:
        grace_days = st.number_input("Grace days", min_value=0, max_value=14, value=1, step=1)
    with c3:
        st.caption("Escalation: On Track → Reminder → Firm Follow-up → Escalate")

    escalations, updated_followups = build_sla_escalations(
        line_status_df=line_status_df,
        followups=followups,
        promised_ship_days=int(sla_days),
        grace_days=int(grace_days),
    )

    if escalations is None or escalations.empty:
        st.info("No SLA escalations detected (or missing order created date / supplier_name columns).")
        return updated_followups

    # Filter
    levels = ["Escalate", "Firm Follow-up", "Reminder", "On Track"]
    level_filter = st.multiselect("Show levels", levels, default=["Escalate", "Firm Follow-up", "Reminder"])
    view = escalations.copy()
    if level_filter and "worst_escalation" in view.columns:
        view = view[view["worst_escalation"].isin(level_filter)]

    st.dataframe(
        view[
            [
                c
                for c in [
                    "supplier_name",
                    "worst_escalation",
                    "max_days_past_due",
                    "unshipped_lines",
                    "sku_count",
                    "order_count",
                ]
                if c in view.columns
            ]
        ],
        use_container_width=True,
        height=280,
    )

    with st.expander("Suggested escalation email (pick a supplier)", expanded=False):
        opts = view["supplier_name"].dropna().unique().tolist()
        if not opts:
            st.caption("No suppliers in this view.")
        else:
            chosen = st.selectbox("Supplier", opts, key="sla_email_supplier_pick")
            row = view[view["supplier_name"] == chosen].iloc[0]
            st.text_input("Subject", value=str(row.get("subject_suggested", "")), key="sla_subject_preview")
            st.text_area("Body", value=str(row.get("body_suggested", "")), height=240, key="sla_body_preview")

    st.download_button(
        "Download SLA Escalations CSV",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name="sla_escalations.csv",
        mime="text/csv",
    )

    return updated_followups
