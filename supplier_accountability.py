# core/supplier_accountability.py
import pandas as pd


def _safe_s(x) -> str:
    return "" if x is None else str(x)


def build_supplier_accountability_view(
    scorecard: pd.DataFrame | None = None,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Returns a ranked supplier table designed for accountability conversations.
    Expected scorecard cols (best-effort):
      supplier_name, total_lines, exception_lines, exception_rate, critical, high,
      missing_tracking_flags, late_flags, carrier_exception_flags
    """
    if scorecard is None or not isinstance(scorecard, pd.DataFrame) or scorecard.empty:
        return pd.DataFrame()

    df = scorecard.copy()

    # Ensure numeric
    for c in [
        "total_lines",
        "exception_lines",
        "exception_rate",
        "critical",
        "high",
        "missing_tracking_flags",
        "late_flags",
        "carrier_exception_flags",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # A simple weighted pain score
    df["pain_score"] = (
        df.get("critical", 0) * 5
        + df.get("high", 0) * 2
        + df.get("missing_tracking_flags", 0) * 2
        + df.get("late_flags", 0) * 1.5
        + df.get("carrier_exception_flags", 0) * 2
        + (df.get("exception_rate", 0) * 10)
    ).round(2)

    cols = [
        "supplier_name",
        "pain_score",
        "total_lines",
        "exception_lines",
        "exception_rate",
        "critical",
        "high",
        "missing_tracking_flags",
        "late_flags",
        "carrier_exception_flags",
    ]
    cols = [c for c in cols if c in df.columns]

    out = df[cols].sort_values(["pain_score", "exception_lines"], ascending=False).head(int(top_n))
    return out


# -------------------------------------------------------------------
# ✅ Compatibility wrapper: allows app.py to call with many possible kwargs
# (e.g., exceptions=..., followups=..., escalations_df=..., etc.)
# and it will still work by extracting/using only what we need (scorecard).
# -------------------------------------------------------------------
def build_supplier_accountability_view_compat(*args, **kwargs) -> pd.DataFrame:
    """
    Accepts many possible argument styles and routes to build_supplier_accountability_view.

    Supported calling patterns:
      - build_supplier_accountability_view_compat(scorecard_df, top_n=10)
      - build_supplier_accountability_view_compat(scorecard=scorecard_df, top_n=10)
      - build_supplier_accountability_view_compat(..., scorecard_df passed as first positional)
    """
    # 1) if explicitly provided
    scorecard = kwargs.get("scorecard", None)

    # 2) if passed positionally
    if scorecard is None and len(args) > 0:
        if isinstance(args[0], pd.DataFrame):
            scorecard = args[0]

    # 3) top_n
    top_n = kwargs.get("top_n", 10)

    return build_supplier_accountability_view(scorecard=scorecard, top_n=int(top_n))


def draft_supplier_performance_note(row: dict) -> dict:
    """
    Returns dict with subject/body you can paste into a supplier email.
    """
    sname = _safe_s(row.get("supplier_name", "")).strip() or "Supplier"
    total_lines = int(float(row.get("total_lines", 0) or 0))
    exception_lines = int(float(row.get("exception_lines", 0) or 0))
    exception_rate = float(row.get("exception_rate", 0) or 0)

    critical = int(float(row.get("critical", 0) or 0))
    high = int(float(row.get("high", 0) or 0))
    mt = int(float(row.get("missing_tracking_flags", 0) or 0))
    late = int(float(row.get("late_flags", 0) or 0))
    ce = int(float(row.get("carrier_exception_flags", 0) or 0))

    subject = f"Performance follow-up: tracking + ship updates needed ({sname})"

    body = (
        f"Hi {sname},\n\n"
        "We are seeing a higher-than-normal number of shipment issues tied to recent orders.\n\n"
        f"Summary (current run):\n"
        f"- Total order lines: {total_lines}\n"
        f"- Lines with issues: {exception_lines} (exception rate: {exception_rate:.2%})\n"
        f"- Critical: {critical} | High: {high}\n"
        f"- Missing/invalid tracking flags: {mt}\n"
        f"- Late/unshipped flags: {late}\n"
        f"- Carrier exception flags: {ce}\n\n"
        "Requested actions:\n"
        "1) Provide tracking numbers for any shipped orders missing tracking.\n"
        "2) Provide updated ship dates for any unshipped orders.\n"
        "3) Confirm corrective steps to reduce late shipments going forward.\n\n"
        "Thank you,\n"
    )

    return {"subject": subject, "body": body}
