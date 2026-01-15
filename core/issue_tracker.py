# core/issue_tracker.py
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict


@dataclass
class IssueTrackerStore:
    """
    Simple JSON-backed issue tracker.
    Stores: { issue_id: { resolved: bool, notes: str, updated_at: iso } }
    """
    data_dir: Path | None = None
    filename: str = "issue_tracker.json"

    def _root(self) -> Path:
        # Default to repo-local ./data/
        base = self.data_dir or (Path(__file__).resolve().parents[1] / "data")
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _path(self) -> Path:
        return self._root() / self.filename

    def load(self) -> Dict[str, Dict[str, Any]]:
        p = self._path()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    def save(self, issue_map: Dict[str, Dict[str, Any]]) -> None:
        # ensure updated_at
        now = datetime.utcnow().isoformat() + "Z"
        cleaned: Dict[str, Dict[str, Any]] = {}
        for k, v in (issue_map or {}).items():
            if not k:
                continue
            vv = dict(v or {})
            vv.setdefault("resolved", False)
            vv.setdefault("notes", "")
            vv["updated_at"] = vv.get("updated_at") or now
            cleaned[str(k)] = vv

        p = self._path()
        p.write_text(json.dumps(cleaned, indent=2, sort_keys=True), encoding="utf-8")

    def set_resolved(self, issue_id: str, resolved: bool) -> None:
        m = self.load()
        rec = dict(m.get(str(issue_id), {}) or {})
        rec["resolved"] = bool(resolved)
        rec["updated_at"] = datetime.utcnow().isoformat() + "Z"
        m[str(issue_id)] = rec
        self.save(m)

    def set_notes(self, issue_id: str, notes: str) -> None:
        m = self.load()
        rec = dict(m.get(str(issue_id), {}) or {})
        rec["notes"] = str(notes or "")
        rec["updated_at"] = datetime.utcnow().isoformat() + "Z"
        m[str(issue_id)] = rec
        self.save(m)

    def clear_resolved(self) -> int:
        m = self.load()
        before = len(m)
        m = {k: v for k, v in m.items() if not bool((v or {}).get("resolved", False))}
        self.save(m)
        return before - len(m)

    def prune_resolved_older_than_days(self, days: int) -> int:
        days = int(days)
        cutoff = datetime.utcnow() - timedelta(days=days)

        m = self.load()
        keep: Dict[str, Dict[str, Any]] = {}
        removed = 0

        for k, v in (m or {}).items():
            rec = dict(v or {})
            resolved = bool(rec.get("resolved", False))
            ts = str(rec.get("updated_at", "") or "")
            dt = None
            try:
                dt = datetime.fromisoformat(ts.replace("Z", ""))
            except Exception:
                dt = None

            if resolved and dt and dt < cutoff:
                removed += 1
                continue
            keep[str(k)] = rec

        self.save(keep)
        return removed
