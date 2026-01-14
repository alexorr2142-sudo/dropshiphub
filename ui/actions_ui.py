# ui/actions_ui.py
import pandas as pd
import streamlit as st


def render_daily_action_list(actions: dict):
    st.divider()
    st.subheader("Daily Action List (What to do today)")

    summary = actions.get("summary", {}) or {}
    c1, c2, c3 = st.columns(3)
    c1.metric("Customer actions", summary.get("customer_actions", 0))
    c2.metric("Supplier actions", summary.get("supplier_actions", 0))
    c3.metric("Watchlist", summary.get("watchlist", 0))

    cust = actions.get("customer_actions", pd.DataFrame())
    supp = actions.get("supplier_actions", pd.DataFrame())
    watch = actions.get("watchlist", pd.DataFrame())

    with st.expander("🔴 Customer actions (protect customer experience)", expanded=True):
        if cust is None or cust.empty:
            st.caption("Nothing urgent found for customer-facing action.")
        else:
            st.dataframe(cust, use_container_width=True, height=260)
            st.download_button(
                "Download customer actions CSV",
                data=cust.to_csv(index=False).encode("utf-8"),
                file_name="daily_customer_actions.csv",
                mime="text/csv",
            )

    with st.expander("🟠 Supplier actions (send follow-ups)", expanded=True):
        if supp is None or supp.empty:
            st.caption("No supplier follow-ups needed.")
        else:
            st.dataframe(supp, use_container_width=True, height=240)
            st.download_button(
                "Download supplier actions CSV",
                data=supp.to_csv(index=False).encode("utf-8"),
                file_name="daily_supplier_actions.csv",
                mime="text/csv",
            )

    with st.expander("🟡 Watchlist (keep an eye on these)", expanded=False):
        if watch is None or watch.empty:
            st.caption("No watchlist items.")
        else:
            st.dataframe(watch, use_container_width=True, height=220)
