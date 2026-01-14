# core/sla_escalations.py
from __future__ import annotations
import pandas as pd
from datetime import datetime, timezone


def _to_dt(x):
    try:
        return pd.to_datetime(x, errors="coerce", utc=True)
    except Exception:
        return pd.NaT


def _now_utc():
    return pd.Timestamp(datetime.now(timezone.utc))


def _normalize_status(s: str) -> str:
    s = (s or "").strip().lower()
    return s


def _build_email(subject_base: str, tone: str, supplier_name: str, order_ids: list[str], sku_count: int) -> tuple[str, str]:
    order_blob = ", ".join([o for o in order_ids if str(o).strip()][:10])
    if len(order_ids) > 10:
        order_blob += f" (+{len(order_ids)-10} more)"

    if tone == "reminder":
        subject = f"{subject_base} — quick check-in"
        body = (
            f"Hi {supplier_name},\n\n"
            f"Quick check-in on {sku_count} item(s) across order(s): {order_blob}.\n"
            "Can you confirm ship date + tracking as soon as available?\n\n"
            "Thank you,\n"
        )
    elif tone == "firm":
        subject = f"{subject_base} — tracking/ship date needed today"
        body = (
            f"Hi {supplier_name},\n\n"
            f"We still need an updated ship date and tracking for {sku_count} item(s) "
            f"across order(s): {order_blob}.\n"
            "Please reply today with either:\n"
            "1) Tracking number(s), or\n"
            "2) Confirmed ship date (with reason for delay)\n\n"
            "Thanks,\n"
        )
    else:  # escalate
        subject = f"{subject_base} — escalation: SLA breach"
        body = (
            f"Hi {supplier_name},\n\n"
            f"These shipments are now beyond SLA. We need tracking or a confirmed ship date immediately "
            f"for {sku_count} item(s) across order(s): {order_blob}.\n\n"
            "If we do not receive an update within 24 hours, we will need to:\n"
            "- re-route fulfillment, or\n"
            "- cancel/replace inventory depending on availability.\n\n"
            "Please respond ASAP.\n"
        )

    return subject, body


def build_sla_escalations(
    line_status_df: pd.DataFrame,
    followups: pd.DataFrame,
    promised_ship_days: int = 3,
    grace_days: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
      (escalations_table, updated_followups)

    escalations_table: one row per supplier with escalation level + counts + suggested comms.
    updated_followups: followups with escalation columns injected (subject/body can be replaced when escalation is higher).
    """
    if line_status_df is None or line_status_df.empty:
        return pd.DataFrame(), followups

    df = line_status_df.copy()

    # Expected columns (best-effort)
    # We'll try common names: order_created_at / order_date / created_at
    created_col = None
    for c in ["order_created_at", "order_date", "created_at", "order_created", "order_created_datetime"]:
        if c in df.columns:
            created_col = c
            break

    if created_col is None or "supplier_name" not in df.columns:
        return pd.DataFrame(), followups

    df["supplier_name"] = df["supplier_name"].fillna("").astype(str)
    df = df[df["supplier_name"].str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame(), followups

    df["_created_dt"] = _to_dt(df[created_col])
    now = _now_utc()

    # Compute SLA due date
    sla_days = int(promised_ship_days) + int(grace_days)
    df["_sla_due"] = df["_created_dt"] + pd.to_timedelta(sla_days, unit="D")

    # shipped/delivered detection
    status_col = None
    for c in ["line_status", "status", "shipment_status"]:
        if c in df.columns:
            status_col = c
            break

    if status_col is None:
        df["_status_norm"] = ""
    else:
        df["_status_norm"] = df[status_col].astype(str).map(_normalize_status)

    is_done = df["_status_norm"].str.contains("delivered|shipped", regex=True, na=False)
    is_unshipped = ~is_done

    # Days late (only if unshipped)
    df["_days_past_due"] = (now - df["_sla_due"]).dt.total_seconds() / 86400.0
    df["_days_past_due"] = df["_days_past_due"].where(is_unshipped, 0)
    df["_days_past_due"] = df["_days_past_due"].fillna(0)

    # Escalation bands
    #  <=0 : On Track
    #  0-1 : Reminder
    #  1-3 : Firm
    #  >3  : Escalate
    def _level(d):
        if d <= 0:
            return "On Track"
        if d <= 1:
            return "Reminder"
        if d <= 3:
            return "Firm Follow-up"
        return "Escalate"

    df["escalation_level"] = df["_days_past_due"].apply(_level)

    # Order IDs and SKU counts
    order_col = "order_id" if "order_id" in df.columns else None
    sku_col = "sku" if "sku" in df.columns else None

    def _safe_list(x):
        if x is None:
            return []
        return [str(v) for v in x if str(v).strip() != ""]

    rows = []
    for supplier, g in df[is_unshipped].groupby("supplier_name"):
        if g.empty:
            continue

        # worst level wins
        level_rank = {"On Track": 0, "Reminder": 1, "Firm Follow-up": 2, "Escalate": 3}
        worst_level = sorted(g["escalation_level"].unique().tolist(), key=lambda x: level_rank.get(x, 0))[-1]

        order_ids = _safe_list(g[order_col].dropna().unique().tolist()) if order_col else []
        sku_count = int(g[sku_col].dropna().nunique()) if sku_col else int(len(g))

        subject_base = "Action required: outstanding shipments"
        tone = "reminder" if worst_level == "Reminder" else ("firm" if worst_level == "Firm Follow-up" else "escalate")
        subj, body = _build_email(subject_base, tone, supplier, order_ids, sku_count)

        rows.append(
            {
                "supplier_name": supplier,
                "unshipped_lines": int(len(g)),
                "sku_count": sku_count,
                "order_count": int(len(order_ids)) if order_ids else None,
                "worst_escalation": worst_level,
                "max_days_past_due": float(g["_days_past_due"].max()) if "_days_past_due" in g.columns else None,
                "subject_suggested": subj,
                "body_suggested": body,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out, followups

    out = out.sort_values(
        ["worst_escalation", "max_days_past_due", "unshipped_lines"],
        ascending=[False, False, False],
    )

    # Enrich followups if possible
    updated_followups = followups
    if followups is not None and not followups.empty and "supplier_name" in followups.columns:
        f = followups.copy()
        f = f.merge(
            out[["supplier_name", "worst_escalation", "subject_suggested", "body_suggested"]],
            on="supplier_name",
            how="left",
        )
        # If escalation is higher than normal, override subject/body
        if "subject" in f.columns:
            f["subject"] = f["subject"].where(f["worst_escalation"].isna(), f["subject_suggested"].fillna(f["subject"]))
        else:
            f["subject"] = f["subject_suggested"].fillna("Action required: outstanding shipments")

        if "body" in f.columns:
            f["body"] = f["body"].where(f["worst_escalation"].isna(), f["body_suggested"].fillna(f["body"]))
        else:
            f["body"] = f["body_suggested"].fillna("")

        # cleanup
        f = f.drop(columns=[c for c in ["subject_suggested", "body_suggested"] if c in f.columns])
        updated_followups = f

    return out, updated_followups
