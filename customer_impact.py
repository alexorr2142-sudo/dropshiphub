# core/customer_impact.py
import pandas as pd


def build_customer_impact_view(exceptions: pd.DataFrame, max_items: int = 50) -> pd.DataFrame:
    """
    Build customer comms candidates from exceptions.
    This is intentionally defensive: it works even if your exceptions schema varies.
    Returns columns like:
      order_id, customer_email, customer_country, worst_urgency, reason
    """
    if exceptions is None or exceptions.empty:
        return pd.DataFrame(columns=["order_id", "customer_email", "customer_country", "worst_urgency", "reason"])

    df = exceptions.copy()

    # Normalize likely columns
    order_col = "order_id" if "order_id" in df.columns else ("order" if "order" in df.columns else None)
    if not order_col:
        # if we can't tie to an order, we still return something
        df["order_id"] = ""
        order_col = "order_id"

    email_col = "customer_email" if "customer_email" in df.columns else ("email" if "email" in df.columns else None)
    if not email_col:
        df["customer_email"] = ""
        email_col = "customer_email"

    country_col = "customer_country" if "customer_country" in df.columns else None
    if not country_col:
        df["customer_country"] = ""
        country_col = "customer_country"

    urg_col = "Urgency" if "Urgency" in df.columns else None
    if not urg_col:
        df["Urgency"] = ""
        urg_col = "Urgency"

    # Build reason text
    def _row_reason(r):
        bits = []
        for c in ["issue_type", "line_status", "explanation", "next_action"]:
            if c in df.columns:
                val = str(r.get(c, "") or "").strip()
                if val:
                    bits.append(val)
        return " | ".join(bits)[:400]

    df["_reason"] = df.apply(_row_reason, axis=1)

    # Worst urgency by category order
    urg_order = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0, "": -1}
    df["_urg_rank"] = df[urg_col].astype(str).map(lambda x: urg_order.get(str(x), -1))

    grp = df.groupby(df[order_col].astype(str), dropna=False)

    rows = []
    for oid, g in grp:
        g = g.copy()
        g = g.sort_values("_urg_rank", ascending=False)

        worst = str(g.iloc[0][urg_col] or "").strip()
        email = str(g.iloc[0][email_col] or "").strip()
        country = str(g.iloc[0][country_col] or "").strip()

        # Compose a concise reason summary from top 3 lines
        reasons = [str(x).strip() for x in g["_reason"].head(3).tolist() if str(x).strip()]
        reason = " / ".join(reasons)[:500]

        rows.append(
            {
                "order_id": str(oid).strip(),
                "customer_email": email,
                "customer_country": country,
                "worst_urgency": worst,
                "reason": reason,
            }
        )

    out = pd.DataFrame(rows)
    # Sort: worst urgency first
    out["_urg_rank"] = out["worst_urgency"].astype(str).map(lambda x: urg_order.get(str(x), -1))
    out = out.sort_values("_urg_rank", ascending=False).drop(columns=["_urg_rank"], errors="ignore")

    return out.head(int(max_items)).reset_index(drop=True)
