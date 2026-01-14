# core/actions.py
import pandas as pd


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
    # Heuristics:
    # - Urgency Critical/High => customer comms candidates
    # - "late", "overdue", "past due", "missing tracking" => customer pain
    customer_actions = pd.DataFrame()
    if not exc.empty:
        blob = (
            exc.get("issue_type", "").astype(str).fillna("") + " " +
            exc.get("explanation", "").astype(str).fillna("") + " " +
            exc.get("next_action", "").astype(str).fillna("") + " " +
            exc.get("line_status", "").astype(str).fillna("")
        ).str.lower()

        is_urgent = exc.get("Urgency", "").astype(str).isin(["Critical", "High"])
        is_customer_pain = blob.str.contains("late|overdue|past due|missing tracking|no tracking|exception|lost|stuck|returned", regex=True, na=False)

        customer_actions = exc[is_urgent | is_customer_pain].copy()

        keep = [c for c in [
            "Urgency", "order_id", "sku", "supplier_name", "customer_country",
            "issue_type", "line_status", "explanation", "next_action", "customer_risk"
        ] if c in customer_actions.columns]

        customer_actions = customer_actions[keep]
        # best-effort sort
        sort_cols = [c for c in ["Urgency", "customer_risk", "order_id"] if c in customer_actions.columns]
        if sort_cols:
            customer_actions = customer_actions.sort_values(sort_cols, ascending=True)

        customer_actions = customer_actions.head(max_items)

    # ---------- Supplier actions (from followups) ----------
    supplier_actions = pd.DataFrame()
    if fu is not None and not fu.empty:
        keep = [c for c in ["supplier_name", "supplier_email", "item_count", "order_ids", "urgency", "subject"] if c in fu.columns]
        supplier_actions = fu[keep].copy()

        # sort: item_count desc if exists
        if "item_count" in supplier_actions.columns:
            try:
                supplier_actions["_ic"] = pd.to_numeric(supplier_actions["item_count"], errors="coerce").fillna(0)
                supplier_actions = supplier_actions.sort_values("_ic", ascending=False).drop(columns=["_ic"])
            except Exception:
                pass

        supplier_actions = supplier_actions.head(max_items)

    # ---------- Watchlist (medium urgency exceptions) ----------
    watchlist = pd.DataFrame()
    if not exc.empty and "Urgency" in exc.columns:
        watchlist = exc[exc["Urgency"].astype(str).isin(["Medium"])].copy()
        keep = [c for c in [
            "Urgency", "order_id", "sku", "supplier_name",
            "issue_type", "line_status", "next_action"
        ] if c in watchlist.columns]
        watchlist = watchlist[keep].head(max_items)

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
