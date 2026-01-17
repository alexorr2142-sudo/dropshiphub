"""Backwards-compatible issue tracker module.

The issue tracker grew large; to keep the repo maintainable we split the
implementation into multiple <300-line modules.

Other modules should continue to import from `core.issue_tracker`.
"""

from __future__ import annotations

from core.issue_tracker_schema import (
    CONTACT_STATUSES,
    ISSUE_STATUSES,
    issue_tracker_path_for_ws_root,
)
from core.issue_tracker_store import IssueTrackerStore, IssueRecord
from core.issue_tracker_time import utc_now_iso as _utc_now_iso, parse_iso as _parse_iso

__all__ = [
    "CONTACT_STATUSES",
    "ISSUE_STATUSES",
    "issue_tracker_path_for_ws_root",
    "IssueTrackerStore",
    "IssueRecord",
    "_utc_now_iso",
    "_parse_iso",
]
