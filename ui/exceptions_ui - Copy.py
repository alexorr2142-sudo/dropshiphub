# ui/exceptions_ui.py
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.styling import style_exceptions_table


def render_exceptions_queue(
    exceptions: pd.DataFrame,
    *,
    key_prefix: str = "exq",
    height: int = 420,
) -> None:
    """
    Renders the Exceptions Queue exactly like app.py:

      - Issue type multiselect (default all)
      - Customer country multiselect (default all)
      - Supplier multiselect (default all)
      - Urgency multiselect (default all)
      - Sort by Urgency then order_id (when present)
      - Styled table (row color by Urgency)
      - Download filtered exceptions CSV

    Requirements (best effort):
      - exceptions df should include columns: issue_type, customer_country, supplier_name, Urgency, order_id, etc.
    """
    st.subheader("Exceptions Queue (Action this first)")

    if exceptions is None or not isinstance(exceptions, pd.DataFrame) or exceptions.empty:
        st.info("No exceptions found 🎉")
        return

    fcol1, fcol2, fcol3, fcol4 = st.columns(4)

    with fcol1:
        issue_types = (
            sorted(exceptions["issue_type"].dropna().unique().tolist())
            if "issue_type" in exceptions.columns
            else []
        )
        issue_filter = st.multiselect(
            "Issue types",
            issue_types,
            default=issue_types,
            key=f"{key_prefix}_issue_types",
        )

    with fcol2:
        countries = (
            sorted(
                [
                    c
                    for c in exceptions.get("customer_country", pd.Series([], dtype="object"))
                    .dropna()
                    .unique()
                    .tolist()
                    if str(c).strip() != ""
                ]
            )
            if "customer_country" in exceptions.columns or "customer_country" in exceptions.keys()
            else []
        )
        country_filter = st.multiselect(
            "Customer country",
            countries,
            default=countries,
            key=f"{key_prefix}_countries",
        )

    with fcol3:
        suppliers = (
            sorted(
                [
                    s
                    for s in exceptions.get("supplier_name", pd.Series([], dtype="object"))
                    .dropna()
                    .unique()
                    .tolist()
                    if str(s).strip() != ""
                ]
            )
            if "supplier_name" in exceptions.columns or "supplier_name" in exceptions.keys()
            else []
        )
        supplier_filter = st.multiselect(
            "Supplier",
            suppliers,
            default=suppliers,
            key=f"{key_prefix}_suppliers",
        )

    with fcol4:
        urgencies = ["Critical", "High", "Medium", "Low"]
        urgency_filter = st.multiselect(
            "Urgency",
            urgencies,
            default=urgencies,
            key=f"{key_prefix}_urgency",
        )

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

    st.dataframe(
        style_exceptions_table(filtered[show_cols]),
        use_container_width=True,
        height=int(height),
    )

    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
        key=f"{key_prefix}_dl_exceptions_csv",
    )
