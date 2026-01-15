# core/issue_tracker.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# ----------------------------
# Time helpers
# ----------------------------
def _utc_now_iso() -> str:
    # Keep your original "Z" style but make it timezone-safe
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Handle your stored "Z" suffix
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2)
    except Exception:
        return None


# ----------------------------
# Contact tracking schema
# ----------------------------
CONTACT_STATUSES = [
    "Not Contacted",
    "Contacted",
    "Waiting",
    "Escalated",
    "Resolved",
]


def _ensure_contact(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migration-safe: ensures 'contact' exists and has defaults.
    Does NOT remove anything existing.
    """
    contact = rec.get("contact") or {}
    if not isinstance(contact, dict):
        contact = {}

    contact.setdefault("status", "Not Contacted")
    contact.setdefault("last_contacted_at", "")
    contact.setdefault("channel", "")
    contact.setdefault("follow_up_count", 0)

    hist = contact.get("history")
    if not isinstance(hist, list):
        hist = []
    contact["history"] = hist

    # Normalize unknown status to default
    if contact.get("status") not in CONTACT_STATUSES:
        contact["status"] = "Not Contacted"

    rec["contact"] = contact
    return rec


@dataclass
class IssueRecord:
    resolved: bool = False
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str = ""
    # NOTE: dataclass not actively used for storage; kept for backward compat / clarity.


class IssueTrackerStore:
    """
    JSON-backed issue tracker.

    Compatibility (existing):
      - load() -> dict
      - prune_resolved_older_than_days(days) -> int
      - clear_resolved() -> int
      - upsert(issue_id, resolved=?, notes=?)
      - set_resolved(issue_id, bool)
      - set_notes(issue_id, str)

    Adds (new build phase):
      - mark_contacted(issue_id, channel="email", note="")
      - increment_followup(issue_id, channel="email", note="")
      - set_contact_status(issue_id, status)
      - get_contact_summary() -> dict(status -> count)

    Data shape per issue_id:
      {
        "resolved": bool,
        "notes": str,
        "created_at": str,
        "updated_at": str,
        "resolved_at": str,
        "contact": {
          "status": str,
          "last_contacted_at": str,
          "channel": str,
          "follow_up_count": int,
          "history": [ { "timestamp": str, "channel": str, "note": str, "status": str } ]
        }
      }
    """

    def __init__(self, path: Optional[str | Path] = None):
        base = Path(__file__).resolve().parent.parent
        data_dir = base / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = Path(path) if path else (data_dir / "issue_tracker.json")

        # Lightweight migration: ensure contact object exists for stored records
        data = self.load()
        changed = False
        for k, rec in list(data.items()):
            if isinstance(rec, dict):
                before = json.dumps(rec.get("contact", None), sort_keys=True, default=str)
                _ensure_contact(rec)
                after = json.dumps(rec.get("contact", None), sort_keys=True, default=str)
                if before != after:
                    data[k] = rec
                    changed = True
        if changed:
            self.save(data)

    # ----------------------------
    # Persistence
    # ----------------------------
    def load(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            # Ensure all records have contact defaults
            for k, rec in list(data.items()):
                if isinstance(rec, dict):
                    _ensure_contact(rec)
            return data
        except Exception:
            return {}

    def save(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ----------------------------
    # Core mutations (existing)
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
                # If resolved, also mark contact as Resolved (nice UX, safe default)
                _ensure_contact(rec)
                rec["contact"]["status"] = "Resolved"
            else:
                rec["resolved_at"] = ""

        if notes is not None:
            rec["notes"] = str(notes)

        rec["updated_at"] = now

        _ensure_contact(rec)
        data[issue_id] = rec
        self.save(data)

    def set_resolved(self, issue_id: str, resolved: bool) -> None:
        self.upsert(issue_id=issue_id, resolved=resolved)

    def set_notes(self, issue_id: str, notes: str) -> None:
        self.upsert(issue_id=issue_id, notes=notes)

    # ----------------------------
    # New: Contact / Follow-up tracking
    # ----------------------------
    def mark_contacted(
        self,
        issue_id: str,
        channel: str = "email",
        note: str = "",
        new_status: str = "Contacted",
    ) -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return

        if new_status not in CONTACT_STATUSES:
            new_status = "Contacted"

        data = self.load()
        rec = data.get(issue_id, {}) if isinstance(data.get(issue_id, {}), dict) else {}

        now = _utc_now_iso()
        if not rec.get("created_at"):
            rec["created_at"] = now
        rec["updated_at"] = now

        _ensure_contact(rec)
        rec["contact"]["status"] = new_status
        rec["contact"]["last_contacted_at"] = now
        rec["contact"]["channel"] = str(channel or "").strip()

        # Treat first outreach as follow-up count increment
        rec["contact"]["follow_up_count"] = int(rec["contact"].get("follow_up_count") or 0) + 1

        rec["contact"]["history"].append(
            {
                "timestamp": now,
                "channel": rec["contact"]["channel"],
                "note": str(note or ""),
                "status": new_status,
            }
        )

        data[issue_id] = rec
        self.save(data)

    def increment_followup(self, issue_id: str, channel: str = "email", note: str = "") -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return

        data = self.load()
        rec = data.get(issue_id, {}) if isinstance(data.get(issue_id, {}), dict) else {}

        now = _utc_now_iso()
        if not rec.get("created_at"):
            rec["created_at"] = now
        rec["updated_at"] = now

        _ensure_contact(rec)
        rec["contact"]["follow_up_count"] = int(rec["contact"].get("follow_up_count") or 0) + 1
        rec["contact"]["last_contacted_at"] = now
        rec["contact"]["channel"] = str(channel or "").strip()

        # If following up and not resolved, default to Waiting (unless Escalated already)
        if rec["contact"]["status"] not in ("Resolved", "Escalated"):
            rec["contact"]["status"] = "Waiting"

        rec["contact"]["history"].append(
            {
                "timestamp": now,
                "channel": rec["contact"]["channel"],
                "note": str(note or ""),
                "status": rec["contact"]["status"],
            }
        )

        data[issue_id] = rec
        self.save(data)

    def set_contact_status(self, issue_id: str, status: str) -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return
        if status not in CONTACT_STATUSES:
            return

        data = self.load()
        rec = data.get(issue_id, {}) if isinstance(data.get(issue_id, {}), dict) else {}
        now = _utc_now_iso()

        if not rec.get("created_at"):
            rec["created_at"] = now
        rec["updated_at"] = now

        _ensure_contact(rec)
        rec["contact"]["status"] = status

        # Keep resolved in sync if they set Resolved here
        if status == "Resolved":
            rec["resolved"] = True
            if not rec.get("resolved_at"):
                rec["resolved_at"] = now

        data[issue_id] = rec
        self.save(data)

    def get_contact_summary(self) -> Dict[str, int]:
        data = self.load()
        counts = {s: 0 for s in CONTACT_STATUSES}
        for _, rec in data.items():
            if not isinstance(rec, dict):
                continue
            _ensure_contact(rec)
            s = rec["contact"].get("status") or "Not Contacted"
            if s not in counts:
                s = "Not Contacted"
            counts[s] += 1
        return counts

    # ----------------------------
    # Maintenance (existing)
    # ----------------------------
    def prune_resolved_older_than_days(self, days: int) -> int:
        days = int(days)
        if days <= 0:
            return 0

        data = self.load()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

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
