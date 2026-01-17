# core/timeline_store.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timeline_path_for_ws_root(ws_root: Path) -> Path:
    return Path(ws_root) / "timeline.jsonl"


def timeline_path_for_issue_tracker_path(issue_tracker_path: Path) -> Path:
    """
    Keep timeline beside issue_tracker.json:
      <ws_root>/issue_tracker.json
      <ws_root>/timeline.jsonl
    """
    issue_tracker_path = Path(issue_tracker_path)
    return issue_tracker_path.parent / "timeline.jsonl"


@dataclass
class TimelineEvent:
    ts: str
    scope: str  # "issue" | "order" | "supplier" | "system"
    event_type: str
    summary: str

    # Common ids
    issue_id: str = ""
    order_id: str = ""
    supplier_name: str = ""

    # Optional metadata
    severity: str = ""
    actor: str = "user"  # "user" | "system"
    actor_id: str = ""
    data: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "event_id": str(uuid4()),
            "ts": self.ts,
            "scope": self.scope,
            "event_type": self.event_type,
            "summary": self.summary,
            "issue_id": self.issue_id,
            "order_id": self.order_id,
            "supplier_name": self.supplier_name,
            "severity": self.severity,
            "actor": self.actor,
            "actor_id": self.actor_id,
            "data": self.data or {},
        }


class TimelineStore:
    """
    Append-only JSONL timeline.
    Each line is a single event dict.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, event: Dict[str, Any]) -> None:
        """
        Fail-safe append.
        Never raises to callers (timeline must never break app).
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(event, ensure_ascii=False)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            # Intentionally swallow errors
            return

    def log(
        self,
        *,
        scope: str,
        event_type: str,
        summary: str,
        issue_id: str = "",
        order_id: str = "",
        supplier_name: str = "",
        severity: str = "",
        actor: str = "user",
        actor_id: str = "",
        data: Optional[Dict[str, Any]] = None,
        ts: Optional[str] = None,
    ) -> None:
        ev = TimelineEvent(
            ts=ts or _utc_now_iso(),
            scope=scope,
            event_type=event_type,
            summary=summary,
            issue_id=str(issue_id or ""),
            order_id=str(order_id or ""),
            supplier_name=str(supplier_name or ""),
            severity=str(severity or ""),
            actor=str(actor or "user"),
            actor_id=str(actor_id or ""),
            data=data or {},
        )
        self.append(ev.as_dict())
