# ui/customer_impact_ui.py
import pandas as pd
import streamlit as st


def render_customer_impact_view(customer_impact: pd.DataFrame) -> None:
    if customer_impact is None or customer_impact.empty:
        st.caption("No customer-impact items to show.")
        return

    st.markdown("**Customer Impact Candidates**")
    cols = [c for c in ["order_id", "customer_email", "customer_country", "worst_urgency", "reason"] if c in customer_impact.columns]
    if not cols:
        st.dataframe(customer_impact, use_container_width=True, height=260)
        return

    st.dataframe(customer_impact[cols], use_container_width=True, height=260)
