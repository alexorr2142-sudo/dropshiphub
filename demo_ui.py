from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd
import streamlit as st

from ui.demo_state import _demo_mode_active, _infer_data_dir, _load_demo_files, ensure_demo_state

def render_demo_editor(key_prefix: str = "demo") -> None:
    """
    Main-page demo editors (3 tables). Edits persist while demo mode is on.
    """
    if not _demo_mode_active():
        st.info("Turn on **Demo Mode (Sticky)** in the sidebar to play with demo data (edits persist).")
        return

    st.success("Demo mode is ON (sticky). Your demo edits persist until you turn demo mode off or reset.")

    # Friendly schema status
    rep = st.session_state.get("demo_schema_report")
    if isinstance(rep, dict) and rep.get("level") in ("warn", "error"):
        level = rep.get("level")
        if level == "warn":
            st.warning("Demo data loaded with warnings. See details below.")
        else:
            st.error("Demo data is missing required columns. Fix demo CSVs in /data.")
        with st.expander("Demo schema details", expanded=False):
            for m in rep.get("messages", []):
                st.write("- ", m)

    c0, _ = st.columns([1, 3])
    with c0:
        if st.button("Reset demo from CSV files", use_container_width=True, key=f"{key_prefix}_btn_reset"):
            data_dir = _infer_data_dir()
            _reset_demo_tables(data_dir)
            ensure_demo_state(data_dir)
            st.success("Demo reset ✅")
            st.rerun()

    with st.expander("Edit demo data (these edits persist)", expanded=True):
        c1, c2, c3 = st.columns(3)

        with c1:
            st.caption("raw_orders.csv (demo)")
            st.session_state[DEMO_KEYS["orders"]] = st.data_editor(
                st.session_state.get(DEMO_KEYS["orders"], pd.DataFrame()),
                use_container_width=True,
                height=280,
                num_rows="dynamic",
                key=f"{key_prefix}_orders_editor",
            )

        with c2:
            st.caption("raw_shipments.csv (demo)")
            st.session_state[DEMO_KEYS["shipments"]] = st.data_editor(
                st.session_state.get(DEMO_KEYS["shipments"], pd.DataFrame()),
                use_container_width=True,
                height=280,
                num_rows="dynamic",
                key=f"{key_prefix}_shipments_editor",
            )

        with c3:
            st.caption("raw_tracking.csv (demo)")
            st.session_state[DEMO_KEYS["tracking"]] = st.data_editor(
                st.session_state.get(DEMO_KEYS["tracking"], pd.DataFrame()),
                use_container_width=True,
                height=280,
                num_rows="dynamic",
                key=f"{key_prefix}_tracking_editor",
            )

    # Recompute schema report after edits
    try:
        report = validate_demo_inputs(
            st.session_state.get(DEMO_KEYS["orders"], pd.DataFrame()),
            st.session_state.get(DEMO_KEYS["shipments"], pd.DataFrame()),
            st.session_state.get(DEMO_KEYS["tracking"], pd.DataFrame()),
        )
        st.session_state["demo_schema_report"] = {
            "ok": report.ok,
            "level": report.level,
            "messages": report.messages,
        }
    except Exception:
        pass

    # NEW: Fork demo edits into a workspace snapshot (RAW CSVs)
    try:
        render_demo_fork_controls(
            raw_orders=st.session_state.get(DEMO_KEYS["orders"], pd.DataFrame()),
            raw_shipments=st.session_state.get(DEMO_KEYS["shipments"], pd.DataFrame()),
            raw_tracking=st.session_state.get(DEMO_KEYS["tracking"], pd.DataFrame()),
            key_prefix=f"{key_prefix}_fork",
        )
    except Exception:
        # Never let optional UI break the main app
        pass


def get_active_raw_inputs(
    demo_mode_active: bool,
    data_dir: Path,
    f_orders,
    f_shipments,
    f_tracking,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Must match app.py call signature.

    Chooses between:
      - sticky demo state, OR
      - user uploads
    """
    ensure_demo_state(data_dir)

    has_uploads = (f_orders is not None) and (f_shipments is not None)

    if not (demo_mode_active or has_uploads):
        st.info("Upload Orders + Shipments, or turn on **Demo Mode (Sticky)** in the sidebar to begin.")
        st.stop()

    if demo_mode_active:
        raw_orders = st.session_state.get(DEMO_KEYS["orders"], pd.DataFrame())
        raw_shipments = st.session_state.get(DEMO_KEYS["shipments"], pd.DataFrame())
        raw_tracking = st.session_state.get(DEMO_KEYS["tracking"], pd.DataFrame())

        report = validate_demo_inputs(raw_orders, raw_shipments, raw_tracking)
        if report.level == "error":
            st.error("Demo data is not valid enough to run the pipeline.")
            for m in report.messages:
                st.write("- ", m)
            st.stop()

        st.caption("Using sticky demo data ✅")
        return raw_orders, raw_shipments, raw_tracking

    try:
        raw_orders = pd.read_csv(f_orders)
        raw_shipments = pd.read_csv(f_shipments)
        raw_tracking = pd.read_csv(f_tracking) if f_tracking else pd.DataFrame()
        return raw_orders, raw_shipments, raw_tracking
    except Exception as e:
        st.error("Failed to read one of your CSV uploads.")
        st.code(str(e))
        st.stop()
