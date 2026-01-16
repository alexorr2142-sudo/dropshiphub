# ui/demo.py
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd
import streamlit as st

from core.demo_schema import validate_demo_inputs
from ui.demo_fork_ui import render_demo_fork_controls

DEMO_KEYS = {
    "orders": "demo_raw_orders",
    "shipments": "demo_raw_shipments",
    "tracking": "demo_raw_tracking",
}

DEMO_FILES = {
    "orders": "raw_orders.csv",
    "shipments": "raw_shipments.csv",
    "tracking": "raw_tracking.csv",
}


def _demo_mode_active() -> bool:
    # Canonical demo mode written by ui/sidebar.py
    return bool(
        st.session_state.get(
            "demo_mode",
            st.session_state.get("app_demo_mode", st.session_state.get("sb_demo_mode", False)),
        )
    )


def _infer_data_dir() -> Path:
    # Same convention as app.py: BASE_DIR / "data"
    return Path(__file__).resolve().parent.parent / "data"


def _load_demo_files(data_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    orders_path = data_dir / DEMO_FILES["orders"]
    shipments_path = data_dir / DEMO_FILES["shipments"]
    tracking_path = data_dir / DEMO_FILES["tracking"]

    missing = [p.name for p in [orders_path, shipments_path] if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required demo CSV file(s): " + ", ".join(missing) + f" in {data_dir.as_posix()}"
        )

    o = pd.read_csv(orders_path)
    s = pd.read_csv(shipments_path)
    t = pd.read_csv(tracking_path) if tracking_path.exists() else pd.DataFrame()
    return o, s, t


def _load_snapshot_raw_csvs(snapshot_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Loads RAW snapshot CSVs from a workspace snapshot directory.
    Fail-safe: raises on missing required files.
    """
    orders_path = snapshot_dir / DEMO_FILES["orders"]
    shipments_path = snapshot_dir / DEMO_FILES["shipments"]
    tracking_path = snapshot_dir / DEMO_FILES["tracking"]

    missing = [p.name for p in [orders_path, shipments_path] if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Snapshot missing required file(s): " + ", ".join(missing) + f" in {snapshot_dir.as_posix()}"
        )

    o = pd.read_csv(orders_path)
    s = pd.read_csv(shipments_path)
    t = pd.read_csv(tracking_path) if tracking_path.exists() else pd.DataFrame()
    return o, s, t


def _consume_snapshot_load_request() -> None:
    """
    Optional hook: Workspaces UI can queue a request to load a RAW snapshot into Demo Mode.

    This function:
      - checks session_state for a queued request
      - attempts to load snapshot CSVs into demo tables
      - validates schema enough to run
      - clears the request (one-shot)
      - fails safe (warning only)
    """
    # Default key_prefix in ui/workspaces_ui.py is "ws"
    req_key = "ws_req_load_snapshot_into_demo"
    payload = st.session_state.get(req_key)
    if not payload:
        return

    # Always clear request to avoid loops / repeated attempts
    st.session_state[req_key] = None

    try:
        snap_dir = Path(str(payload.get("snapshot_dir", "") or ""))
        if not snap_dir.exists() or not snap_dir.is_dir():
            st.warning("Snapshot load request ignored: snapshot folder not found.")
            return

        o, s, t = _load_snapshot_raw_csvs(snap_dir)

        # Validate enough to run pipeline (same gate as demo)
        report = validate_demo_inputs(o, s, t)
        if report.level == "error":
            st.warning("Snapshot loaded but is not valid enough to run the pipeline (schema errors).")
            with st.expander("Snapshot schema details", expanded=False):
                for m in report.messages:
                    st.write("- ", m)
            return

        # IMPORTANT: we do NOT flip demo_mode here (sidebar is canonical).
        # We just stage the demo tables so that when demo mode is ON, it uses them.
        st.session_state[DEMO_KEYS["orders"]] = o
        st.session_state[DEMO_KEYS["shipments"]] = s
        st.session_state[DEMO_KEYS["tracking"]] = t

        st.session_state["demo_schema_report"] = {
            "ok": report.ok,
            "level": report.level,
            "messages": report.messages,
        }

        # Friendly confirmation (non-fatal)
        src_ws = payload.get("source_workspace", "")
        src_run = payload.get("source_run_id", "")
        if src_ws or src_run:
            st.success(f"Loaded snapshot into Demo tables ✅ ({src_ws} / {src_run})")
        else:
            st.success("Loaded snapshot into Demo tables ✅")

        # If user already has demo mode ON, ensure UI refresh uses new tables
        if _demo_mode_active():
            st.rerun()

    except Exception as e:
        st.warning("Could not load snapshot into Demo Mode (safe ignore).")
        st.code(str(e))


def ensure_demo_state(data_dir: Path) -> None:
    """
    Called by app.py. Keeps demo tables aligned with current demo_mode state.
    """
    # Allow queued workspace snapshot loads to populate demo tables safely
    try:
        _consume_snapshot_load_request()
    except Exception:
        # Never let optional hook break the app
        pass

    if _demo_mode_active():
        if (DEMO_KEYS["orders"] not in st.session_state) or (DEMO_KEYS["shipments"] not in st.session_state):
            o, s, t = _load_demo_files(data_dir)
            st.session_state[DEMO_KEYS["orders"]] = o
            st.session_state[DEMO_KEYS["shipments"]] = s
            st.session_state[DEMO_KEYS["tracking"]] = t

        # Validate and store report for debug/health displays
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
    else:
        for k in DEMO_KEYS.values():
            st.session_state.pop(k, None)
        st.session_state.pop("demo_schema_report", None)


def _reset_demo_tables(data_dir: Path) -> None:
    o, s, t = _load_demo_files(data_dir)
    st.session_state[DEMO_KEYS["orders"]] = o
    st.session_state[DEMO_KEYS["shipments"]] = s
    st.session_state[DEMO_KEYS["tracking"]] = t


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
