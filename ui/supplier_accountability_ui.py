# ui/supplier_accountability_ui.py
import pandas as pd
import streamlit as st

from core.styling import copy_button
from core.supplier_accountability import draft_supplier_performance_note


def render_supplier_accountability(view_df: pd.DataFrame):
    st.divider()
    st.subheader("Supplier Accountability Mode (Who is causing issues?)")

    if view_df is None or view_df.empty:
        st.info("No supplier scorecard data available yet (requires supplier_name in line status).")
        return

    st.caption("Ranked by a weighted pain score (critical/high + tracking/late + exception rate).")
    st.dataframe(view_df, use_container_width=True, height=300)

    st.download_button(
        "Download Supplier Accountability CSV",
        data=view_df.to_csv(index=False).encode("utf-8"),
        file_name="supplier_accountability.csv",
        mime="text/csv",
    )

    st.divider()
    st.markdown("### Supplier performance note (copy/paste)")

    options = list(range(len(view_df)))
    idx = st.selectbox(
        "Choose supplier",
        options=options,
        format_func=lambda i: str(view_df.iloc[i].get("supplier_name", "")),
        key="supplier_accountability_select",
    )

    row = view_df.iloc[int(idx)].to_dict()
    note = draft_supplier_performance_note(row)

    subject = note.get("subject", "")
    body = note.get("body", "")

    c1, c2 = st.columns(2)
    with c1:
        copy_button(subject, "Copy subject", key=f"copy_supplier_perf_subject_{idx}")
    with c2:
        copy_button(body, "Copy body", key=f"copy_supplier_perf_body_{idx}")

    st.text_input("Subject", value=subject, key="supplier_perf_subject_preview")
    st.text_area("Body", value=body, height=220, key="supplier_perf_body_preview")
