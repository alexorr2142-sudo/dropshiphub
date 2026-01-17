from __future__ import annotations

from typing import Any, Dict, Optional

from core.issue_tracker_helpers import ensure_contact, ensure_issue_meta, merge_context
from core.issue_tracker_schema import ISSUE_STATUSES
from core.issue_tracker_time import utc_now_iso


def upsert(
    store,
    *,
    issue_id: str,
    resolved: Optional[bool] = None,
    notes: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    issue_id = str(issue_id or "").strip()
    if not issue_id:
        return

    data = store.load()
    existing = data.get(issue_id)
    rec = existing if isinstance(existing, dict) else {}

    now = utc_now_iso()
    is_new = not bool(rec.get("created_at"))

    if is_new:
        rec["created_at"] = now

    rec = merge_context(rec, context)

    prev_resolved = bool(rec.get("resolved", False))
    prev_notes = str(rec.get("notes", "") or "")

    if resolved is not None:
        rec["resolved"] = bool(resolved)
        if bool(resolved):
            if not rec.get("resolved_at"):
                rec["resolved_at"] = now
            ensure_contact(rec)
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

    ensure_contact(rec)
    ensure_issue_meta(rec)
    data[issue_id] = rec
    store.save(data)

    # Timeline events (best-effort)
    if is_new:
        store._log_event(
            event_type="issue.created",
            summary="Issue created",
            issue_id=issue_id,
            data={},
        )

    if resolved is not None and prev_resolved != bool(resolved):
        store._log_event(
            event_type="issue.resolved_changed",
            summary=f"Resolved set to {bool(resolved)}",
            issue_id=issue_id,
            data={"prev": prev_resolved, "new": bool(resolved)},
        )

    if notes is not None and prev_notes != str(notes):
        store._log_event(
            event_type="issue.notes_updated",
            summary="Notes updated",
            issue_id=issue_id,
            data={"prev": prev_notes, "new": str(notes)},
        )


def get_issue(store, *, issue_id: str) -> Dict[str, Any]:
    issue_id = str(issue_id or "").strip()
    if not issue_id:
        return {}
    data = store.load()
    rec = data.get(issue_id, {})
    if not isinstance(rec, dict):
        return {}
    ensure_contact(rec)
    ensure_issue_meta(rec)
    return rec


def set_owner(store, *, issue_id: str, owner: str, context: Optional[Dict[str, Any]] = None) -> None:
    issue_id = str(issue_id or "").strip()
    if not issue_id:
        return

    data = store.load()
    existing = data.get(issue_id)
    rec = existing if isinstance(existing, dict) else {}
    now = utc_now_iso()
    is_new = not bool(rec.get("created_at"))

    prev_owner = str(rec.get("owner", "") or "")

    if is_new:
        rec["created_at"] = now
    rec["updated_at"] = now
    rec["last_action_at"] = now

    rec = merge_context(rec, context)

    ensure_contact(rec)
    ensure_issue_meta(rec)

    rec["owner"] = str(owner or "").strip()

    data[issue_id] = rec
    store.save(data)

    if is_new:
        store._log_event("issue.created", "Issue created", issue_id=issue_id, data={})
    if prev_owner != rec["owner"]:
        store._log_event(
            event_type="issue.owner_set",
            summary=f"Owner set to {rec['owner'] or '(blank)'}",
            issue_id=issue_id,
            data={"prev": prev_owner, "new": rec["owner"]},
        )


def set_issue_status(store, *, issue_id: str, status: str, context: Optional[Dict[str, Any]] = None) -> None:
    issue_id = str(issue_id or "").strip()
    if not issue_id:
        return

    status = str(status or "").strip()
    if status not in ISSUE_STATUSES:
        return

    data = store.load()
    existing = data.get(issue_id)
    rec = existing if isinstance(existing, dict) else {}
    now = utc_now_iso()
    is_new = not bool(rec.get("created_at"))

    prev_status = str(rec.get("status", "") or "")
    prev_resolved = bool(rec.get("resolved", False))

    if is_new:
        rec["created_at"] = now
    rec["updated_at"] = now
    rec["last_action_at"] = now

    rec = merge_context(rec, context)

    ensure_contact(rec)
    ensure_issue_meta(rec)

    rec["status"] = status

    if status == "Resolved":
        rec["resolved"] = True
        if not rec.get("resolved_at"):
            rec["resolved_at"] = now
        rec["contact"]["status"] = "Resolved"
    else:
        rec["resolved"] = False
        rec["resolved_at"] = ""
        if rec["contact"].get("status") == "Resolved":
            rec["contact"]["status"] = "Not Contacted"

    data[issue_id] = rec
    store.save(data)

    if is_new:
        store._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

    if prev_status != status:
        store._log_event(
            event_type="issue.status_changed",
            summary=f"Status changed to {status}",
            issue_id=issue_id,
            data={"prev": prev_status, "new": status},
        )

    if prev_resolved != bool(rec.get("resolved", False)):
        store._log_event(
            event_type="issue.resolved_changed",
            summary=f"Resolved set to {bool(rec.get('resolved', False))}",
            issue_id=issue_id,
            data={"prev": prev_resolved, "new": bool(rec.get("resolved", False))},
        )


def set_next_action_at(store, *, issue_id: str, next_action_at: str, context: Optional[Dict[str, Any]] = None) -> None:
    issue_id = str(issue_id or "").strip()
    if not issue_id:
        return

    data = store.load()
    existing = data.get(issue_id)
    rec = existing if isinstance(existing, dict) else {}
    now = utc_now_iso()
    is_new = not bool(rec.get("created_at"))

    prev_next = str(rec.get("next_action_at", "") or "")

    if is_new:
        rec["created_at"] = now
    rec["updated_at"] = now
    rec["last_action_at"] = now

    rec = merge_context(rec, context)

    ensure_contact(rec)
    ensure_issue_meta(rec)

    rec["next_action_at"] = str(next_action_at or "").strip()

    data[issue_id] = rec
    store.save(data)

    if is_new:
        store._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

    if prev_next != rec["next_action_at"]:
        store._log_event(
            event_type="issue.next_action_set",
            summary=f"Next action set to {rec['next_action_at'] or '(blank)'}",
            issue_id=issue_id,
            data={"prev": prev_next, "new": rec["next_action_at"]},
        )


def get_issue_summary(store) -> Dict[str, int]:
    data = store.load()
    counts = {s: 0 for s in ISSUE_STATUSES}
    for _, rec in data.items():
        if not isinstance(rec, dict):
            continue
        ensure_contact(rec)
        ensure_issue_meta(rec)
        s = (rec.get("status") or "Open").strip()
        if s not in counts:
            s = "Open"
        counts[s] += 1
    return counts
