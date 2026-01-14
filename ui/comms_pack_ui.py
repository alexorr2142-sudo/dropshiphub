# ui/comms_pack_ui.py
import streamlit as st
import pandas as pd

from core.comms_pack import make_comms_pack_bytes


def render_comms_pack_download(followups: pd.DataFrame, customer_impact: pd.DataFrame):
    st.divider()
    st.subheader("Bulk Comms Pack (ZIP)")

    c1, c2 = st.columns(2)
    with c1:
        max_supplier = st.slider("Max supplier emails", 5, 200, 50, 5)
    with c2:
        max_customer = st.slider("Max customer messages", 5, 200, 50, 5)

    zip_bytes, zip_name = make_comms_pack_bytes(
        followups=followups,
        customer_impact=customer_impact,
        max_supplier=int(max_supplier),
        max_customer=int(max_customer),
    )

    st.download_button(
        "⬇️ Download Bulk Comms Pack ZIP",
        data=zip_bytes,
        file_name=zip_name,
        mime="application/zip",
        use_container_width=True,
        key="btn_bulk_comms_pack",
    )

    st.caption("Includes per-supplier follow-up emails and per-order customer message drafts.")
