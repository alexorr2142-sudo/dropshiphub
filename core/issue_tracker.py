# core/issue_tracker.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Tuple

import pandas as pd

DEFAULT_STORE_PATH = Path("data/issue_tracker.json")


@dataclass
class IssueTrackerStore:
    path: Path = DEFAULT_STORE_PATH

    def _ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save(self, data: Dict[str, Dict[str, Any]]) -> None:
        self._ensure_parent()
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    # ============================================================
    # Maintenance helpers (NEW)
    # ============================================================
    def clear_resolved(self) -> Tuple[int, int]:
        """
        Remove ALL entries where resolved == True.
        Returns: (removed_count, remaining_count)
        """
        data = self.load()
        before = len(data)
        kept = {k: v for k, v in data.items() if not bool((v or {}).get("resolved", False))}
        removed = before - len(kept)
        self.save(kept)
        return removed, len(kept)

    def prune_resolved(self, older_than_days: int = 30) -> Tuple[int, int]:
        """
        Remove entries that are resolved and whose updated_at is older than N days.
        If updated_at is missing or invalid, we keep the record (safer).
        Returns: (removed_count, remaining_count)
        """
        days = int(older_than_days)
        data = self.load()
        before = len(data)

        cutoff = pd.Timestamp.utcnow().tz_localize("UTC") - pd.Timedelta(days=days)

        kept: Dict[str, Dict[str, Any]] = {}
        removed = 0

        for k, v in data.items():
            v = v or {}
            is_resolved = bool(v.get("resolved", False))

            if not is_resolved:
                kept[k] = v
                continue

            # resolved == True: check updated_at
            updated_at = v.get("updated_at", "")
            try:
                ts = pd.to_datetime(updated_at, errors="coerce", utc=True)
            except Exception:
                ts = pd.NaT

            # If timestamp is missing/invalid -> keep (don’t accidentally wipe)
            if pd.isna(ts):
                kept[k] = v
                continue

            if ts < cutoff:
                removed += 1
            else:
                kept[k] = v

        if removed != (before - len(kept)):
            # sanity (should always match, but keep safe)
            removed = before - len(kept)

        self.save(kept)
        return removed, len(kept)


def make_issue_id(row: pd.Series) -> str:
    """
    Create a stable-ish ID for an exception/followup row.
    Uses common column candidates; falls back to row dict.
    """
    candidates = [
        "line_id",
        "LineID",
        "order_line_id",
        "OrderLineID",
        "shipment_line_id",
        "ShipmentLineID",
    ]
    line_part = next((str(row[c]) for c in candidates if c in row and pd.notna(row[c])), "")

    order_candidates = [
        "order_id",
        "OrderID",
        "po_number",
        "PONumber",
        "customer_po",
        "CustomerPO",
    ]
    order_part = next((str(row[c]) for c in order_candidates if c in row and pd.notna(row[c])), "")

    exc_candidates = [
        "exception_type",
        "ExceptionType",
        "issue_type",
        "IssueType",
        "reason",
        "Reason",
        "status_reason",
    ]
    exc_part = next((str(row[c]) for c in exc_candidates if c in row and pd.notna(row[c])), "")

    supplier_candidates = ["supplier_name", "Supplier", "vendor", "Vendor"]
    supplier_part = next((str(row[c]) for c in supplier_candidates if c in row and pd.notna(row[c])), "")

    base = "|".join([order_part, line_part, supplier_part, exc_part]).strip("|")
    if not base:
        base = str(row.to_dict())

    return f"EXC::{base}"
