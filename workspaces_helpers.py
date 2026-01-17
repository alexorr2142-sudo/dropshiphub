# ui/workspaces_ui.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from core.workspaces import (
    workspace_root,
    list_runs,
    save_run,
    load_run,
    make_run_zip_bytes,
    delete_run_dir,
    build_run_history_df,
)

# Optional import: conversion is additive and must never break the app
try:
    from core.workspaces import convert_raw_snapshot_to_full_run
except Exception:  # pragma: no cover
    convert_raw_snapshot_to_full_run = None  # type: ignore


@dataclass
class WorkspacesResult:
    ws_root: Path
    workspace_name: str
    loaded_run_dir: Optional[Path]
    # Back-compat outputs (optional)
    exceptions: Optional[pd.DataFrame] = None
    followups_full: Optional[pd.DataFrame] = None
    order_rollup: Optional[pd.DataFrame] = None
    line_status_df: Optional[pd.DataFrame] = None
    suppliers_df: Optional[pd.DataFrame] = None


def _is_raw_snapshot_run(run: dict) -> bool:
    """
    Best-effort detection for demo RAW snapshot runs.

    We treat a run as "RAW snapshot" if:
      - run_id contains "_raw", OR
      - the run folder name contains "_raw"
    """
    try:
        rid = str(run.get("run_id", "") or "")
        if "_raw" in rid:
            return True
        p = run.get("path")
        if p:
            return "_raw" in Path(p).name
    except Exception:
        return False
    return False


def _consume_convert_snapshot_request(
    *,
    req_key: str,
    ws_root: Path,
    account_id: str,
    store_id: str,
    platform_hint: Optional[str],
    loaded_key: str,
) -> tuple[Optional[Path], Optional[str]]:
    """
    Consumes a queued conversion request and performs conversion if supported.

    Returns (new_run_dir, message). message is informational; errors are returned as message too.
    """
    payload = st.session_state.get(req_key)
    if not payload:
        return None, None

    # one-shot: clear immediately so we never loop
    st.session_state[req_key] = None

    if convert_raw_snapshot_to_full_run is None:
        return None, "Conversion not available (missing converter)."

    try:
        snapshot_dir = Path(str(payload.get("snapshot_dir", "") or ""))
        target_ws = str(payload.get("target_workspace", "default") or "default")
        src_ws = str(payload.get("source_workspace", "") or "")
        src_run = str(payload.get("source_run_id", "") or "")
        note = f"Converted from RAW snapshot {src_ws}/{src_run}".strip()

        new_dir, err = convert_raw_snapshot_to_full_run(
            ws_root=ws_root,
            snapshot_dir=snapshot_dir,
            target_workspace_name=target_ws,
            account_id=account_id,
            store_id=store_id,
            platform_hint=platform_hint or "",
            note=note,
        )

        if err:
            return None, f"Conversion failed: {err}"

        if new_dir:
            st.session_state[loaded_key] = str(new_dir)
            label = f"{target_ws}/{new_dir.name}"
            return new_dir, f"Converted ✅ Saved as {label}"

        return None, "Conversion failed: unknown error"

    except Exception as e:
        return None, f"Conversion failed: {e}"


