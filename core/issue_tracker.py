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
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
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

# ----------------------------
# Issue ownership / follow-through schema
# ----------------------------
ISSUE_STATUSES = [
    "Open",
    "Waiting",
    "Resolved",
]


def issue_tracker_path_for_ws_root(ws_root: Path) -> Path:
    return Path(ws_root) / "issue_tracker.json"


def _ensure_contact(rec: Dict[str, Any]) -> Dict[str, Any]:
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

    if contact.get("status") not in CONTACT_STATUSES:
        contact["status"] = "Not Contacted"

    rec["contact"] = contact
    return rec


def _derive_issue_status(rec: Dict[str, Any]) -> str:
    try:
        if bool(rec.get("resolved", False)):
            return "Resolved"
        contact = rec.get("contact") if isinstance(rec.get("contact"), dict) else {}
        cstat = (contact.get("status") or "").strip()
        if cstat in ("Waiting", "Escalated"):
            return "Waiting"
        if cstat == "Resolved":
            return "Resolved"
        return "Open"
    except Exception:
        return "Open"


def _ensure_issue_meta(rec: Dict[str, Any]) -> Dict[str, Any]:
    owner = rec.get("owner", "")
    if owner is None:
        owner = ""
    rec["owner"] = str(owner)

    status = rec.get("status", "")
    if not isinstance(status, str) or not status.strip():
        status = _derive_issue_status(rec)
    status = status.strip()
    if status not in ISSUE_STATUSES:
        status = _derive_issue_status(rec)
    rec["status"] = status

    naa = rec.get("next_action_at", "")
    if naa is None:
        naa = ""
    rec["next_action_at"] = str(naa)

    rec.setdefault("last_action_at", "")

    if rec.get("status") == "Resolved":
        rec["resolved"] = True
        if not rec.get("resolved_at"):
            rec["resolved_at"] = rec.get("updated_at", "") or _utc_now_iso()

    return rec


@dataclass
class IssueRecord:
    resolved: bool = False
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str = ""


