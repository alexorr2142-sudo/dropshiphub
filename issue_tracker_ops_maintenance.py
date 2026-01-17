from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from core.issue_tracker_time import parse_iso


def prune_resolved_older_than_days(store, *, days: int) -> int:
    days = int(days)
    if days <= 0:
        return 0

    data = store.load()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    removed = 0
    keep: Dict[str, Dict[str, Any]] = {}
    for k, rec in data.items():
        if not isinstance(rec, dict):
            continue

        if not bool(rec.get("resolved", False)):
            keep[k] = rec
            continue

        resolved_at = parse_iso(str(rec.get("resolved_at", ""))) or parse_iso(str(rec.get("updated_at", "")))
        if resolved_at and resolved_at < cutoff:
            removed += 1
        else:
            keep[k] = rec

    if removed:
        store.save(keep)
    return removed


def clear_resolved(store) -> int:
    data = store.load()
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
        store.save(keep)
    return removed
