# ui/demo_health.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.demo_schema import validate_demo_inputs


def render_demo_health_badge(data_dir: Path) -> None:
    """
    Sidebar health indicator for ClearOps Demo mode.
    No dependency on app.py changes.
    """
    demo_on = bool(st.session_state.get("demo_mode", st.session_state.get("app_demo_mode", False)))
    if not demo_on:
        st.caption("ClearOps Demo Health: (off)")
        return

    raw_orders = st.session_state.get("demo_raw_orders", pd.DataFrame())
    raw_shipments = st.session_state.get("demo_raw_shipments", pd.DataFrame())
    raw_tracking = st.session_state.get("demo_raw_tracking", pd.DataFrame())

    report = validate_demo_inputs(raw_orders, raw_shipments, raw_tracking)

    if report.level == "ok":
        st.success("ClearOps Demo Health: OK", icon="✅")
    elif report.level == "warn":
        st.warning("ClearOps Demo Health: WARN", icon="⚠️")
    else:
        st.error("ClearOps Demo Health: BROKEN", icon="🛑")

    with st.expander("ClearOps demo health details", expanded=False):
        for m in report.messages:
            st.write("- ", m)
        st.caption(f"Demo files expected in: {data_dir.as_posix()}")
