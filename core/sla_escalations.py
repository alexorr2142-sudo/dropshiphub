# core/sla_escalations.py
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

# ✅ Step 2 import (NEW)
from dropshiphub.core.issue_tracker import make_issue_id


# -------------------------------
# Helpers
# -------------------------------
def _now_utc() -> pd.Timestamp:
    # Always timezone-aware
    return pd.Timestamp.now(tz="UTC")


def _to_utc(series: pd.Series) -> pd.Series:
    """
    Convert a Series to timezone-aware UTC datetimes safely.

    Handles:
      - strings
      - tz-naive datetimes
      - tz-aware datetimes (converts to UTC)
      - mixed/invalid values => NaT
    """
    if series is None:
        return pd.Series([], dtype="datetime64[ns, UTC]")

    s = pd.to_datetime(series, errors="coerce", utc=True)

    # If conversion produced tz-naive dtype (rare edge), localize
    # (most times utc=True already yields tz-aware)
    try:
        if getattr(s.dt, "tz", None) is None:
            s = s.dt.tz_localize("UTC")
    except Exception:
        # If s isn't datetime-like for some reason, re-coerce
        s = pd.to_datetime(series, errors="coerce", utc=True)

    return s


def _safe_col(df: pd.DataFrame, name: str) -> bool:
    return df is not None and not df.empty and name in df.columns


def _pick_due_date_col(df: pd.DataFrame) -> str | None:
    """
    Choose the best due-date style column present in line_status_df.
    """
    candidates = [
        "sla_due_date",
        "promised_ship_date",
        "ship_by_date",
        "sla_due_dt",
        "due_date",
    ]
    for c in candidates:
        if _safe_col(df, c):
            return c
    return None


def _pick_created_date_col(df: pd.DataFrame) -> str | None:
    candidates = [
        "order_created_at",
        "order_datetime_utc",
        "order_date",
        "created_at",
        "created_datetime",
    ]
    for c in candidates:
        if _safe_col(df, c):
            return c
    return None


# ✅ Step 2 helper (NEW)
def _attach_issue_ids(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensures df has a stable issue_id column for issue tracking.

    - Safe on None/empty frames
    - Won't overwrite if issue_id already exists
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    if "issue_id" in df.columns:
        return df

    out = df.copy()
    out["issue_id"] = out.apply(make_issue_id, axis=1)
    return out


# -------------------------------
# Output model (optional)
# -------------------------------
@dataclass
class SlaEscalationConfig:
    promised_ship_days: int = 3
    grace_days: int = 0
    at_risk_hours: int = 72  # show items due within next N hours


# -------------------------------
# Core builder
# -------------------------------
def build_sla_escalations(
    line_status_df: pd.DataFrame,
    followups: pd.DataFrame,
    promised_ship_days: int = 3,
    grace_days: int = 0,
    at_risk_hours: int = 72,
):
    """
    Returns:
      escalations_df, updated_followups_df

    escalations_df: supplier-level summary with counts by escalation bucket
    updated_followups_df: followups annotated with worst escalation bucket
    """
    df = line_status_df.copy() if line_status_df is not None else pd.DataFrame()
    fu = followups.copy() if followups is not None else pd.DataFrame()

    if df.empty:
        return pd.DataFrame(), fu

    if "supplier_name" not in df.columns:
        return pd.DataFrame(), fu

    # Determine due date
    due_col = _pick_due_date_col(df)
    created_col = _pick_created_date_col(df)

    # If we don't have a due date column, compute from created + promised_ship_days
    if due_col is None:
        if created_col is None:
            # no usable timing fields
            return pd.DataFrame(), fu

        df["_created_dt"] = _to_utc(df[created_col])
        # compute due in UTC
        df["_due_dt"] = df["_created_dt"] + pd.to_timedelta(int(promised_ship_days), unit="D")
    else:
        df["_due_dt"] = _to_utc(df[due_col])

    # Apply grace window (still UTC)
    if grace_days and int(grace_days) != 0:
        df["_due_dt"] = df["_due_dt"] + pd.to_timedelta(int(grace_days), unit="D")

    # Must have at least some due dates
    if df["_due_dt"].isna().all():
        return pd.DataFrame(), fu

    # Choose "open" lines to consider for escalation
    # We focus on not-yet-shipped OR missing tracking situations
    status = df.get("line_status", pd.Series([""] * len(df))).astype(str).fillna("")
    issue = df.get("issue_type", pd.Series([""] * len(df))).astype(str).fillna("")
    is_open = status.isin(["UNSHIPPED", "PARTIALLY_SHIPPED"]) | issue.str.contains("MISSING_TRACKING", na=False)

    work = df[is_open].copy()
    if work.empty:
        return pd.DataFrame(), fu

    # ✅ Step 2: attach issue_id at the line level (NEW)
    work
