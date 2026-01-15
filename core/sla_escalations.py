# core/sla_escalations.py
from __future__ import annotations

import pandas as pd
from datetime import datetime


# ----------------------------
# Helpers
# ----------------------------
def _to_dt(series) -> pd.Series:
    try:
        return pd.to_datetime(series, errors="coerce")
    except Exception:
        return pd.Series([pd.NaT] * len(series))


def _now() -> pd.Timestamp:
    # Use local naive timestamp (works fine for relative “days past due”)
    return pd.Timestamp(datetime.now())


def _pick_first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _normalize_status(s: str) -> str:
    return (s or "").strip().lower()


def _escalation_level(days_past_due: float, days_to_due: float) -> str:
    """
    days_past_due > 0 means overdue.
    days_to_due >= 0 means not overdue.
    """
    # Overdue buckets
    if days_past_due > 3:
        return "Escalate"
    if days_past_due > 1:
        return "Firm Follow-up"
    if days_past_due > 0:
        return "Reminder"

    # Not overdue yet: "at risk" window
    if days_to_due <= 3:
        return "At Risk (72h)"
    return "On Track"


def draft_escalation_email(
    supplier_name: str,
    level: str,
    order_ids: list[str],
    sku_count: int,
    max_days_past_due: float,
    max_days_to_due: float,
) -> tuple[str, str]:
    """
    Returns (subject, body). Keep it blunt + usable.
    """
    supplier_name = (supplier_name or "").strip() or "Supplier"
    order_blob = ", ".join([str(o) for o in order_ids[:10] if str(o).strip()])
    if len(order_ids) > 10:
        order_blob += f" (+{len(order_ids) - 10} more)"

    base_subject = "Action required: outstanding shipments"

    if level == "At Risk (72h)":
        subject = f"{base_subject} — confirm ship date/tracking (due soon)"
        body = (
            f"Hi {supplier_name},\n\n"
            f"We have {sku_count} item(s) across order(s): {order_blob} that are coming due within ~{max_days_to_due:.1f} day(s).\n"
            "Can you confirm:\n"
            "1) Ship date, and\n"
            "2) Tracking number(s) as soon as available?\n\n"
            "Thanks,\n"
        )
        return subject, body

    if level == "Reminder":
        subject = f"{base_subject} — quick check-in"
        body = (
            f"Hi {supplier_name},\n\n"
            f"Quick check-in on {sku_count} item(s) across order(s): {order_blob}.\n"
            f"These appear overdue by ~{max_days_past_due:.1f} day(s). Please confirm ship date + tracking.\n\n"
            "Thank you,\n"
        )
        return subject, body

    if level == "Firm Follow-up":
        subject = f"{base_subject} — tracking/ship date needed today"
        body = (
            f"Hi {supplier_name},\n\n"
            f"We still need tracking or an updated ship date for {sku_count} item(s) across order(s): {order_blob}.\n"
            f"These are overdue by up to ~{max_days_past_due:.1f} day(s).\n\n"
            "Please reply today with either:\n"
            "1) Tracking number(s), or\n"
            "2) Confirmed ship date (with reason for delay)\n\n"
            "Thanks,\n"
        )
        return subject, body

    if level == "Escalate":
        subject = f"{base_subject} — escalation: SLA breach"
        body = (
            f"Hi {supplier_name},\n\n"
            f"These shipments are now beyond SLA. We need tracking or a confirmed ship date immediately for "
            f"{sku_count} item(s) across order(s): {order_blob}.\n"
            f"Overdue by up to ~{max_days_past_due:.1f} day(s).\n\n"
            "If we do not receive an update within 24 hours, we will need to re-route fulfillment or cancel/replace.\n\n"
            "Please respond ASAP.\n"
        )
        return subject, body

    # On Track fallback
    return base_subject, (
        f"Hi {supplier_name},\n\n"
        f"Just confirming status for {sku_count} item(s) across order(s): {order_blob}.\n"
        "Please share ship date + tracking when available.\n\n"
        "Thanks,\n"
    )


