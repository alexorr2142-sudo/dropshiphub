# core/sla_escalations.py
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


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

    now = _now_utc()

    # ✅ FIX: both sides are tz-aware UTC now, subtraction always works
    work["_days_to_due"] = (work["_due_dt"] - now).dt.total_seconds() / 86400.0

    # Bucket logic
    # - Overdue => Escalate / Firm follow-up depending on how late
    # - Due soon => At Risk / Reminder
    at_risk_days = float(at_risk_hours) / 24.0

    def _bucket(days_to_due: float) -> str:
        if pd.isna(days_to_due):
            return "Unknown"
        if days_to_due < -3:
            return "Escalate"
        if days_to_due < 0:
            return "Firm Follow-up"
        if days_to_due <= at_risk_days:
            return "At Risk (72h)"
        if days_to_due <= 7:
            return "Reminder"
        return "On Track"

    work["_bucket"] = work["_days_to_due"].apply(_bucket)

    # Supplier-level summary
    grp = (
        work.groupby(["supplier_name", "_bucket"])
        .size()
        .reset_index(name="open_lines")
    )

    pivot = grp.pivot_table(
        index="supplier_name",
        columns="_bucket",
        values="open_lines",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    # Ensure consistent columns
    wanted = ["Escalate", "Firm Follow-up", "At Risk (72h)", "Reminder", "On Track", "Unknown"]
    for c in wanted:
        if c not in pivot.columns:
            pivot[c] = 0

    pivot["open_lines_total"] = pivot[wanted].sum(axis=1)

    # Worst escalation label per supplier
    def _worst(row) -> str:
        if int(row.get("Escalate", 0)) > 0:
            return "Escalate"
        if int(row.get("Firm Follow-up", 0)) > 0:
            return "Firm Follow-up"
        if int(row.get("At Risk (72h)", 0)) > 0:
            return "At Risk (72h)"
        if int(row.get("Reminder", 0)) > 0:
            return "Reminder"
        if int(row.get("On Track", 0)) > 0:
            return "On Track"
        return "Unknown"

    pivot["worst_escalation"] = pivot.apply(_worst, axis=1)

    # Order suppliers by worst escalation then volume
    rank = {"Escalate": 5, "Firm Follow-up": 4, "At Risk (72h)": 3, "Reminder": 2, "On Track": 1, "Unknown": 0}
    pivot["_rank"] = pivot["worst_escalation"].map(rank).fillna(0)
    pivot = pivot.sort_values(["_rank", "open_lines_total"], ascending=[False, False]).drop(columns=["_rank"])

    escalations_df = pivot[
        ["supplier_name", "worst_escalation", "open_lines_total"]
        + [c for c in wanted if c in pivot.columns]
    ].copy()

    # Annotate followups with escalation status
    updated_fu = fu.copy()
    if not updated_fu.empty and "supplier_name" in updated_fu.columns:
        updated_fu = updated_fu.merge(
            escalations_df[["supplier_name", "worst_escalation"]],
            on="supplier_name",
            how="left",
        )
        updated_fu["worst_escalation"] = updated_fu["worst_escalation"].fillna("On Track")

    return escalations_df, updated_fu
