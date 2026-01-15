# core/customer_comms.py
from __future__ import annotations

import pandas as pd


def _pick(col_candidates: list[str], df: pd.DataFrame) -> str | None:
    for c in col_candidates:
        if df is not None and not df.empty and c in df.columns:
            return c
    return None


def build_customer_email_queue(
    exceptions: pd.DataFrame,
    order_rollup: pd.DataFrame | None = None,
    max_items: int = 50,
) -> pd.DataFrame:
    """
    Build a customer email queue from exceptions (SKU-level).
    Best-effort: merges customer email/name from order_rollup if possible.

    Output columns:
      - order_id
      - customer_email
      - template_type
      - subject
      - body
      - customer_risk
      - issue_type
      - supplier_name
    """
    exc = exceptions.copy() if exceptions is not None else pd.DataFrame()
    if exc.empty:
        return pd.DataFrame(columns=[
            "order_id", "customer_email", "template_type", "subject", "body",
            "customer_risk", "issue_type", "supplier_name"
        ])

    # prefer order id column names
    order_col = _pick(["order_id", "Order ID", "order_number"], exc) or "order_id"
    if order_col not in exc.columns:
        exc[order_col] = ""

    # collapse to order-level: choose the “worst” risk if present
    risk_col = _pick(["customer_risk", "risk", "Customer Risk"], exc)
    issue_col = _pick(["issue_type", "Issue Type"], exc)
    supplier_col = _pick(["supplier_name", "Supplier"], exc)

    if risk_col is None:
        exc["_risk_rank"] = 0
    else:
        r = exc[risk_col].fillna("").astype(str).str.lower()
        exc["_risk_rank"] = r.map({
            "critical": 4, "high": 3, "medium": 2, "low": 1
        }).fillna(0).astype(int)

    # create a compact “issue type” summary at order-level
    def _agg_issue_types(s: pd.Series) -> str:
        vals = s.dropna().astype(str).tolist()
        vals = [v.strip() for v in vals if v.strip()]
        uniq = []
        for v in vals:
            if v not in uniq:
                uniq.append(v)
        return ", ".join(uniq[:3])

    grp_cols = [order_col]
    agg = {
        "_risk_rank": "max",
    }
    if risk_col:
        agg[risk_col] = lambda x: _agg_issue_types(x) if False else (x.dropna().astype(str).iloc[0] if len(x.dropna()) else "")
    if issue_col:
        agg[issue_col] = _agg_issue_types
    if supplier_col:
        agg[supplier_col] = lambda x: _agg_issue_types(x)

    order_view = exc.groupby(grp_cols, dropna=False).agg(agg).reset_index()

    # Merge customer email from rollup (if possible)
    order_view["customer_email"] = ""
    if order_rollup is not None and isinstance(order_rollup, pd.DataFrame) and not order_rollup.empty:
        roll = order_rollup.copy()
        roll_order_col = _pick(["order_id", "Order ID", "order_number"], roll)
        email_col = _pick(["customer_email", "email", "Email"], roll)
        if roll_order_col and email_col:
            roll2 = roll[[roll_order_col, email_col]].copy()
            roll2[roll_order_col] = roll2[roll_order_col].astype(str)
            roll2[email_col] = roll2[email_col].fillna("").astype(str)
            roll2 = roll2.drop_duplicates(subset=[roll_order_col])
            order_view[order_col] = order_view[order_col].astype(str)
            order_view = order_view.merge(
                roll2.rename(columns={roll_order_col: order_col, email_col: "customer_email"}),
                on=order_col,
                how="left",
                suffixes=("", "_r"),
            )
            order_view["customer_email"] = order_view["customer_email"].fillna("").astype(str)

    # Determine template type heuristically
    blob = (
        order_view.get(issue_col, pd.Series([""] * len(order_view))).fillna("").astype(str) + " " +
        order_view.get(supplier_col, pd.Series([""] * len(order_view))).fillna("").astype(str)
    ).str.lower()

    def _template(b: str) -> str:
        if "missing tracking" in b or "no tracking" in b or "tracking" in b:
            return "tracking_update"
        if "late" in b or "overdue" in b or "past due" in b or "unshipped" in b:
            return "delay_update"
        if "carrier exception" in b or "returned" in b or "lost" in b or "stuck" in b:
            return "carrier_exception"
        return "general_update"

    order_view["template_type"] = blob.apply(_template)

    # Customer risk label
    def _risk_label(rank: int) -> str:
        if rank >= 4:
            return "Critical"
        if rank == 3:
            return "High"
        if rank == 2:
            return "Medium"
        if rank == 1:
            return "Low"
        return "Low"

    order_view["customer_risk"] = order_view["_risk_rank"].apply(_risk_label)

    # Generate subject/body
    def _subject(row) -> str:
        oid = str(row.get(order_col, "")).strip()
        t = row.get("template_type", "general_update")
        if t == "tracking_update":
            return f"Update on your order {oid}: tracking details"
        if t == "delay_update":
            return f"Update on your order {oid}: shipping delay"
        if t == "carrier_exception":
            return f"Update on your order {oid}: delivery issue"
        return f"Update on your order {oid}"

    def _body(row) -> str:
        oid = str(row.get(order_col, "")).strip()
        t = row.get("template_type", "general_update")
        risk = str(row.get("customer_risk", "")).strip()
        issue_summary = str(row.get(issue_col, "")).strip() if issue_col else ""
        supplier = str(row.get(supplier_col, "")).strip() if supplier_col else ""

        lines = []
        lines.append("Hi there,")
        lines.append("")
        if t == "tracking_update":
            lines.append(f"We’re following up on your order **{oid}** to confirm tracking details.")
        elif t == "delay_update":
            lines.append(f"We’re reaching out with an update on your order **{oid}** — it’s taking longer than expected to ship.")
        elif t == "carrier_exception":
            lines.append(f"We’re reaching out with an update on your order **{oid}** — there may be a carrier/delivery issue.")
        else:
            lines.append(f"We’re reaching out with an update on your order **{oid}**.")

        if issue_summary:
            lines.append(f"Internal note: {issue_summary}")
        if supplier:
            lines.append(f"Supplier: {supplier}")
        if risk:
            lines.append(f"Priority: {risk}")

        lines.append("")
        lines.append("Here’s what’s happening and what we’re doing next:")
        lines.append("• We’re contacting the supplier/carrier to confirm the latest status and next scan/ship date.")
        lines.append("• As soon as we have tracking or an updated ETA, we’ll send it immediately.")
        lines.append("• If the item can’t be fulfilled in time, we’ll offer the best available resolution (replacement/refund).")
        lines.append("")
        lines.append("Thanks for your patience — we’re on it and will keep you updated.")
        lines.append("")
        lines.append("Best,")
        lines.append("")

        return "\n".join(lines)

    order_view["subject"] = order_view.apply(_subject, axis=1)
    order_view["body"] = order_view.apply(_body, axis=1)

    # normalize column names in output
    out = order_view.rename(columns={order_col: "order_id"}).copy()
    # keep only expected columns + useful context
    keep = [
        "order_id",
        "customer_email",
        "template_type",
        "subject",
        "body",
        "customer_risk",
    ]
    if issue_col and issue_col in out.columns:
        keep.append(issue_col)
    if supplier_col and supplier_col in out.columns:
        keep.append(supplier_col)

    out = out[keep].copy()

    # sort and limit
    out["_risk_rank"] = order_view["_risk_rank"].values
    out = out.sort_values(["_risk_rank", "order_id"], ascending=[False, True]).drop(columns=["_risk_rank"])
    return out.head(int(max_items))
