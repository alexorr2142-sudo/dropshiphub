from __future__ import annotations

"""Issue tracker constants + tiny helpers.

This file exists to keep the issue tracker implementation split across
multiple <300-line modules.
"""

from pathlib import Path


CONTACT_STATUSES: list[str] = [
    "Not Contacted",
    "Contacted",
    "Waiting",
    "Escalated",
    "Resolved",
]


ISSUE_STATUSES: list[str] = [
    "Open",
    "Waiting",
    "Resolved",
]


def issue_tracker_path_for_ws_root(ws_root: Path) -> Path:
    """Workspace-relative path used across the app."""
    return Path(ws_root) / "issue_tracker.json"
