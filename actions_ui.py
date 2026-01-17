# ui/actions_ui.py
import pandas as pd
import streamlit as st


def _apply_search(df: pd.DataFrame, q: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    q = (q or "").strip().lower()
    if not q:
        return df

    # Search across all columns (stringified)
    blob = df.astype(str).fillna("").agg(" ".join, axis=1).str.lower()
    return df[blob.str.contains(q, na=False)].copy()


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

    # Global search
    q = st.text_input("Search actions (order id, SKU, supplier, keyword)", value="", key="daily_actions_search")

    cust_v = _apply_search(cust, q)
    supp_v = _apply_search(supp, q)
    watch_v = _apply_search(watch, q)

    tab1, tab2, tab3 = st.tabs(
        [
            f"🔴 Customer ({0 if cust_v is None else len(cust_v)})",
            f"🟠 Supplier ({0 if supp_v is None else len(supp_v)})",
            f"🟡 Watchlist ({0 if watch_v is None else len(watch_v)})",
        ]
    )

    with tab1:
        if cust_v is None or cust_v.empty:
            st.caption("Nothing urgent found for customer-facing action.")
        else:
            st.dataframe(cust_v, use_container_width=True, height=320)
            st.download_button(
                "Download customer actions CSV",
                data=cust_v.to_csv(index=False).encode("utf-8"),
                file_name="daily_customer_actions.csv",
                mime="text/csv",
                key="dl_customer_actions",
            )

    with tab2:
        if supp_v is None or supp_v.empty:
            st.caption("No supplier follow-ups needed.")
        else:
            st.dataframe(supp_v, use_container_width=True, height=320)
            st.download_button(
                "Download supplier actions CSV",
                data=supp_v.to_csv(index=False).encode("utf-8"),
                file_name="daily_supplier_actions.csv",
                mime="text/csv",
                key="dl_supplier_actions",
            )

    with tab3:
        if watch_v is None or watch_v.empty:
            st.caption("No watchlist items.")
        else:
            st.dataframe(watch_v, use_container_width=True, height=320)
            st.download_button(
                "Download watchlist CSV",
                data=watch_v.to_csv(index=False).encode("utf-8"),
                file_name="daily_watchlist.csv",
                mime="text/csv",
                key="dl_watchlist",
            )
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
