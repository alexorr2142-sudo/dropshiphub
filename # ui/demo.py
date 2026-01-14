# ui/demo.py
from pathlib import Path
import pandas as pd
import streamlit as st

def _init_demo_tables_if_needed(data_dir: Path):
    if "demo_mode" not in st.session_state:
        st.session_state["demo_mode"] = False

    if st.session_state.get("demo_mode", False):
        if "demo_raw_orders" not in st.session_state:
            st.session_state["demo_raw_orders"] = pd.read_csv(data_dir / "raw_orders.csv")
        if "demo_raw_shipments" not in st.session_state:
            st.session_state["demo_raw_shipments"] = pd.read_csv(data_dir / "raw_shipments.csv")
        if "demo_raw_tracking" not in st.session_state:
            st.session_state["demo_raw_tracking"] = pd.read_csv(data_dir / "raw_tracking.csv")
    else:
        for k in ["demo_raw_orders", "demo_raw_shipments", "demo_raw_tracking"]:
            st.session_state.pop(k, None)

def _reset_demo_tables(data_dir: Path):
    st.session_state["demo_raw_orders"] = pd.read_csv(data_dir / "raw_orders.csv")
    st.session_state["demo_raw_shipments"] = pd.read_csv(data_dir / "raw_shipments.csv")
    st.session_state["demo_raw_tracking"] = pd.read_csv(data_dir / "raw_tracking.csv")

def ensure_demo_state(data_dir: Path):
    _init_demo_tables_if_needed(data_dir)

def render_demo_editor():
    demo_mode = st.session_state.get("demo_mode", False)
    if demo_mode:
        st.success("Demo mode is ON (sticky). Your demo edits persist until you reset/clear.")
        with st.expander("Edit demo data (these edits persist)", expanded=True):
            e1, e2, e3 = st.columns(3)

            with e1:
                st.caption("raw_orders.csv (demo)")
                st.session_state["demo_raw_orders"] = st.data_editor(
                    st.session_state.get("demo_raw_orders", pd.DataFrame()),
                    use_container_width=True,
                    height=280,
                    num_rows="dynamic",
                    key="demo_orders_editor",
                )

            with e2:
                st.caption("raw_shipments.csv (demo)")
                st.session_state["demo_raw_shipments"] = st.data_editor(
                    st.session_state.get("demo_raw_shipments", pd.DataFrame()),
                    use_container_width=True,
                    height=280,
                    num_rows="dynamic",
                    key="demo_shipments_editor",
                )

            with e3:
                st.caption("raw_tracking.csv (demo)")
                st.session_state["demo_raw_tracking"] = st.data_editor(
                    st.session_state.get("demo_raw_tracking", pd.DataFrame()),
                    use_container_width=True,
                    height=280,
                    num_rows="dynamic",
                    key="demo_tracking_editor",
                )
    else:
        st.info("Turn on **Demo Mode (Sticky)** in the sidebar to play with demo data (edits persist).")

def get_active_raw_inputs(demo_mode: bool, data_dir: Path, f_orders, f_shipments, f_tracking):
    has_uploads = (f_orders is not None) and (f_shipments is not None)

    if not (demo_mode or has_uploads):
        st.info("Upload Orders + Shipments, or turn on **Demo Mode (Sticky)** in the sidebar to begin.")
        st.stop()

    if demo_mode:
        raw_orders = st.session_state.get("demo_raw_orders", pd.DataFrame())
        raw_shipments = st.session_state.get("demo_raw_shipments", pd.DataFrame())
        raw_tracking = st.session_state.get("demo_raw_tracking", pd.DataFrame())

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
