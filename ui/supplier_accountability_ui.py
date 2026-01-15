# ui/supplier_accountability_ui.py
from __future__ import annotations

import pandas as pd
import streamlit as st


def _safe_sort(df: pd.DataFrame, by: str, ascending: bool = True) -> pd.DataFrame:
    """Sort only if the column exists. (Avoids pandas 'errors=' kwargs crashes.)"""
    if df is None or df.empty:
        return df
    if by in df.columns:
        return df.sort_values(by=by, ascending=ascending, kind="mergesort")
    return df


def render_supplier_accountability(accountability: pd.DataFrame | None):
    """
    UI for Supplier Accountability.

    Supports BOTH schemas (old + new) by rendering best-effort columns:
      supplier_name, worst_escalation, open_issues, critical, high,
      next_action, owner, last_contacted, score, risk, notes
    """
    st.subheader("Supplier Accountability")

    if accountability is None or getattr(accountability, "empty", True):
        st.caption("No supplier accountability items available for this run.")
        return

    df = accountability.copy()

    # Normalize a few common variants (schema tolerance)
    rename_map = {}
    if "supplier" in df.columns and "supplier_name" not in df.columns:
        rename_map["supplier"] = "supplier_name"
    if "escalation" in df.columns and "worst_escalation" not in df.columns:
        rename_map["escalation"] = "worst_escalation"
    if "actions" in df.columns and "next_action" not in df.columns:
        rename_map["actions"] = "next_action"
    if rename_map:
        df = df.rename(columns=rename_map)

    preferred = [
        "supplier_name",
        "worst_escalation",
        "open_issues",
        "critical",
        "high",
        "score",
        "risk",
        "next_action",
        "owner",
        "last_contacted",
        "notes",
    ]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[cols]

    # Filters
    c1, c2, c3 = st.columns(3)
    with c1:
        supplier_q = st.text_input("Filter supplier", value="", key="sa_filter_supplier")
    with c2:
        min_open = st.number_input("Min open issues", min_value=0, value=0, step=1, key="sa_min_open")
    with c3:
        show_only_escalated = st.checkbox("Only escalated", value=False, key="sa_only_escalated")

    if supplier_q:
        if "supplier_name" in df.columns:
            df = df[df["supplier_name"].astype(str).str.contains(supplier_q, case=False, na=False)]

    if min_open and "open_issues" in df.columns:
        df = df[pd.to_numeric(df["open_issues"], errors="coerce").fillna(0) >= float(min_open)]

    if show_only_escalated and "worst_escalation" in df.columns:
        df = df[df["worst_escalation"].astype(str).str.strip().ne("").fillna(False)]

    # Sort (NO 'errors=' kwarg)
    # Prefer sorting by "worst_escalation" or "open_issues" if present.
    if "worst_escalation" in df.columns:
        df = _safe_sort(df, "worst_escalation", ascending=True)
    elif "open_issues" in df.columns:
        df = _safe_sort(df, "open_issues", ascending=False)

    st.dataframe(df, use_container_width=True, hide_index=True)
