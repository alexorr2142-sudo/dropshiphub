# ui/timeline_ui.py
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st


def _safe_read_lines(path: Path, max_lines: int = 2000) -> List[str]:
    try:
        if not path.exists():
            return []
        # Read last N lines efficiently-ish (fine for small/medium files)
        lines = path.read_text(encoding="utf-8").splitlines()
        if max_lines and len(lines) > max_lines:
            return lines[-max_lines:]
        return lines
    except Exception:
        return []


def _parse_event(line: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def load_timeline_events(
    timeline_path: Path,
    *,
    issue_ids: Optional[Iterable[str]] = None,
    supplier_name: str = "",
    limit: int = 200,
) -> pd.DataFrame:
    """
    Loads events from JSONL. Best-effort, never raises.
    Filters by issue_ids and/or supplier_name when provided.
    Returns newest-first.
    """
    try:
        issue_set = set([str(x) for x in issue_ids]) if issue_ids else set()
        supplier_name = str(supplier_name or "").strip()

        rows: List[Dict[str, Any]] = []
        for line in _safe_read_lines(Path(timeline_path), max_lines=5000):
            ev = _parse_event(line)
            if not ev:
                continue

            iid = str(ev.get("issue_id", "") or "")
            sup = str(ev.get("supplier_name", "") or "")

            if issue_set and iid not in issue_set:
                continue
            if supplier_name and sup != supplier_name:
                continue

            rows.append(ev)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # Best-effort sort by ts desc
        if "ts" in df.columns:
            df["_ts"] = pd.to_datetime(df["ts"], errors="coerce")
            df = df.sort_values("_ts", ascending=False).drop(columns=["_ts"])
        else:
            df = df.iloc[::-1]

        if limit and len(df) > int(limit):
            df = df.head(int(limit))

        return df
    except Exception:
        return pd.DataFrame()


def render_timeline_panel(
    *,
    timeline_path: Path,
    title: str = "Timeline",
    issue_ids: Optional[Iterable[str]] = None,
    supplier_name: str = "",
    limit: int = 100,
    key_prefix: str = "timeline",
) -> None:
    """
    Simple renderer. Shows most recent events with filters.
    """
    with st.expander(title, expanded=False):
        df = load_timeline_events(
            timeline_path=Path(timeline_path),
            issue_ids=issue_ids,
            supplier_name=supplier_name,
            limit=limit,
        )

        if df is None or df.empty:
            st.caption("No timeline events yet.")
            return

        # Keep columns stable-ish
        cols_pref = [
            "ts",
            "scope",
            "event_type",
            "summary",
            "issue_id",
            "order_id",
            "supplier_name",
        ]
        cols = [c for c in cols_pref if c in df.columns] + [c for c in df.columns if c not in cols_pref]

        st.dataframe(df[cols], use_container_width=True, height=300)

        st.download_button(
            "Download timeline JSONL",
            data=Path(timeline_path).read_bytes() if Path(timeline_path).exists() else b"",
            file_name="timeline.jsonl",
            mime="application/json",
            key=f"{key_prefix}_dl_jsonl",
        )
