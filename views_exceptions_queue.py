from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd
import streamlit as st

def render_exceptions_queue_section(
    *,
    exceptions: pd.DataFrame,
    style_exceptions_table: Optional[Callable[..., Any]] = None,
    render_exceptions_queue: Optional[Callable[..., Any]] = None,
) -> None:
    st.divider()
    if callable(render_exceptions_queue):
        render_exceptions_queue(exceptions, key_prefix="exq", height=420)
        return

    st.subheader("Exceptions Queue (Action this first)")
    if exceptions is None or exceptions.empty:
        st.info("No exceptions found 🎉")
        return

    fcol1, fcol2, fcol3, fcol4 = st.columns(4)

    with fcol1:
        issue_types = (
            sorted(exceptions["issue_type"].dropna().unique().tolist()) if "issue_type" in exceptions.columns else []
        )
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types, key="exq_issue_types")

    with fcol2:
        countries = sorted(
            [
                c
                for c in exceptions.get("customer_country", pd.Series([], dtype="object")).dropna().unique().tolist()
                if str(c).strip() != ""
            ]
        )
        country_filter = st.multiselect("Customer country", countries, default=countries, key="exq_countries")

    with fcol3:
        suppliers = sorted(
            [
                s
                for s in exceptions.get("supplier_name", pd.Series([], dtype="object")).dropna().unique().tolist()
                if str(s).strip() != ""
            ]
        )
        supplier_filter = st.multiselect("Supplier", suppliers, default=suppliers, key="exq_suppliers")

    with fcol4:
        urgencies = ["Critical", "High", "Medium", "Low"]
        urgency_filter = st.multiselect("Urgency", urgencies, default=urgencies, key="exq_urgency")

    filtered = exceptions.copy()
    if issue_filter and "issue_type" in filtered.columns:
        filtered = filtered[filtered["issue_type"].isin(issue_filter)]
    if country_filter and "customer_country" in filtered.columns:
        filtered = filtered[filtered["customer_country"].isin(country_filter)]
    if supplier_filter and "supplier_name" in filtered.columns:
        filtered = filtered[filtered["supplier_name"].isin(supplier_filter)]
    if urgency_filter and "Urgency" in filtered.columns:
        filtered = filtered[filtered["Urgency"].isin(urgency_filter)]

    sort_cols = [c for c in ["Urgency", "order_id"] if c in filtered.columns]
    if sort_cols:
        filtered = filtered.sort_values(sort_cols, ascending=True)

    preferred_cols = [
        "Urgency",
        "order_id",
        "sku",
        "issue_type",
        "customer_country",
        "supplier_name",
        "quantity_ordered",
        "quantity_shipped",
        "line_status",
        "explanation",
        "next_action",
        "customer_risk",
    ]
    show_cols = [c for c in preferred_cols if c in filtered.columns]

    if callable(style_exceptions_table) and show_cols:
        st.dataframe(style_exceptions_table(filtered[show_cols]), use_container_width=True, height=420)
    else:
        st.dataframe(filtered[show_cols] if show_cols else filtered, use_container_width=True, height=420)

    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
        key="dl_exceptions_csv",
    )


