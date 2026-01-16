# ui/demo.py
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd
import streamlit as st


# Keep this key consistent with your app.py to avoid collisions
DEMO_TOGGLE_KEY = "sidebar_demo_mode"

# Session keys for demo tables
DEMO_KEYS = {
    "orders": "demo_raw_orders",
    "shipments": "demo_raw_shipments",
    "tracking": "demo_raw_tracking",
}


def demo_mode_on() -> bool:
    return bool(st.session_state.get(DEMO_TOGGLE_KEY, False))


def _load_demo_files(data_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(data_dir / "raw_orders.csv"),
        pd.read_csv(data_dir / "raw_shipments.csv"),
        pd.read_csv(data_dir / "raw_tracking.csv"),
    )


def init_demo_tables_if_needed(data_dir: Path) -> None:
    """
    If demo mode is ON, ensure demo tables exist in session state.
    If demo mode is OFF, remove demo tables from session state.
    """
    if demo_mode_on():
        if DEMO_KEYS["orders"] not in st.session_state:
            o, s, t = _load_demo_files(data_dir)
            st.session_state[DEMO_KEYS["orders"]] = o
            st.session_state[DEMO_KEYS["shipments"]] = s
            st.session_state[DEMO_KEYS["tracking"]] = t
    else:
        for k in DEMO_KEYS.values():
            st.session_state.pop(k, None)


def reset_demo_tables(data_dir: Path) -> None:
    o, s, t = _load_demo_files(data_dir)
    st.session_state[DEMO_KEYS["orders"]] = o
    st.session_state[DEMO_KEYS["shipments"]] = s
    st.session_state[DEMO_KEYS["tracking"]] = t


def clear_demo_callback(data_dir: Path) -> None:
    """
    Callback-safe clear:
      - turns demo toggle OFF
      - clears demo tables
      - re-initializes state accordingly
    """
    st.session_state[DEMO_TOGGLE_KEY] = False
    init_demo_tables_if_needed(data_dir)


def render_demo_sidebar_controls(data_dir: Path, key_prefix: str = "demo") -> None:
    """
    Renders:
      - sticky demo toggle
      - reset demo
      - clear demo (callback-safe)
    Also calls init_demo_tables_if_needed() so demo data is ready when enabled.
    """
    st.header("Demo Mode (Sticky)")
    st.toggle(
        "Use demo data (sticky)",
        key=DEMO_TOGGLE_KEY,
        help="Keeps demo data and your edits across interactions until you reset or turn off demo mode.",
    )

    init_demo_tables_if_needed(data_dir)

    if demo_mode_on():
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Reset demo", use_container_width=True, key=f"{key_prefix}_btn_reset"):
                reset_demo_tables(data_dir)
                st.success("Demo reset ✅")
                st.rerun()
        with c2:
            st.button(
                "Clear demo",
                use_container_width=True,
                key=f"{key_prefix}_btn_clear",
                on_click=clear_demo_callback,
                args=(data_dir,),
            )


def render_demo_editor(key_prefix: str = "demo") -> None:
    """
    Main-page demo editors (3 tables).
    """
    if not demo_mode_on():
        st.info("Turn on **Demo Mode (Sticky)** in the sidebar to play with demo data (edits persist).")
        return

    st.success("Demo mode is ON (sticky). Your demo edits persist until you reset/clear.")

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


def get_active_raw_inputs(
    data_dir: Path,
    f_orders,
    f_shipments,
    f_tracking,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Centralized logic to choose between:
      - sticky demo state, OR
      - user uploads

    Matches your current behavior in app.py:
      - requires Orders + Shipments unless demo mode is on
      - Tracking is optional
    """
    has_uploads = (f_orders is not None) and (f_shipments is not None)

    if not (demo_mode_on() or has_uploads):
        st.info("Upload Orders + Shipments, or turn on **Demo Mode (Sticky)** in the sidebar to begin.")
        st.stop()

    if demo_mode_on():
        raw_orders = st.session_state.get(DEMO_KEYS["orders"], pd.DataFrame())
        raw_shipments = st.session_state.get(DEMO_KEYS["shipments"], pd.DataFrame())
        raw_tracking = st.session_state.get(DEMO_KEYS["tracking"], pd.DataFrame())

        if raw_orders is None or raw_orders.empty:
            st.error("Demo orders are empty. Click **Reset demo** in the sidebar.")
            st.stop()
        if raw_shipments is None or raw_shipments.empty:
            st.error("Demo shipments are empty. Click **Reset demo** in the sidebar.")
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
