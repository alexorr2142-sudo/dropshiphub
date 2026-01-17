from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from core.issue_tracker_helpers import ensure_contact, ensure_issue_meta, merge_context
from core.issue_tracker_schema import CONTACT_STATUSES, ISSUE_STATUSES, issue_tracker_path_for_ws_root
from core.issue_tracker_time import utc_now_iso

import core.issue_tracker_ops_issue as ops_issue
import core.issue_tracker_ops_contact as ops_contact
import core.issue_tracker_ops_maintenance as ops_maint


@dataclass
class IssueRecord:
    resolved: bool = False
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str = ""


class IssueTrackerStore:
    """JSON-backed issue tracker with migration-safe schema.

    NOTE: The implementation is split into multiple small modules to enforce
    the repo rule: no file over 300 lines.
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
                        "supplier_name": rec.get("supplier_name", None),
                        "supplier_email": rec.get("supplier_email", None),
                        "order_id": rec.get("order_id", None),
                        "order_ids": rec.get("order_ids", None),
                    },
                    sort_keys=True,
                    default=str,
                )

                ensure_contact(rec)
                ensure_issue_meta(rec)

                after = json.dumps(
                    {
                        "contact": rec.get("contact", None),
                        "owner": rec.get("owner", None),
                        "status": rec.get("status", None),
                        "next_action_at": rec.get("next_action_at", None),
                        "supplier_name": rec.get("supplier_name", None),
                        "supplier_email": rec.get("supplier_email", None),
                        "order_id": rec.get("order_id", None),
                        "order_ids": rec.get("order_ids", None),
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
        """Return TimelineStore or None. Never raises."""
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
        """Backward-compatible logger. Never raises."""
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

        supplier_name = ""
        order_id = ""
        try:
            rec = self.get_issue(issue_id) if issue_id else {}
            if isinstance(rec, dict):
                supplier_name = str(rec.get("supplier_name", "") or "")
                order_id = str(rec.get("order_id", "") or "")
        except Exception:
            supplier_name = ""
            order_id = ""

        try:
            tl.log(
                scope="issue",
                event_type=str(event_type or ""),
                summary=str(summary or ""),
                issue_id=str(issue_id or ""),
                supplier_name=supplier_name,
                order_id=order_id,
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
                    ensure_contact(rec)
                    ensure_issue_meta(rec)
            return data
        except Exception:
            return {}

    def save(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ----------------------------
    # Read helpers
    # ----------------------------
    def get_issue(self, issue_id: str) -> Dict[str, Any]:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return {}
        data = self.load()
        rec = data.get(issue_id, {})
        if not isinstance(rec, dict):
            return {}
        ensure_contact(rec)
        ensure_issue_meta(rec)
        return rec

    # ----------------------------
    # Delegated operations
    # ----------------------------
    def upsert(
        self,
        issue_id: str,
        resolved: Optional[bool] = None,
        notes: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        return ops_issue.upsert(self, issue_id=issue_id, resolved=resolved, notes=notes, context=context)

    def set_resolved(self, issue_id: str, resolved: bool, context: Optional[Dict[str, Any]] = None) -> None:
        return self.upsert(issue_id=issue_id, resolved=resolved, context=context)

    def set_notes(self, issue_id: str, notes: str, context: Optional[Dict[str, Any]] = None) -> None:
        return self.upsert(issue_id=issue_id, notes=notes, context=context)

    def set_owner(self, issue_id: str, owner: str, context: Optional[Dict[str, Any]] = None) -> None:
        return ops_issue.set_owner(self, issue_id=issue_id, owner=owner, context=context)

    def set_issue_status(self, issue_id: str, status: str, context: Optional[Dict[str, Any]] = None) -> None:
        return ops_issue.set_issue_status(self, issue_id=issue_id, status=status, context=context)

    def set_next_action_at(self, issue_id: str, next_action_at: str, context: Optional[Dict[str, Any]] = None) -> None:
        return ops_issue.set_next_action_at(self, issue_id=issue_id, next_action_at=next_action_at, context=context)

    def get_issue_summary(self) -> Dict[str, int]:
        return ops_issue.get_issue_summary(self)

    def mark_contacted(
        self,
        issue_id: str,
        channel: str = "email",
        note: str = "",
        new_status: str = "Contacted",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        return ops_contact.mark_contacted(
            self,
            issue_id=issue_id,
            channel=channel,
            note=note,
            new_status=new_status,
            context=context,
        )

    def increment_followup(
        self,
        issue_id: str,
        channel: str = "email",
        note: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        return ops_contact.increment_followup(self, issue_id=issue_id, channel=channel, note=note, context=context)

    def set_contact_status(self, issue_id: str, status: str, context: Optional[Dict[str, Any]] = None) -> None:
        return ops_contact.set_contact_status(self, issue_id=issue_id, status=status, context=context)

    def get_contact_summary(self) -> Dict[str, int]:
        return ops_contact.get_contact_summary(self)

    def prune_resolved_older_than_days(self, days: int) -> int:
        return ops_maint.prune_resolved_older_than_days(self, days=days)

    def clear_resolved(self) -> int:
        return ops_maint.clear_resolved(self)
