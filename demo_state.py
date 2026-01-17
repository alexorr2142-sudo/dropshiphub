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