class IssueTrackerStore:
    """
    JSON-backed issue tracker with migration-safe schema.

    Adds Timeline logging (Feature #1):
      - append-only events to <ws_root>/timeline.jsonl
      - logging is best-effort and NEVER breaks the app
    """

    def __init__(self, path: Optional[str | Path] = None):
        base = Path(__file__).resolve().parent.parent
        data_dir = base / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = Path(path) if path else (data_dir / "issue_tracker.json")

        # Lightweight migration: ensure contact + meta exist
        data = self.load()
        changed = False
        for k, rec in list(data.items()):
            if isinstance(rec, dict):
                before = json.dumps(
                    {
                        "contact": rec.get("contact", None),
                        "owner": rec.get("owner", None),
                        "status": rec.get("status", None),
                        "next_action_at": rec.get("next_action_at", None),
                    },
                    sort_keys=True,
                    default=str,
                )

                _ensure_contact(rec)
                _ensure_issue_meta(rec)

                after = json.dumps(
                    {
                        "contact": rec.get("contact", None),
                        "owner": rec.get("owner", None),
                        "status": rec.get("status", None),
                        "next_action_at": rec.get("next_action_at", None),
                    },
                    sort_keys=True,
                   default=str,
                )
                if before != after:
                    data[k] = rec
                    changed = True
        if changed:
            self.save(data)

    # ----------------------------
    # Timeline (best-effort)
    # ----------------------------
    def _timeline(self):
        """
        Returns TimelineStore or None. Never raises.
        Timeline is stored beside issue_tracker.json: <ws_root>/timeline.jsonl
        """
        try:
            from core.timeline_store import TimelineStore, timeline_path_for_issue_tracker_path

            return TimelineStore(timeline_path_for_issue_tracker_path(self.path))
        except Exception:
            return None

    def _log_event(
        self,
        *args,
        event_type: str = "",
        summary: str = "",
        issue_id: str = "",
        data: Optional[Dict[str, Any]] = None,
        actor: str = "user",
    ) -> None:
        """
        Backward-compatible logger:
          - supports calling as _log_event(event_type, summary, issue_id=..., data=...)
          - supports calling as _log_event(event_type="...", summary="...", issue_id="...")
        Never raises.
        """
        # Allow positional usage: (event_type, summary)
        try:
            if args:
                if len(args) >= 1 and not event_type:
                    event_type = str(args[0] or "")
                if len(args) >= 2 and not summary:
                    summary = str(args[1] or "")
        except Exception:
            pass

        tl = self._timeline()
        if tl is None:
            return
        try:
            tl.log(
                scope="issue",
                event_type=str(event_type or ""),
                summary=str(summary or ""),
                issue_id=str(issue_id or ""),
                actor=str(actor or "user"),
                data=data or {},
            )
        except Exception:
            return

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
            for _, rec in list(data.items()):
                if isinstance(rec, dict):
                    _ensure_contact(rec)
                    _ensure_issue_meta(rec)
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
        existing = data.get(issue_id)
        rec = existing if isinstance(existing, dict) else {}

        now = _utc_now_iso()
        is_new = not bool(rec.get("created_at"))

        if is_new:
            rec["created_at"] = now

        prev_resolved = bool(rec.get("resolved", False))
        prev_notes = str(rec.get("notes", "") or "")

        if resolved is not None:
            rec["resolved"] = bool(resolved)
            if bool(resolved):
                if not rec.get("resolved_at"):
                    rec["resolved_at"] = now
                _ensure_contact(rec)
                rec["contact"]["status"] = "Resolved"
                rec["status"] = "Resolved"
            else:
                rec["resolved_at"] = ""
                if rec.get("status") == "Resolved":
                    rec["status"] = "Open"

        if notes is not None:
            rec["notes"] = str(notes)

        rec["updated_at"] = now
        rec["last_action_at"] = now

        _ensure_contact(rec)
        _ensure_issue_meta(rec)
        data[issue_id] = rec
        self.save(data)

        # Timeline events (best-effort)
        if is_new:
            self._log_event(
                event_type="issue.created",
                summary="Issue created",
                issue_id=issue_id,
                data={},
            )

        if resolved is not None and prev_resolved != bool(resolved):
            self._log_event(
                event_type="issue.resolved_changed",
                summary=f"Resolved set to {bool(resolved)}",
                issue_id=issue_id,
                data={"prev": prev_resolved, "new": bool(resolved)},
            )

        if notes is not None and prev_notes != str(notes):
            self._log_event(
                event_type="issue.notes_updated",
                summary="Notes updated",
                issue_id=issue_id,
                data={"prev": prev_notes, "new": str(notes)},
            )

    def set_resolved(self, issue_id: str, resolved: bool) -> None:
        self.upsert(issue_id=issue_id, resolved=resolved)

    def set_notes(self, issue_id: str, notes: str) -> None:
        self.upsert(issue_id=issue_id, notes=notes)

    # ----------------------------
    # Ownership / Status / Next action
    # ----------------------------
    def get_issue(self, issue_id: str) -> Dict[str, Any]:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return {}
        data = self.load()
        rec = data.get(issue_id, {})
        if not isinstance(rec, dict):
            return {}
        _ensure_contact(rec)
        _ensure_issue_meta(rec)
        return rec

    def set_owner(self, issue_id: str, owner: str) -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return

        data = self.load()
        existing = data.get(issue_id)
        rec = existing if isinstance(existing, dict) else {}
        now = _utc_now_iso()
        is_new = not bool(rec.get("created_at"))

        prev_owner = str(rec.get("owner", "") or "")

        if is_new:
            rec["created_at"] = now
        rec["updated_at"] = now
        rec["last_action_at"] = now

        _ensure_contact(rec)
        _ensure_issue_meta(rec)

        rec["owner"] = str(owner or "").strip()

        data[issue_id] = rec
        self.save(data)

        if is_new:
            self._log_event("issue.created", "Issue created", issue_id=issue_id, data={})
        if prev_owner != rec["owner"]:
            self._log_event(
                event_type="issue.owner_set",
                summary=f"Owner set to {rec['owner'] or '(blank)'}",
                issue_id=issue_id,
                data={"prev": prev_owner, "new": rec["owner"]},
            )

    def set_issue_status(self, issue_id: str, status: str) -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return

        status = str(status or "").strip()
        if status not in ISSUE_STATUSES:
            return

        data = self.load()
        existing = data.get(issue_id)
        rec = existing if isinstance(existing, dict) else {}
        now = _utc_now_iso()
        is_new = not bool(rec.get("created_at"))

        prev_status = str(rec.get("status", "") or "")
        prev_resolved = bool(rec.get("resolved", False))

        if is_new:
            rec["created_at"] = now
        rec["updated_at"] = now
        rec["last_action_at"] = now

        _ensure_contact(rec)
        _ensure_issue_meta(rec)

        rec["status"] = status

        if status == "Resolved":
            rec["resolved"] = True
            if not rec.get("resolved_at"):
                rec["resolved_at"] = now
            rec["contact"]["status"] = "Resolved"
        else:
            rec["resolved"] = False
            rec["resolved_at"] = ""
            if rec["contact"]["status"] == "Resolved":
                rec["contact"]["status"] = "Not Contacted"

        data[issue_id] = rec
        self.save(data)

        if is_new:
            self._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

        if prev_status != status:
            self._log_event(
                event_type="issue.status_changed",
                summary=f"Status changed to {status}",
                issue_id=issue_id,
                data={"prev": prev_status, "new": status},
            )

        if prev_resolved != bool(rec.get("resolved", False)):
            self._log_event(
                event_type="issue.resolved_changed",
                summary=f"Resolved set to {bool(rec.get('resolved', False))}",
                issue_id=issue_id,
                data={"prev": prev_resolved, "new": bool(rec.get("resolved", False))},
            )

    def set_next_action_at(self, issue_id: str, next_action_at: str) -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return

        data = self.load()
        existing = data.get(issue_id)
        rec = existing if isinstance(existing, dict) else {}
        now = _utc_now_iso()
        is_new = not bool(rec.get("created_at"))

        prev_next = str(rec.get("next_action_at", "") or "")

        if is_new:
            rec["created_at"] = now
        rec["updated_at"] = now
        rec["last_action_at"] = now

        _ensure_contact(rec)
        _ensure_issue_meta(rec)

        rec["next_action_at"] = str(next_action_at or "").strip()

        data[issue_id] = rec
        self.save(data)

        if is_new:
            self._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

        if prev_next != rec["next_action_at"]:
            self._log_event(
                event_type="issue.next_action_set",
                summary=f"Next action set to {rec['next_action_at'] or '(blank)'}",
                issue_id=issue_id,
                data={"prev": prev_next, "new": rec["next_action_at"]},
            )

    def get_issue_summary(self) -> Dict[str, int]:
        data = self.load()
        counts = {s: 0 for s in ISSUE_STATUSES}
        for _, rec in data.items():
            if not isinstance(rec, dict):
                continue
            _ensure_contact(rec)
            _ensure_issue_meta(rec)
            s = (rec.get("status") or "Open").strip()
            if s not in counts:
                s = "Open"
            counts[s] += 1
        return counts

    # ----------------------------
    # Contact / Follow-up tracking
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
        existing = data.get(issue_id)
        rec = existing if isinstance(existing, dict) else {}

        now = _utc_now_iso()
        is_new = not bool(rec.get("created_at"))

        if is_new:
            rec["created_at"] = now
        rec["updated_at"] = now
        rec["last_action_at"] = now

        _ensure_contact(rec)
        _ensure_issue_meta(rec)

        prev_contact_status = str(rec["contact"].get("status", "") or "Not Contacted")
        prev_count = int(rec["contact"].get("follow_up_count") or 0)

        rec["contact"]["status"] = new_status
        rec["contact"]["last_contacted_at"] = now
        rec["contact"]["channel"] = str(channel or "").strip()
        rec["contact"]["follow_up_count"] = prev_count + 1

        rec["contact"]["history"].append(
            {
                "timestamp": now,
                "channel": rec["contact"]["channel"],
                "note": str(note or ""),
                "status": new_status,
            }
        )

        if rec.get("status") != "Resolved" and new_status in ("Waiting", "Escalated"):
            rec["status"] = "Waiting"

        data[issue_id] = rec
        self.save(data)

        if is_new:
            self._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

        self._log_event(
            event_type="contact.mark_contacted",
            summary=f"Contact logged ({rec['contact']['channel'] or 'channel'})",
            issue_id=issue_id,
            data={
                "channel": rec["contact"]["channel"],
                "note": str(note or ""),
                "prev_status": prev_contact_status,
                "new_status": new_status,
                "follow_up_count": rec["contact"]["follow_up_count"],
            },
        )

    def increment_followup(self, issue_id: str, channel: str = "email", note: str = "") -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return

        data = self.load()
        existing = data.get(issue_id)
        rec = existing if isinstance(existing, dict) else {}

        now = _utc_now_iso()
        is_new = not bool(rec.get("created_at"))

        if is_new:
            rec["created_at"] = now
        rec["updated_at"] = now
        rec["last_action_at"] = now

        _ensure_contact(rec)
        _ensure_issue_meta(rec)

        prev_count = int(rec["contact"].get("follow_up_count") or 0)
        prev_contact_status = str(rec["contact"].get("status", "") or "Not Contacted")

        rec["contact"]["follow_up_count"] = prev_count + 1
        rec["contact"]["last_contacted_at"] = now
        rec["contact"]["channel"] = str(channel or "").strip()

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

        if rec.get("status") != "Resolved":
            rec["status"] = "Waiting"

        data[issue_id] = rec
        self.save(data)

        if is_new:
            self._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

        self._log_event(
            event_type="contact.followup",
            summary="Follow-up logged",
            issue_id=issue_id,
            data={
                "channel": rec["contact"]["channel"],
                "note": str(note or ""),
                "prev_status": prev_contact_status,
                "new_status": rec["contact"]["status"],
                "prev_follow_up_count": prev_count,
                "new_follow_up_count": rec["contact"]["follow_up_count"],
            },
        )

    def set_contact_status(self, issue_id: str, status: str) -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return
        if status not in CONTACT_STATUSES:
            return

        data = self.load()
        existing = data.get(issue_id)
        rec = existing if isinstance(existing, dict) else {}

        now = _utc_now_iso()
        is_new = not bool(rec.get("created_at"))

        if is_new:
            rec["created_at"] = now
        rec["updated_at"] = now
        rec["last_action_at"] = now

        _ensure_contact(rec)
        _ensure_issue_meta(rec)

        prev_contact_status = str(rec["contact"].get("status", "") or "Not Contacted")
        rec["contact"]["status"] = status

        if status == "Resolved":
            rec["resolved"] = True
            rec["status"] = "Resolved"
            if not rec.get("resolved_at"):
                rec["resolved_at"] = now
        elif status in ("Waiting", "Escalated") and rec.get("status") != "Resolved":
            rec["status"] = "Waiting"

        data[issue_id] = rec
        self.save(data)

        if is_new:
            self._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

        if prev_contact_status != status:
            self._log_event(
                event_type="contact.status_changed",
                summary=f"Contact status changed to {status}",
                issue_id=issue_id,
                data={"prev": prev_contact_status, "new": status},
            )

    def get_contact_summary(self) -> Dict[str, int]:
        data = self.load()
        counts = {s: 0 for s in CONTACT_STATUSES}
        for _, rec in data.items():
            if not isinstance(rec, dict):
                continue
            _ensure_contact(rec)
            _ensure_issue_meta(rec)
            s = rec["contact"].get("status") or "Not Contacted"
            if s not in counts:
                s = "Not Contacted"
            counts[s] += 1
        return counts

    # ----------------------------
    # Maintenance
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
