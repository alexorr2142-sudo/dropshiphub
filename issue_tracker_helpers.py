from __future__ import annotations

from typing import Any, Dict, Optional


def ensure_contact(rec: Dict[str, Any]) -> Dict[str, Any]:
    contact = rec.get("contact") or {}
    if not isinstance(contact, dict):
        contact = {}

    contact.setdefault("status", "Not Contacted")
    contact.setdefault("last_contacted_at", "")
    contact.setdefault("channel", "")
    contact.setdefault("follow_up_count", 0)
    history = contact.get("history") or []
    if not isinstance(history, list):
        history = []
    contact["history"] = history
    rec["contact"] = contact
    return rec


def ensure_issue_meta(rec: Dict[str, Any]) -> Dict[str, Any]:
    rec.setdefault("owner", "")
    rec.setdefault("status", "Open")
    rec.setdefault("next_action_at", "")
    rec.setdefault("last_action_at", rec.get("updated_at", "") or "")
    return rec


def merge_context(rec: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge context fields into rec, but only fill blanks.

    Context is intentionally permissive (best-effort). Known fields:
      supplier_name, supplier_email, order_id, order_ids
    """
    if not context or not isinstance(context, dict):
        return rec

    allowed = [
        "supplier_name",
        "supplier_email",
        "order_id",
        "order_ids",
    ]

    for k in allowed:
        if k not in context:
            continue
        new_v = context.get(k)
        if new_v in (None, "", [], {}):
            continue
        old_v = rec.get(k)
        if old_v in (None, "", [], {}):
            rec[k] = new_v

    return rec
