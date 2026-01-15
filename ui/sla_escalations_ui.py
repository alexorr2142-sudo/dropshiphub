# ui/sla_escalations_ui.py
import pandas as pd
import streamlit as st

from core.sla_escalations import build_sla_escalations

# Optional: use your existing copy_button if it exists
try:
    from core.styling import copy_button
except Exception:
    copy_button = None


def render_sla_escalations(
    line_status_df: pd.DataFrame,
    followups: pd.DataFrame,
    promised_ship_days: int,
):
    st.divider()
    st.subheader("Supplier SLA Escalations (Prevent fires)")

    c1, c2, c3 = st.columns(3)
    with c1:
        sla_days = st.number_input("Promised ship days (SLA)", min_value=1, max_value=30, value=int(promised_ship_days), step=1)
    with c2:
        grace_days = st.number_input("Grace days", min_value=0, max_value=14, value=1, step=1)
    with c3:
        apply_templates = st.checkbox("Apply suggested subject/body to followups", value=False)

    escalations, updated_followups = build_sla_escalations(
        line_status_df=line_status_df,
        followups=followups,
        promised_ship_days=int(sla_days),
        grace_days=int(grace_days),
    )

    if escalations is None or escalations.empty:
        st.info("No SLA escalations detected (or missing promised/created date + supplier_name).")
        return followups

    # Filters
    levels = ["Escalate", "Firm Follow-up", "Reminder", "At Risk (72h)", "On Track"]
    chosen_levels = st.multiselect(
        "Show levels",
        levels,
        default=["Escalate", "Firm Follow-up", "Reminder", "At Risk (72h)"],
        key="sla_levels_filter",
    )

    view = escalations.copy()
    if chosen_levels and "worst_escalation" in view.columns:
        view = view[view["worst_escalation"].isin(chosen_levels)].copy()

    show_cols = [c for c in [
        "supplier_name",
        "worst_escalation",
        "max_days_past_due",
        "min_days_to_due",
        "unshipped_lines",
        "sku_count",
        "order_count",
    ] if c in view.columns]

    st.dataframe(view[show_cols], use_container_width=True, height=300)

    st.download_button(
        "Download SLA Escalations CSV",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name="sla_escalations.csv",
        mime="text/csv",
        key="dl_sla_escalations",
    )

    # Email preview
    with st.expander("Suggested escalation email (pick a supplier)", expanded=False):
        opts = view["supplier_name"].dropna().unique().tolist()
        if not opts:
            st.caption("No suppliers in this filtered view.")
        else:
            chosen = st.selectbox("Supplier", opts, key="sla_supplier_pick")
            row = view[view["supplier_name"] == chosen].iloc[0]

            subj = str(row.get("subject_suggested", "")).strip()
            body = str(row.get("body_suggested", "")).strip()

            if copy_button is not None:
                cA, cB = st.columns(2)
                with cA:
                    copy_button(subj, "Copy subject", key=f"sla_copy_subject_{chosen}")
                with cB:
                    copy_button(body, "Copy body", key=f"sla_copy_body_{chosen}")

            st.text_input("Subject", value=subj, key="sla_subject_preview")
            st.text_area("Body", value=body, height=240, key="sla_body_preview")

    # Optionally overwrite followup subject/body with suggested templates
    if apply_templates and updated_followups is not None and not updated_followups.empty:
        f = updated_followups.copy()
        if "subject" in f.columns and "subject_suggested" in f.columns:
            f["subject"] = f["subject_suggested"].fillna(f["subject"])
        if "body" in f.columns and "body_suggested" in f.columns:
            f["body"] = f["body_suggested"].fillna(f["body"])
        # keep helpful columns, but you can drop suggesteds if you want
        return f

    return updated_followups
