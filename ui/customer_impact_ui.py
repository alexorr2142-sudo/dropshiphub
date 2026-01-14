# ui/customer_impact_ui.py
import pandas as pd
import streamlit as st

from core.styling import copy_button


def render_customer_impact_view(df: pd.DataFrame):
    st.divider()
    st.subheader("Customer Impact View (Protect customer experience)")

    if df is None or df.empty:
        st.info("No customer-impact items detected 🎉")
        return

    # Quick filter controls
    c1, c2 = st.columns(2)

    with c1:
        categories = sorted(df["impact_category"].dropna().unique().tolist()) if "impact_category" in df.columns else []
        cat_filter = st.multiselect("Impact category", categories, default=categories)

    with c2:
        urgencies = ["Critical", "High", "Medium", "Low"]
        urg_filter = st.multiselect("Urgency", urgencies, default=[u for u in urgencies if u in df.get("Urgency", []).astype(str).unique()])

    view = df.copy()
    if cat_filter and "impact_category" in view.columns:
        view = view[view["impact_category"].isin(cat_filter)]
    if urg_filter and "Urgency" in view.columns:
        view = view[view["Urgency"].astype(str).isin(urg_filter)]

    st.dataframe(view, use_container_width=True, height=360)

    st.download_button(
        "Download Customer Impact CSV",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name="customer_impact_view.csv",
        mime="text/csv",
    )

    # Message preview tool
    if "customer_message_draft" in view.columns and len(view) > 0:
        st.divider()
        st.markdown("### Customer message preview (copy/paste)")

        label_col = "order_id" if "order_id" in view.columns else None
        options = list(range(len(view)))
        chosen_idx = st.selectbox(
            "Select row",
            options=options,
            format_func=lambda i: f"{view.iloc[i].get('impact_category','')} | Order {view.iloc[i].get(label_col,'')}".strip(),
            key="cust_impact_select",
        )

        row = view.iloc[int(chosen_idx)]
        msg = str(row.get("customer_message_draft", "")).strip()

        copy_button(msg, "Copy customer message", key=f"copy_customer_msg_{chosen_idx}")
        st.text_area("Message draft", value=msg, height=180, key="cust_msg_preview")
