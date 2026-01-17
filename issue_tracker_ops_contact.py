from __future__ import annotations

from typing import Any, Dict, Optional

from core.issue_tracker_helpers import ensure_contact, ensure_issue_meta, merge_context
from core.issue_tracker_schema import CONTACT_STATUSES
from core.issue_tracker_time import utc_now_iso


def mark_contacted(
    store,
    *,
    issue_id: str,
    channel: str = "email",
    note: str = "",
    new_status: str = "Contacted",
    context: Optional[Dict[str, Any]] = None,
) -> None:
    issue_id = str(issue_id or "").strip()
    if not issue_id:
        return

    if new_status not in CONTACT_STATUSES:
        new_status = "Contacted"

    data = store.load()
    existing = data.get(issue_id)
    rec = existing if isinstance(existing, dict) else {}

    now = utc_now_iso()
    is_new = not bool(rec.get("created_at"))

    if is_new:
        rec["created_at"] = now
    rec["updated_at"] = now
    rec["last_action_at"] = now

    rec = merge_context(rec, context)
    ensure_contact(rec)
    ensure_issue_meta(rec)

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
    store.save(data)

    if is_new:
        store._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

    store._log_event(
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


def increment_followup(
    store,
    *,
    issue_id: str,
    channel: str = "email",
    note: str = "",
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
    rec["updated_at"] = now
    rec["last_action_at"] = now

    rec = merge_context(rec, context)
    ensure_contact(rec)
    ensure_issue_meta(rec)

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
    store.save(data)

    if is_new:
        store._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

    store._log_event(
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


def set_contact_status(
    store,
    *,
    issue_id: str,
    status: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    issue_id = str(issue_id or "").strip()
    if not issue_id:
        return
    if status not in CONTACT_STATUSES:
        return

    data = store.load()
    existing = data.get(issue_id)
    rec = existing if isinstance(existing, dict) else {}

    now = utc_now_iso()
    is_new = not bool(rec.get("created_at"))

    if is_new:
        rec["created_at"] = now
    rec["updated_at"] = now
    rec["last_action_at"] = now

    rec = merge_context(rec, context)
    ensure_contact(rec)
    ensure_issue_meta(rec)

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
    store.save(data)

    if is_new:
        store._log_event("issue.created", "Issue created", issue_id=issue_id, data={})

    if prev_contact_status != status:
        store._log_event(
            event_type="contact.status_changed",
            summary=f"Contact status changed to {status}",
            issue_id=issue_id,
            data={"prev": prev_contact_status, "new": status},
        )


def get_contact_summary(store) -> Dict[str, int]:
    data = store.load()
    counts = {s: 0 for s in CONTACT_STATUSES}
    for _, rec in data.items():
        if not isinstance(rec, dict):
            continue
        ensure_contact(rec)
        ensure_issue_meta(rec)
        s = rec["contact"].get("status") or "Not Contacted"
        if s not in counts:
            s = "Not Contacted"
        counts[s] += 1
    return counts
