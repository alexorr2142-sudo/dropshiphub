# ui/supplier_accountability_ui.py
from __future__ import annotations

import io
from typing import Optional

import pandas as pd
import streamlit as st


def render_supplier_accountability(
    accountability: pd.DataFrame | None,
    *,
    title: str = "Supplier Accountability",
    key_prefix: str = "sa",
) -> None:
    """
    UI-only component.

    IMPORTANT:
    - This file must NOT render pages at import time.
    - No st.set_page_config(), no st.title(), no gates here.
    - app.py is the orchestrator; this module is a component.

    Expected columns (best effort):
      supplier_name, open_issues, critical, high, worst_escalation,
      next_action, owner, last_contacted
    """
    st.subheader(title)

    if accountability is None or getattr(accountability, "empty", True):
        st.caption("No supplier accountability items available for this run.")
        return

    df = accountability.copy()

    # ---- Normalize a few common column variants (best effort, non-destructive)
    rename_map = {}
    if "supplier" in df.columns and "supplier_name" not in df.columns:
        rename_map["supplier"] = "supplier_name"
    if "escalation" in df.columns and "worst_escalation" not in df.columns:
        rename_map["escalation"] = "worst_escalation"
    if rename_map:
        df = df.rename(columns=rename_map)

    # ---- Filters
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        q = st.text_input(
            "Search supplier",
            value="",
            key=f"{key_prefix}_q",
            placeholder="Type a supplier name…",
        ).strip()
    with c2:
        urg = st.selectbox(
            "Escalation",
            options=["All", "Critical", "High", "Medium", "Low"],
            index=0,
            key=f"{key_prefix}_urg",
        )
    with c3:
        show_top = st.number_input(
            "Show top N",
            min_value=5,
            max_value=200,
            value=50,
            step=5,
            key=f"{key_prefix}_topn",
        )

    if "supplier_name" in df.columns and q:
        df = df[df["supplier_name"].fillna("").astype(str).str.contains(q, case=False, na=False)]

    if urg != "All" and "worst_escalation" in df.columns:
        df = df[df["worst_escalation"].fillna("").astype(str).str.lower() == urg.lower()]

    # ---- Column ordering (clean + stable)
    preferred = [
        "supplier_name",
        "worst_escalation",
        "open_issues",
        "critical",
        "high",
        "next_action",
        "owner",
        "last_contacted",
    ]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[cols]

    # ---- Sort best effort
    if "critical" in df.columns:
        df = df.sort_values(by=["critical"], ascending=False, kind="mergesort")
    elif "open_issues" in df.columns:
        df = df.sort_values(by=["open_issues"], ascending=False, kind="mergesort")

    df = df.head(int(show_top))

    # ---- Render
    st.dataframe(df, use_container_width=True, height=420)

    # ---- Download CSV
    try:
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download supplier accountability CSV",
            data=csv_bytes,
            file_name="supplier_accountability.csv",
            mime="text/csv",
            key=f"{key_prefix}_dl",
        )
    except Exception:
        # Optional; never crash the page for download issues
        st.caption("Download unavailable in this environment.")

