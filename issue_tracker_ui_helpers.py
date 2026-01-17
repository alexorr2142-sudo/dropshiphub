# ui/issue_tracker_ui.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import streamlit as st

from core.issue_tracker import IssueTrackerStore

# Local constants (UI-level, safe)
ISSUE_STATUSES = ["Open", "Waiting", "Resolved"]


def _get_store(issue_tracker_path: Optional[Path] = None) -> IssueTrackerStore:
    """
    Ensures we always use the per-tenant store file when provided.
    Falls back to IssueTrackerStore() default behavior if no path is given.
    """
    try:
        return IssueTrackerStore(issue_tracker_path) if issue_tracker_path else IssueTrackerStore()
    except TypeError:
        # Backward compatibility if IssueTrackerStore() signature differs
        return IssueTrackerStore()


def _row_context(r: pd.Series) -> Dict[str, Any]:
    """
    Best-effort context extraction for timeline + filtering.
    Only includes keys that exist / are non-empty.
    """
    ctx: Dict[str, Any] = {}

    def _pick(col: str) -> str:
        try:
            return str(r.get(col, "") or "").strip()
        except Exception:
            return ""

    supplier_name = _pick("supplier_name")
    supplier_email = _pick("supplier_email")
    order_id = _pick("order_id")
    order_ids = _pick("order_ids")

    if supplier_name:
        ctx["supplier_name"] = supplier_name
    if supplier_email:
        ctx["supplier_email"] = supplier_email
    if order_id:
        ctx["order_id"] = order_id
    if order_ids:
        ctx["order_ids"] = order_ids

    return ctx

