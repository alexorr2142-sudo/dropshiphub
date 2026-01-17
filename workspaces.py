"""Workspace helpers (thin facade).

Constraint: keep files small (<300 lines).
"""

from __future__ import annotations

from core.workspaces_utils import safe_slug, workspace_root
from core.workspaces_io import (
    convert_raw_snapshot_to_full_run,
    list_runs,
    load_run,
    save_raw_inputs_snapshot,
    save_run,
)
from core.workspaces_artifacts import build_run_history_df, delete_run_dir, make_run_zip_bytes

__all__ = [
    "safe_slug",
    "workspace_root",
    "list_runs",
    "save_run",
    "save_raw_inputs_snapshot",
    "convert_raw_snapshot_to_full_run",
    "load_run",
    "make_run_zip_bytes",
    "delete_run_dir",
    "build_run_history_df",
]
