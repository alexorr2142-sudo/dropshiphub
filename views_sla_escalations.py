from __future__ import annotations

import pandas as pd
import streamlit as st

def render_sla_escalations_panel(*, escalations_df: pd.DataFrame) -> None:
    if isinstance(escalations_df, pd.DataFrame) and not escalations_df.empty:
        st.divider()
        st.subheader("SLA Escalations (Supplier-level)")
        st.dataframe(escalations_df, use_container_width=True, height=260)
