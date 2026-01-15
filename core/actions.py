# core/actions.py
import pandas as pd


def _series(df: pd.DataFrame, col: str, default: str = "") -> pd.Series:
    """
    Safe column getter that ALWAYS returns a Series aligned to df length.
    """
    if df is None or df.empty:
        return pd.Series([], dtype="object")
    if col in df.columns:
        return df[col].astype(str).fillna("")
    return pd.Series([default] * len(df), index=df.index, dtype="object")


def build_daily_action_list(
    exceptions: pd.DataFrame,
    followups: pd.DataFrame,
    max_items: int = 10,
) -> dict:
    """
    Returns a dict of action lists.
    Output keys:
      - customer_actions (DataFrame)
      - supplier_actions (DataFrame)
      - watchlist (DataFrame)
      - summary (dict)
    """
    exc = exceptions.copy() if exceptions is not None else pd.DataFrame()
    fu = followups.copy() if followups is not None else pd.DataFrame()

    # ---------- Customer actions (from exceptions) ----------
    customer_actions = pd.DataFrame()

    if exc is not None and not exc.empty:
        issue_type = _series(exc, "issue_type")
        explanation = _series(exc, "explanation")
        next_action = _series(exc, "next_action")
        line_status = _series(exc, "line_status")
        urgency = _series(exc, "Urgency")  # safe even if missing

        blob = (issue_type + " " + explanation + " " + next_action + " " + line_status).str.lower()

        is_urgent = urgency.isin(["Critical", "High"])
        is_customer_pain = blob.str.contains(
            "late|overdue|past due|missing tracking|no tracking|exception|lost|stuck|returned",
            regex=True,
            na=False,
        )

        customer_actions = exc[is_urgent | is_customer_pain].copy()

        keep = [c for c in [
            "Urgency", "order_id", "sku", "supplier_name", "customer_country",
            "issue_type", "line_status", "explanation", "next_action", "customer_risk"
        ] if c in customer_actions.columns]

        if keep:
            customer_actions = customer_actions[keep]

        # best-effort sort
        sort_cols = [c for c in ["Urgency", "customer_risk", "order_id"] if c in customer_actions.columns]
        if sort_cols:
            customer_actions = customer_actions.sort_values(sort_cols, ascending=True)

        customer_actions = customer_actions.head(int(max_items))

    # ---------- Supplier actions (from followups) ----------
    supplier_actions = pd.DataFrame()

    if fu is not None and not fu.empty:
        keep = [c for c in ["supplier_name", "supplier_email", "item_count", "order_ids", "urgency", "worst_escalation", "subject"] if c in fu.columns]
        supplier_actions = fu[keep].copy() if keep else fu.copy()

        # sort: item_count desc if exists
        if "item_count" in supplier_actions.columns:
            try:
                supplier_actions["_ic"] = pd.to_numeric(supplier_actions["item_count"], errors="coerce").fillna(0)
                supplier_actions = supplier_actions.sort_values("_ic", ascending=False).drop(columns=["_ic"])
            except Exception:
                pass

        # If SLA escalation exists, push worse escalations to top
        if "worst_escalation" in supplier_actions.columns:
            rank = {"Escalate": 4, "Firm Follow-up": 3, "Reminder": 2, "At Risk (72h)": 1, "On Track": 0}
            try:
                supplier_actions["_er"] = supplier_actions["worst_escalation"].astype(str).map(rank).fillna(0)
                supplier_actions = supplier_actions.sort_values(["_er"], ascending=False).drop(columns=["_er"])
            except Exception:
                pass

        supplier_actions = supplier_actions.head(int(max_items))

    # ---------- Watchlist (medium urgency exceptions) ----------
    watchlist = pd.DataFrame()
    if exc is not None and not exc.empty:
        urgency = _series(exc, "Urgency")
        watch_mask = urgency.isin(["Medium"])
        watchlist = exc[watch_mask].copy()

        keep = [c for c in [
            "Urgency", "order_id", "sku", "supplier_name",
            "issue_type", "line_status", "next_action"
        ] if c in watchlist.columns]

        if keep:
            watchlist = watchlist[keep]

        watchlist = watchlist.head(int(max_items))

    # ---------- Summary ----------
    summary = {
        "customer_actions": int(len(customer_actions)) if customer_actions is not None else 0,
        "supplier_actions": int(len(supplier_actions)) if supplier_actions is not None else 0,
        "watchlist": int(len(watchlist)) if watchlist is not None else 0,
    }

    return {
        "customer_actions": customer_actions,
        "supplier_actions": supplier_actions,
        "watchlist": watchlist,
        "summary": summary,
    }
