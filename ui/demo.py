# ui/demo.py
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd
import streamlit as st

# Session keys for demo tables (must match app.py fallback usage)
DEMO_KEYS = {
    "orders": "demo_raw_orders",
    "shipments": "demo_raw_shipments",
    "tracking": "demo_raw_tracking",
}

# Filenames expected in /data
DEMO_FILES = {
    "orders": "raw_orders.csv",
    "shipments": "raw_shipments.csv",
    "tracking": "raw_tracking.csv",
}


def _demo_mode_active() -> bool:
    """
    Demo Mode is controlled by the sidebar in ui/sidebar.py.

    That sidebar attempts to set:
      - st.session_state["demo_mode"] (canonical)
      - OR falls back to st.session_state["app_demo_mode"] if Streamlit blocks 'demo_mode'

    We also tolerate reading sb_demo_mode directly just in case.
    """
    return bool(
        st.session_state.get(
            "demo_mode",
            st.session_state.get(
                "app_demo_mode",
                st.session_state.get("sb_demo_mode", False),
            ),
        )
    )


def _load_demo_files(data_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    orders_path = data_dir / DEMO_FILES["orders"]
    shipments_path = data_dir / DEMO_FILES["shipments"]
    tracking_path = data_dir / DEMO_FILES["tracking"]

    missing = [p.name for p in [orders_path, shipments_path, tracking_path] if not p.exists()]
    if missing:
        # Keep behavior explicit: if demo files are missing, don't pretend we have data.
        raise FileNotFoundError(
            "Missing demo CSV file(s): " + ", ".join(missing) + f" in {data_dir.as_posix()}"
        )

    o = pd.read_csv(orders_path)
    s = pd.read_csv(shipments_path)
    t = pd.read_csv(tracking_path) if tracking_path.exists() else pd.DataFrame()
    return o, s, t


def _init_demo_tables_if_needed(data_dir: Path) -> None:
    """
    If demo mode is ON:
      - ensure demo tables exist in session state (load once)
    If demo mode is OFF:
      - remove demo tables from session state
    """
    if _demo_mode_active():
        if (DEMO_KEYS["orders"] not in st.session_state) or (DEMO_KEYS["shipments"] not in st.session_state):
            try:
                o, s, t = _load_demo_files(data_dir)
            except Exception as e:
                st.error("Demo Mode is ON, but demo CSV files could not be loaded.")
                st.code(str(e))
                st.stop()

            st.session_state[DEMO_KEYS["orders"]] = o
            st.session_state[DEMO_KEYS["shipments"]] = s
            st.session_state[DEMO_KEYS["tracking"]] = t
    else:
        for k in DEMO_KEYS.values():
            st.session_state.pop(k, None)


def ensure_demo_state(data_dir: Path) -> None:
    """
    Called by app.py at the top of the page.
    Keeps demo tables aligned with current demo_mode state.
    """
    _init_demo_tables_if_needed(data_dir)


def _reset_demo_tables(data_dir: Path) -> None:
    try:
        o, s, t = _load_demo_files(data_dir)
    except Exception as e:
        st.error("Could not reset demo tables because demo CSV files could not be loaded.")
        st.code(str(e))
        st.stop()

    st.session_state[DEMO_KEYS["orders"]] = o
    st.session_state[DEMO_KEYS["shipments"]] = s
    st.session_state[DEMO_KEYS["tracking"]] = t


def render_demo_editor(key_prefix: str = "demo") -> None:
    """
    Main-page demo editors (3 tables). Edits persist in session_state while demo mode is on.
    """
    if not _demo_mode_active():
        st.info("Turn on **Demo Mode (Sticky)** in the sidebar to play with demo data (edits persist).")
        return

    # Make sure tables exist before rendering editors
    # (uses the same data_dir your app already passed into ensure_demo_state earlier)
    # If ensure_demo_state wasn't called for some reason, this still protects us.
    # We try to infer data_dir from app convention: ./data
    try:
        # Best effort: if data was not initialized, try loading from the default ./data path.
        # Your app always uses DATA_DIR = BASE_DIR / "data", so this is consistent.
        # If it's already in session_state, nothing happens.
        default_data_dir = Path(__file__).resolve().parent.parent / "data"
        _init_demo_tables_if_needed(default_data_dir)
    except Exception:
        pass

    st.success("Demo mode is ON (sticky). Your demo edits persist until you turn demo mode off or reset files.")

    c0, c1 = st.columns([1, 3])
    with c0:
        if st.button("Reset demo from CSV files", use_container_width=True, key=f"{key_prefix}_btn_reset"):
            # Use app's data dir convention
            data_dir = Path(__file__).resolve().parent.parent / "data"
            _reset_demo_tables(data_dir)
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

    Orders + Shipments are required unless demo mode is on.
    Tracking is optional.
    """
    # Always keep demo tables synced with the passed demo_mode_active flag
    # (source of truth is still session_state, but this protects from drift)
    if demo_mode_active != _demo_mode_active():
        # Don't try to overwrite the sidebar state; just re-init based on actual session state.
        pass

    _init_demo_tables_if_needed(data_dir)

    has_uploads = (f_orders is not None) and (f_shipments is not None)

    if not (demo_mode_active or has_uploads):
        st.info("Upload Orders + Shipments, or turn on **Demo Mode (Sticky)** in the sidebar to begin.")
        st.stop()

    if demo_mode_active:
        raw_orders = st.session_state.get(DEMO_KEYS["orders"], pd.DataFrame())
        raw_shipments = st.session_state.get(DEMO_KEYS["shipments"], pd.DataFrame())
        raw_tracking = st.session_state.get(DEMO_KEYS["tracking"], pd.DataFrame())

        if raw_orders is None or not isinstance(raw_orders, pd.DataFrame) or raw_orders.empty:
            st.error("Demo orders are empty. Ensure raw_orders.csv exists in /data and click reset if needed.")
            st.stop()
        if raw_shipments is None or not isinstance(raw_shipments, pd.DataFrame) or raw_shipments.empty:
            st.error("Demo shipments are empty. Ensure raw_shipments.csv exists in /data and click reset if needed.")
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