# ----------------------------
# Main builder
# ----------------------------
def build_sla_escalations(
    line_status_df: pd.DataFrame,
    followups: pd.DataFrame,
    promised_ship_days: int = 3,
    grace_days: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
      - escalations_df: per-supplier summary of unshipped lines that are at-risk / overdue
      - updated_followups: followups merged with worst_escalation + suggested subject/body (does not overwrite unless caller chooses)
    """
    if line_status_df is None or line_status_df.empty:
        return pd.DataFrame(), followups

    df = line_status_df.copy()

    # Required: supplier_name
    if "supplier_name" not in df.columns:
        return pd.DataFrame(), followups

    df["supplier_name"] = df["supplier_name"].fillna("").astype(str)
    df = df[df["supplier_name"].str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame(), followups

    # Determine date basis:
    # Prefer promised_ship_date if present, else created/order date + promised_ship_days
    promised_col = _pick_first_col(df, ["promised_ship_date", "promised_ship_at", "sla_due_date", "ship_by_date"])
    created_col = _pick_first_col(df, ["order_created_at", "order_date", "created_at", "order_created", "order_created_datetime"])

    now = _now()

    if promised_col:
        df["_due_dt"] = _to_dt(df[promised_col])
    elif created_col:
        df["_created_dt"] = _to_dt(df[created_col])
        df["_due_dt"] = df["_created_dt"] + pd.to_timedelta(int(promised_ship_days) + int(grace_days), unit="D")
    else:
        # Can't compute anything useful without any date
        return pd.DataFrame(), followups

    # Identify shipped/delivered vs unshipped
    status_col = _pick_first_col(df, ["line_status", "status", "shipment_status"])
    if status_col:
        s = df[status_col].astype(str).map(_normalize_status)
        is_done = s.str.contains("delivered|shipped", regex=True, na=False)
    else:
        # If no status column, assume not done (conservative)
        is_done = pd.Series([False] * len(df))

    is_unshipped = ~is_done

    # Days to due / past due
    df["_days_to_due"] = (df["_due_dt"] - now).dt.total_seconds() / 86400.0
    df["_days_past_due"] = (now - df["_due_dt"]).dt.total_seconds() / 86400.0

    # Only meaningful for unshipped lines
    df["_days_past_due"] = df["_days_past_due"].where(is_unshipped, 0).fillna(0)
    df["_days_to_due"] = df["_days_to_due"].where(is_unshipped, 9999).fillna(9999)

    df["escalation_level"] = df.apply(
        lambda r: _escalation_level(float(r.get("_days_past_due", 0)), float(r.get("_days_to_due", 9999))),
        axis=1,
    )

    # Build per-supplier rollup on unshipped only
    order_col = "order_id" if "order_id" in df.columns else None
    sku_col = "sku" if "sku" in df.columns else None

    level_rank = {"Escalate": 4, "Firm Follow-up": 3, "Reminder": 2, "At Risk (72h)": 1, "On Track": 0}

    rows = []
    for supplier, g in df[is_unshipped].groupby("supplier_name"):
        if g.empty:
            continue

        levels = g["escalation_level"].astype(str).unique().tolist()
        worst_level = sorted(levels, key=lambda x: level_rank.get(x, 0), reverse=True)[0]

        max_past = float(pd.to_numeric(g["_days_past_due"], errors="coerce").fillna(0).max())
        min_to_due = float(pd.to_numeric(g["_days_to_due"], errors="coerce").fillna(9999).min())
        max_to_due = float(pd.to_numeric(g["_days_to_due"], errors="coerce").fillna(9999).max())

        order_ids = []
        if order_col:
            order_ids = [str(v) for v in g[order_col].dropna().unique().tolist() if str(v).strip() != ""]

        sku_count = int(g[sku_col].dropna().nunique()) if sku_col else int(len(g))

        subject_suggested, body_suggested = draft_escalation_email(
            supplier_name=supplier,
            level=worst_level,
            order_ids=order_ids,
            sku_count=sku_count,
            max_days_past_due=max_past,
            max_days_to_due=min_to_due,
        )

        rows.append(
            {
                "supplier_name": supplier,
                "unshipped_lines": int(len(g)),
                "sku_count": sku_count,
                "order_count": int(len(order_ids)),
                "worst_escalation": worst_level,
                "max_days_past_due": round(max_past, 2),
                "min_days_to_due": round(min_to_due, 2),
                "max_days_to_due": round(max_to_due, 2),
                "subject_suggested": subject_suggested,
                "body_suggested": body_suggested,
            }
        )

    escalations = pd.DataFrame(rows)
    if escalations.empty:
        return escalations, followups

    escalations["_rank"] = escalations["worst_escalation"].map(level_rank).fillna(0).astype(int)
    escalations = escalations.sort_values(["_rank", "max_days_past_due", "unshipped_lines"], ascending=[False, False, False]).drop(columns=["_rank"])

    # Merge escalation summary onto followups (non-destructive; caller can choose to overwrite subject/body)
    updated_followups = followups
    if followups is not None and not followups.empty and "supplier_name" in followups.columns:
        f = followups.copy()
        f = f.merge(
            escalations[["supplier_name", "worst_escalation", "max_days_past_due", "min_days_to_due", "subject_suggested", "body_suggested"]],
            on="supplier_name",
            how="left",
        )
        updated_followups = f

    return escalations, updated_followups
