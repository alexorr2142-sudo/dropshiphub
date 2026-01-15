# core/issue_tracker.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd


@dataclass
class IssueTrackerStore:
    """
    Persists per-issue state for followups/exceptions:
      - resolved flag
      - notes
      - timestamps

    Stored in a single JSON file per app tenant root, e.g. data/issue_tracker.json
    """
    path: Path

    def load(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def save(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data or {}, indent=2), encoding="utf-8")

    def upsert(self, issue_id: str, patch: Dict[str, Any]) -> None:
        issue_id = str(issue_id or "").strip()
        if not issue_id:
            return
        db = self.load()
        cur = db.get(issue_id, {})
        if not isinstance(cur, dict):
            cur = {}
        cur.update(patch or {})
        db[issue_id] = cur
        self.save(db)

    def bulk_apply_to_df(self, df: pd.DataFrame, issue_id_col: str = "issue_id") -> pd.DataFrame:
        """
        Adds/overwrites:
          - resolved (bool)
          - notes (str)
          - resolved_at (str)
          - updated_at (str)
        """
        if df is None or df.empty or issue_id_col not in df.columns:
            return df

        db = self.load()
        out = df.copy()

        def _get(issue_id: Any, key: str, default: Any):
            d = db.get(str(issue_id), {})
            if isinstance(d, dict) and key in d:
                return d.get(key)
            return default

        out["resolved"] = out[issue_id_col].apply(lambda x: bool(_get(x, "resolved", False)))
        out["notes"] = out[issue_id_col].apply(lambda x: str(_get(x, "notes", "") or ""))
        out["resolved_at"] = out[issue_id_col].apply(lambda x: str(_get(x, "resolved_at", "") or ""))
        out["updated_at"] = out[issue_id_col].apply(lambda x: str(_get(x, "updated_at", "") or ""))
        return out

    def prune_resolved(self, older_than_days: int = 30) -> int:
        """
        Deletes resolved items whose resolved_at is older than N days.
        Returns number of removed entries.
        """
        n = int(older_than_days)
        db = self.load()
        if not db:
            return 0

        now = pd.Timestamp.utcnow()
        keep: Dict[str, Dict[str, Any]] = {}
        removed = 0

        for issue_id, payload in db.items():
            if not isinstance(payload, dict):
                continue

            resolved = bool(payload.get("resolved", False))
            resolved_at = payload.get("resolved_at", "")

            if not resolved:
                keep[issue_id] = payload
                continue

            # If no timestamp, keep it (safer than deleting unknown age)
            if not resolved_at:
                keep[issue_id] = payload
                continue

            try:
                dt = pd.to_datetime(resolved_at, utc=True, errors="coerce")
            except Exception:
                dt = pd.NaT

            if pd.isna(dt):
                keep[issue_id] = payload
                continue

            age_days = (now - dt).total_seconds() / 86400.0
            if age_days > n:
                removed += 1
            else:
                keep[issue_id] = payload

        if removed:
            self.save(keep)
        return removed

    def clear_resolved(self) -> int:
        """
        Deletes ALL resolved entries. Keeps unresolved entries + notes intact.
        Returns number removed.
        """
        db = self.load()
        if not db:
            return 0

        keep: Dict[str, Dict[str, Any]] = {}
        removed = 0
        for issue_id, payload in db.items():
            if isinstance(payload, dict) and bool(payload.get("resolved", False)):
                removed += 1
                continue
            keep[issue_id] = payload if isinstance(payload, dict) else {}

        if removed:
            self.save(keep)
        return removed
