# ui/customer_impact_ui.py
import streamlit as st
import pandas as pd


def render_customer_impact_view(customer_impact: pd.DataFrame):
    st.divider()
    st.subheader("Customer Impact View (Who should be notified)")

    if customer_impact is None or customer_impact.empty:
        st.info("No customer-impact items detected.")
        return

    st.dataframe(customer_impact, use_container_width=True, height=320)

    st.download_button(
        "Download Customer Impact CSV",
        data=customer_impact.to_csv(index=False).encode("utf-8"),
        file_name="customer_impact.csv",
        mime="text/csv",
    )
