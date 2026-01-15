from __future__ import annotations

import pandas as pd
import streamlit as st


def _safe_sort(df: pd.DataFrame, by: str, ascending: bool = True) -> pd.DataFrame:
    """
    Pandas-safe sort: only sort if the column exists.
    Avoids the invalid sort_values(..., errors="ignore") crash.
    """
    if df is None or df.empty:
        return df
    if by in df.columns:
        return df.sort_values(by=by, ascending=ascending, kind="mergesort")
    return df


def render_supplier_accountability(accountability: pd.DataFrame | None):
    """
    Supplier Accountability UI.

    Supports both older and newer schemas (best-effort). Common columns:
      supplier_name / supplier
      worst_escalation / escalation
      open_issues
      critical
      high
      score
      risk
      next_action / actions
      owner
      last_contacted
      notes
    """
    st.subheader("Supplier Accountability")

    if accountability is None or getattr(accountability, "empty", True):
        st.caption("No supplier accountability items available for this run.")
        return

    df = accountability.copy()

    # ---- Schema tolerance (rename common variants) ----
    rename_map = {}
    if "supplier" in df.columns and "supplier_name" not in df.columns:
        rename_map["supplier"] = "supplier_name"
    if "escalation" in df.columns and "worst_escalation" not in df.columns:
        rename_map["escalation"] = "worst_escalation"
    if "actions" in df.columns and "next_action" not in df.columns:
        rename_map["actions"] = "next_action"
    if rename_map:
        df = df.rename(columns=rename_map)

    # ---- Clean column ordering (best-effort) ----
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

    # ---- Light filtering controls ----
    c1, c2, c3 = st.columns(3)
    with c1:
        supplier_q = st.text_input("Filter supplier", value="", key="sa_filter_supplier")
    with c2:
        min_open = st.number_input("Min open issues", min_value=0, value=0, step=1, key="sa_min_open")
    with c3:
        only_escalated = st.checkbox("Only escalated", value=False, key="sa_only_escalated")

    if supplier_q and "supplier_name" in df.columns:
        df = df[df["supplier_name"].astype(str).str.contains(supplier_q, case=False, na=False)]

    if min_open and "open_issues" in df.columns:
        df = df[pd.to_numeric(df["open_issues"], errors="coerce").fillna(0) >= float(min_open)]

    if only_escalated and "worst_escalation" in df.columns:
        df = df[df["worst_escalation"].astype(str).fillna("").str.strip() != ""]

    # ---- Sort (NO invalid 'errors=' kwarg) ----
    if "open_issues" in df.columns:
        df = _safe_sort(df, "open_issues", ascending=False)
    elif "critical" in df.columns:
        df = _safe_sort(df, "critical", ascending=False)
    elif "high" in df.columns:
        df = _safe_sort(df, "high", ascending=False)
    elif "worst_escalation" in df.columns:
        df = _safe_sort(df, "worst_escalation", ascending=True)

    st.dataframe(df, use_container_width=True, hide_index=True)
