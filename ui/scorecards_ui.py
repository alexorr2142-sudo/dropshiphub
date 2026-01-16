# ui/scorecards_ui.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.scorecards import load_recent_scorecard_history


def render_supplier_scorecards(
    scorecard: pd.DataFrame,
    *,
    ws_root: Path,
    key_prefix: str = "scorecard",
    title: str = "Supplier Scorecards (Performance + Trends)",
) -> None:
    st.subheader(title)

    if scorecard is None or not isinstance(scorecard, pd.DataFrame) or scorecard.empty:
        st.info("Scorecards require `supplier_name` in your normalized line status data.")
        return

    sc1, sc2 = st.columns(2)
    with sc1:
        top_n = st.slider(
            "Show top N suppliers",
            min_value=5,
            max_value=50,
            value=15,
            step=5,
            key=f"{key_prefix}_top_n",
        )
    with sc2:
        min_lines = st.number_input(
            "Min total lines",
            min_value=1,
            max_value=1_000_000,
            value=1,
            step=1,
            key=f"{key_prefix}_min_lines",
        )

    view = scorecard[scorecard["total_lines"] >= int(min_lines)].head(int(top_n))

    show_cols = [
        "supplier_name",
        "total_lines",
        "exception_lines",
        "exception_rate",
        "critical",
        "high",
        "missing_tracking_flags",
        "late_flags",
        "carrier_exception_flags",
    ]
    show_cols = [c for c in show_cols if c in view.columns]
    st.dataframe(view[show_cols] if show_cols else view, use_container_width=True, height=320)

    st.download_button(
        "Download Supplier Scorecards CSV",
        data=scorecard.to_csv(index=False).encode("utf-8"),
        file_name="supplier_scorecards.csv",
        mime="text/csv",
        key=f"{key_prefix}_dl_scorecards_csv",
    )

    with st.expander("Trend over time (from saved runs)", expanded=True):
        runs_for_trend_exist = ws_root.exists() and any(ws_root.iterdir())
        if not runs_for_trend_exist:
            st.caption("No saved runs yet. Click **Save this run** to build trend history.")
            return

        max_runs = st.slider(
            "Use last N saved runs",
            5,
            50,
            25,
            5,
            key=f"{key_prefix}_trend_max_runs",
        )
        hist = load_recent_scorecard_history(str(ws_root), max_runs=int(max_runs))

        if hist is None or hist.empty:
            st.caption("No historical scorecards found yet (save a run first).")
            return

        supplier_options = sorted(hist["supplier_name"].dropna().unique().tolist())
        if not supplier_options:
            st.caption("No supplier names found in historical scorecards.")
            return

        chosen_supplier = st.selectbox(
            "Supplier",
            supplier_options,
            key=f"{key_prefix}_trend_supplier",
        )

        s_hist = hist[hist["supplier_name"] == chosen_supplier].copy()
        if "run_dt" in s_hist.columns:
            s_hist = s_hist.sort_values("run_dt")

        chart_df = s_hist[["run_dt", "exception_rate"]].dropna() if {"run_dt", "exception_rate"} <= set(s_hist.columns) else pd.DataFrame()
        if not chart_df.empty:
            st.line_chart(chart_df.set_index("run_dt"))

        tcols = ["run_id", "total_lines", "exception_lines", "exception_rate", "critical", "high"]
        tcols = [c for c in tcols if c in s_hist.columns]
        if tcols:
            st.dataframe(
                s_hist[tcols].sort_values("run_id", ascending=False),
                use_container_width=True,
                height=220,
            )
