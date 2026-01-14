# core/customer_impact.py
import pandas as pd


def _safe_s(x) -> str:
    return "" if x is None else str(x)


def _classify_customer_impact(row: dict) -> tuple[str, str]:
    """
    Returns (impact_category, recommended_action)
    """
    issue_type = _safe_s(row.get("issue_type", "")).lower()
    explanation = _safe_s(row.get("explanation", "")).lower()
    next_action = _safe_s(row.get("next_action", "")).lower()
    line_status = _safe_s(row.get("line_status", "")).lower()
    urgency = _safe_s(row.get("Urgency", "")).lower()

    blob = " ".join([issue_type, explanation, next_action, line_status, urgency])

    if any(t in blob for t in ["missing tracking", "no tracking", "tracking missing", "invalid tracking"]):
        return ("No tracking", "Proactively email customer (set expectation)")

    if any(t in blob for t in ["carrier exception", "exception", "stuck", "lost", "returned to sender", "seized"]):
        return ("Carrier exception", "Proactively email customer + investigate")

    if any(t in blob for t in ["partial", "partial shipment", "quantity mismatch"]):
        return ("Partial shipment", "Email customer (split shipment notice)")

    if any(t in blob for t in ["late unshipped", "overdue", "past due", "late"]):
        return ("Late risk", "Proactively email customer (delay notice)")

    if "critical" in urgency:
        return ("High risk", "Proactively email customer")
    if "high" in urgency:
        return ("Moderate risk", "Email customer if no update in 24h")

    return ("Low risk", "Monitor")


def _draft_customer_message(row: dict, impact_category: str) -> str:
    order_id = _safe_s(row.get("order_id", "")).strip()
    sku = _safe_s(row.get("sku", "")).strip()
    supplier = _safe_s(row.get("supplier_name", "")).strip()
    action = _safe_s(row.get("next_action", "")).strip()

    order_ref = f"Order {order_id}" if order_id else "your order"
    sku_part = f" (item: {sku})" if sku else ""

    if impact_category == "No tracking":
        return (
            f"Hi there - quick update on {order_ref}{sku_part}. "
            "We are still waiting on tracking details from our shipping partner. "
            "As soon as tracking is available, we will send it right away. "
            "Thanks for your patience!"
        )

    if impact_category == "Carrier exception":
        return (
            f"Hi there - an update on {order_ref}{sku_part}. "
            "The carrier is showing an exception while in transit. "
            "We are actively investigating and will follow up with the next update ASAP. "
            "If you would like, we can also offer alternative resolution options."
        )

    if impact_category == "Partial shipment":
        return (
            f"Hi there - update on {order_ref}{sku_part}. "
            "Your order may arrive in multiple packages due to fulfillment timing. "
            "We will send tracking for each package as it becomes available. "
            "Thanks for your patience!"
        )

    if impact_category == "Late risk":
        extra = f" Next step: {action}" if action else ""
        supplier_bit = f" (supplier: {supplier})" if supplier else ""
        return (
            f"Hi there - quick update on {order_ref}{sku_part}. "
            "Your shipment is taking a bit longer than expected, and we are working to confirm the latest ship/tracking update. "
            f"{supplier_bit}{extra} "
            "We will follow up with the next update as soon as we have it. "
            "Thanks for your patience!"
        )

    return (
        f"Hi there - quick update on {order_ref}{sku_part}. "
        "We are reviewing your shipment status and will share the next update as soon as possible. "
        "Thanks for your patience!"
    )


def build_customer_impact_view(exceptions: pd.DataFrame, max_items: int = 50) -> pd.DataFrame:
    """
    Creates a customer-impact table from exceptions.
    """
    if exceptions is None or exceptions.empty:
        return pd.DataFrame()

    df = exceptions.copy()

    blob = (
        df.get("issue_type", "").astype(str).fillna("") + " " +
        df.get("explanation", "").astype(str).fillna("") + " " +
        df.get("next_action", "").astype(str).fillna("") + " " +
        df.get("line_status", "").astype(str).fillna("") + " " +
        df.get("Urgency", "").astype(str).fillna("")
    ).str.lower()

    likely_customer_pain = blob.str.contains(
        "late|overdue|past due|late unshipped|missing tracking|no tracking|tracking missing|invalid tracking|"
        "carrier exception|exception|lost|stuck|returned|partial|quantity mismatch",
        regex=True,
        na=False,
    )

    urgent = df.get("Urgency", "").astype(str).isin(["Critical", "High"]) if "Urgency" in df.columns else False
    subset = df[likely_customer_pain | urgent].copy()
    if subset.empty:
        return pd.DataFrame()

    cats, recs, drafts = [], [], []
    for _, r in subset.iterrows():
        cat, rec = _classify_customer_impact(r.to_dict())
        cats.append(cat)
        recs.append(rec)
        drafts.append(_draft_customer_message(r.to_dict(), cat))

    subset["impact_category"] = cats
    subset["recommended_customer_action"] = recs
    subset["customer_message_draft"] = drafts

    preferred = [
        "Urgency",
        "impact_category",
        "recommended_customer_action",
        "order_id",
        "sku",
        "customer_country",
        "supplier_name",
        "issue_type",
        "line_status",
        "customer_risk",
        "next_action",
        "customer_message_draft",
    ]
    show = [c for c in preferred if c in subset.columns]
    out = subset[show].copy()

    if "Urgency" in out.columns:
        order_map = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        u_str = out["Urgency"].astype(str)
        out["_u"] = u_str.map(order_map)
        out["_u"] = pd.to_numeric(out["_u"], errors="coerce").fillna(9).astype(int)

        sort_cols = ["_u", "impact_category"]
        if "order_id" in out.columns:
            sort_cols.append("order_id")

        out = out.sort_values(sort_cols, ascending=True).drop(columns=["_u"], errors="ignore")
    else:
        sort_cols = ["impact_category"]
        if "order_id" in out.columns:
            sort_cols.append("order_id")
        out = out.sort_values(sort_cols, ascending=True)

    return out.head(max_items)
