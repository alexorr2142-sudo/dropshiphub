# core/scorecards.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import pandas as pd

from core.styling import add_urgency_column
from core.workspaces import list_runs


def _contains_any(s: str, terms: list[str]) -> bool:
    s = (s or "").lower()
    return any(t in s for t in terms)


def build_supplier_scorecard_from_run(line_status_df: pd.DataFrame, exceptions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Builds a per-supplier scorecard from:
      - line_status_df (requires supplier_name)
      - exceptions_df (optional; uses supplier_name + urgency + issue text)

    Output columns (best effort):
      supplier_name, total_lines, exception_lines, exception_rate, critical, high,
      missing_tracking_flags, late_flags, carrier_exception_flags
    """
    if line_status_df is None or not isinstance(line_status_df, pd.DataFrame) or line_status_df.empty:
        return pd.DataFrame()

    df = line_status_df.copy()
    if "supplier_name" not in df.columns:
        return pd.DataFrame()

    df["supplier_name"] = df["supplier_name"].fillna("").astype(str)
    df = df[df["supplier_name"].str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame()

    base = df.groupby("supplier_name").size().reset_index(name="total_lines")

    exc = None
    if (
        exceptions_df is not None
        and isinstance(exceptions_df, pd.DataFrame)
        and not exceptions_df.empty
        and "supplier_name" in exceptions_df.columns
    ):
        exc = exceptions_df.copy()
        exc["supplier_name"] = exc["supplier_name"].fillna("").astype(str)
        exc = exc[exc["supplier_name"].str.strip() != ""].copy()

        if not exc.empty:
            if "Urgency" not in exc.columns:
                exc = add_urgency_column(exc)

            exc_counts = exc.groupby("supplier_name").size().reset_index(name="exception_lines")
            crit = exc[exc["Urgency"] == "Critical"].groupby("supplier_name").size().reset_index(name="critical")
            high = exc[exc["Urgency"] == "High"].groupby("supplier_name").size().reset_index(name="high")
        else:
            exc_counts = pd.DataFrame(columns=["supplier_name", "exception_lines"])
            crit = pd.DataFrame(columns=["supplier_name", "critical"])
            high = pd.DataFrame(columns=["supplier_name", "high"])
    else:
        exc_counts = pd.DataFrame(columns=["supplier_name", "exception_lines"])
        crit = pd.DataFrame(columns=["supplier_name", "critical"])
        high = pd.DataFrame(columns=["supplier_name", "high"])

    out = (
        base.merge(exc_counts, on="supplier_name", how="left")
        .merge(crit, on="supplier_name", how="left")
        .merge(high, on="supplier_name", how="left")
    )

    out["exception_lines"] = out["exception_lines"].fillna(0).astype(int)
    out["critical"] = out["critical"].fillna(0).astype(int)
    out["high"] = out["high"].fillna(0).astype(int)
    out["exception_rate"] = (out["exception_lines"] / out["total_lines"]).replace([pd.NA], 0).round(4)

    if exc is not None and not exc.empty:

        def _flag_count(term_list: list[str]) -> pd.DataFrame:
            tmp = exc.copy()
            blob = (
                tmp.get("issue_type", "").astype(str).fillna("") + " "
                + tmp.get("explanation", "").astype(str).fillna("") + " "
                + tmp.get("next_action", "").astype(str).fillna("")
            ).str.lower()
            tmp["_flag"] = blob.apply(lambda x: _contains_any(x, term_list))
            return tmp[tmp["_flag"]].groupby("supplier_name").size().reset_index(name="count")

        missing_tracking_terms = ["missing tracking", "no tracking", "tracking missing", "invalid tracking"]
        late_terms = ["late", "overdue", "past due", "late unshipped"]
        carrier_terms = ["carrier exception", "exception", "stuck", "lost", "returned to sender"]

        mt = _flag_count(missing_tracking_terms).rename(columns={"count": "missing_tracking_flags"})
        lt = _flag_count(late_terms).rename(columns={"count": "late_flags"})
        ct = _flag_count(carrier_terms).rename(columns={"count": "carrier_exception_flags"})

        out = (
            out.merge(mt, on="supplier_name", how="left")
            .merge(lt, on="supplier_name", how="left")
            .merge(ct, on="supplier_name", how="left")
        )
        for c in ["missing_tracking_flags", "late_flags", "carrier_exception_flags"]:
            out[c] = out.get(c, 0).fillna(0).astype(int)
    else:
        out["missing_tracking_flags"] = 0
        out["late_flags"] = 0
        out["carrier_exception_flags"] = 0

    out = out.sort_values(["exception_rate", "critical", "high"], ascending=[False, False, False])
    return out


def _parse_run_id_to_dt(run_id: str) -> Optional[datetime]:
    try:
        return datetime.strptime(run_id, "%Y%m%dT%H%M%SZ")
    except Exception:
        return None


def _maybe_cache_data(func: Callable):
    """
    Optional Streamlit caching. If Streamlit isn't available (tests/CLI),
    this becomes a no-op decorator.
    """
    try:
        import streamlit as st  # type: ignore

        return st.cache_data(show_spinner=False)(func)
    except Exception:
        return func


@_maybe_cache_data
def load_recent_scorecard_history(ws_root_str: str, max_runs: int = 25) -> pd.DataFrame:
    """
    Backward-compatible signature: accepts ws_root_str.
    """
    return load_recent_scorecard_history_path(Path(ws_root_str), max_runs=max_runs)


def load_recent_scorecard_history_path(ws_root: Path, max_runs: int = 25) -> pd.DataFrame:
    """
    Preferred signature: accepts ws_root Path.
    Builds a long table across the last N runs with per-supplier metrics.
    """
    runs = list_runs(ws_root)[: int(max_runs)]
    all_rows: list[pd.DataFrame] = []

    for r in runs:
        run_dir = Path(r["path"])
        run_id = r.get("run_id", run_dir.name)
        run_dt = _parse_run_id_to_dt(str(run_id))

        line_path = run_dir / "line_status.csv"
        exc_path = run_dir / "exceptions.csv"
        if not line_path.exists():
            continue

        try:
            line_df = pd.read_csv(line_path)
        except Exception:
            continue

        try:
            exc_df = pd.read_csv(exc_path) if exc_path.exists() else pd.DataFrame()
        except Exception:
            exc_df = pd.DataFrame()

        sc = build_supplier_scorecard_from_run(line_df, exc_df)
        if sc is None or sc.empty:
            continue

        sc = sc.copy()
        sc["run_id"] = str(run_id)
        sc["run_dt"] = run_dt
        all_rows.append(sc)

    if not all_rows:
        return pd.DataFrame()

    return pd.concat(all_rows, ignore_index=True, sort=False)
