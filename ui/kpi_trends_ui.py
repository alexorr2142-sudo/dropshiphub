# ui/kpi_trends_ui.py
import streamlit as st
import pandas as pd

from core.kpi_trends import load_kpi_history, compute_trend_delta


def _fmt_pct(x):
    try:
        return f"{float(x):.1f}%"
    except Exception:
        return "—"


def render_kpi_trends(workspaces_dir, account_id: str, store_id: str):
    st.divider()
    st.subheader("KPI Trends Over Time (from saved runs)")

    # UX: explain dependency
    st.caption(
        "This chart uses your saved runs. Click **Save this run** in the sidebar every day to build trend history."
    )

    c1, c2 = st.columns(2)
    with c1:
        max_runs = st.slider("Use last N saved runs", 5, 120, 30, 5, key="kpi_trends_max_runs")
    with c2:
        show_workspace = st.checkbox("Show workspace breakdown", value=False, key="kpi_trends_show_workspace")

    df = load_kpi_history(workspaces_dir, account_id, store_id, max_runs=int(max_runs))

    if df is None or df.empty:
        st.info("No saved runs found yet. Save at least 2 runs to see KPI trends.")
        return

    # optional filter by workspace
    if show_workspace and "workspace_name" in df.columns:
        opts = ["(all)"] + sorted(
            [x for x in df["workspace_name"].dropna().unique().tolist() if str(x).strip() != ""]
        )
        chosen = st.selectbox("Workspace", opts, index=0, key="kpi_trends_workspace_select")
        if chosen != "(all)":
            df = df[df["workspace_name"] == chosen].copy()
            if df.empty:
                st.info("No runs for that workspace yet.")
                return

    # Trend tiles (compare last 2)
    t1, t2, t3, t4 = st.columns(4)

    latest_unsh, prev_unsh, delta_unsh = compute_trend_delta(df, "pct_unshipped")
    latest_late, prev_late, delta_late = compute_trend_delta(df, "pct_late_unshipped")
    latest_del, prev_del, delta_del = compute_trend_delta(df, "pct_delivered")
    latest_ship, prev_ship, delta_ship = compute_trend_delta(df, "pct_shipped_or_delivered")

    def _delta_str(d):
        if d is None:
            return None
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.1f} pts"

    # If KPIs are stored as whole percents (like 12.3) these are good.
    t1.metric("% Unshipped", _fmt_pct(latest_unsh), _delta_str(delta_unsh))
    t2.metric("% Late Unshipped", _fmt_pct(latest_late), _delta_str(delta_late))
    t3.metric("% Delivered", _fmt_pct(latest_del), _delta_str(delta_del))
    t4.metric("% Shipped/Delivered", _fmt_pct(latest_ship), _delta_str(delta_ship))

    st.divider()

    # Chart selection
    metric_map = {
        "% Unshipped": "pct_unshipped",
        "% Late Unshipped": "pct_late_unshipped",
        "% Delivered": "pct_delivered",
        "% Shipped/Delivered": "pct_shipped_or_delivered",
        "Exceptions count": "exceptions",
        "Follow-ups count": "followups",
        "Total order lines": "total_order_lines",
    }

    chosen_label = st.selectbox("Metric to chart", list(metric_map.keys()), index=1, key="kpi_trends_metric_select")
    col = metric_map[chosen_label]

    chart_df = df[["run_dt", col]].dropna().copy()
    if chart_df.empty:
        st.info("No data for that metric yet.")
        return

    chart_df = chart_df.set_index("run_dt")
    st.line_chart(chart_df)

    # ---- Optional improvement: show run_dt in the table (formatted), and fix KeyError by sorting before column selection
    with st.expander("See saved KPI history table", expanded=False):
        view_df = df.copy()

        # Format the datetime column nicely for display
        if "run_dt" in view_df.columns:
            view_df["run_dt"] = pd.to_datetime(view_df["run_dt"], errors="coerce")
            view_df["run_date"] = view_df["run_dt"].dt.strftime("%Y-%m-%d %H:%M")
        else:
            view_df["run_date"] = ""

        show_cols = [
            "run_date",  # <- display-friendly timestamp
            "run_id",
            "workspace_name",
            "pct_unshipped",
            "pct_late_unshipped",
            "pct_delivered",
            "pct_shipped_or_delivered",
            "exceptions",
            "followups",
            "total_order_lines",
        ]
        show_cols = [c for c in show_cols if c in view_df.columns]

        # Sort first using run_dt (even if we don't display it)
        if "run_dt" in view_df.columns:
            view_df = view_df.sort_values("run_dt", ascending=False)

        st.dataframe(view_df[show_cols], use_container_width=True, height=260)
