# core/issue_tracker.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

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
