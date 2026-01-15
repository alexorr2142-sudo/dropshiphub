# core/issue_tracker.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        s2 = s.replace("Z", "")
        return datetime.fromisoformat(s2)
    except Exception:
        return None


@dataclass
class IssueRecord:
    resolved: bool = False
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str = ""


class IssueTrackerStore:
    """
    JSON-backed issue tracker.

    Compatibility:
      - load() -> dict
      - prune_resolved_older_than_days(days) -> int
      - clear_resolved() -> int

    Adds:
      - upsert(issue_id, resolved=?, notes=?)
      - set_resolved(issue_id, bool)
      - set_notes(issue_id, str)
    """

    def __init__(self, path: Optional[str | Path] = None):
        base = Path(__file__).resolve().parent.parent
        data_dir = base / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = Path(path) if path else (data_dir / "issue_tracker.json")

    # ----------------------------
    # Persistence
    # ----------------------------
    def load(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ----------------------------
    # Mutations
    # ----------------------------
    def upsert(self, issue_id: str, resolved: Optional[bool] = None, notes: Optional[str] = None) -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return

        data = self.load()
        rec = data.get(issue_id, {}) if isinstance(data.get(issue_id, {}), dict) else {}

        now = _utc_now_iso()
        if not rec.get("created_at"):
            rec["created_at"] = now

        if resolved is not None:
            rec["resolved"] = bool(resolved)
            if bool(resolved):
                if not rec.get("resolved_at"):
                    rec["resolved_at"] = now
            else:
                rec["resolved_at"] = ""

        if notes is not None:
            rec["notes"] = str(notes)

        rec["updated_at"] = now
        data[issue_id] = rec
        self.save(data)

    def set_resolved(self, issue_id: str, resolved: bool) -> None:
        self.upsert(issue_id=issue_id, resolved=resolved)

    def set_notes(self, issue_id: str, notes: str) -> None:
        self.upsert(issue_id=issue_id, notes=notes)

    # ----------------------------
    # Maintenance
    # ----------------------------
    def prune_resolved_older_than_days(self, days: int) -> int:
        days = int(days)
        if days <= 0:
            return 0

        data = self.load()
        cutoff = datetime.utcnow() - timedelta(days=days)

        removed = 0
        keep: Dict[str, Dict[str, Any]] = {}
        for k, rec in data.items():
            if not isinstance(rec, dict):
                continue

            resolved = bool(rec.get("resolved", False))
            if not resolved:
                keep[k] = rec
                continue

            resolved_at = _parse_iso(str(rec.get("resolved_at", ""))) or _parse_iso(str(rec.get("updated_at", "")))
            if resolved_at and resolved_at < cutoff:
                removed += 1
            else:
                keep[k] = rec

        if removed:
            self.save(keep)
        return removed

    def clear_resolved(self) -> int:
        data = self.load()
        removed = 0
        keep: Dict[str, Dict[str, Any]] = {}
        for k, rec in data.items():
            if not isinstance(rec, dict):
                continue
            if bool(rec.get("resolved", False)):
                removed += 1
            else:
                keep[k] = rec
        if removed:
            self.save(keep)
        return removed
