# ui/sla_escalations_ui.py
import pandas as pd
import streamlit as st


def render_sla_escalations(line_status_df: pd.DataFrame, followups: pd.DataFrame, promised_ship_days: int = 3):
    """
    Minimal SLA escalation bucketing:
    - If line_status_df has 'days_past_due' use it.
    - Else if it has 'promised_ship_date' and 'ship_date' derive lateness.
    Returns:
      escalations_df, followups_full_with_worst, followups_open_passthrough
    """
    ls = line_status_df.copy() if isinstance(line_status_df, pd.DataFrame) else pd.DataFrame()
    fu = followups.copy() if isinstance(followups, pd.DataFrame) else pd.DataFrame()

    if ls.empty or "supplier_name" not in ls.columns:
        return pd.DataFrame(), fu, fu

    df = ls.copy()
    df["supplier_name"] = df["supplier_name"].fillna("").astype(str)

    # Determine lateness metric
    if "days_past_due" in df.columns:
        df["_late_days"] = pd.to_numeric(df["days_past_due"], errors="coerce").fillna(0)
    else:
        # best-effort from dates if present
        if "promised_ship_date" in df.columns and "ship_date" in df.columns:
            p = pd.to_datetime(df["promised_ship_date"], errors="coerce")
            s = pd.to_datetime(df["ship_date"], errors="coerce")
            df["_late_days"] = (pd.Timestamp.utcnow().normalize() - p).dt.days
            # if shipped, consider not late
            df.loc[s.notna(), "_late_days"] = 0
            df["_late_days"] = df["_late_days"].fillna(0)
        else:
            df["_late_days"] = 0

    def bucket(d: float) -> str:
        try:
            d = float(d)
        except Exception:
            d = 0
        if d >= 10:
            return "10+ days late"
        if d >= 5:
            return "5–9 days late"
        if d >= 1:
            return "1–4 days late"
        return "On time"

    df["escalation_bucket"] = df["_late_days"].map(bucket)

    esc = (
        df.groupby(["supplier_name", "escalation_bucket"])
        .size()
        .reset_index(name="line_count")
        .sort_values(["line_count"], ascending=False)
    )

    # Supplier worst escalation for merge
    order = {"10+ days late": 3, "5–9 days late": 2, "1–4 days late": 1, "On time": 0}
    tmp = df[["supplier_name", "escalation_bucket"]].copy()
    tmp["_rank"] = tmp["escalation_bucket"].map(lambda x: order.get(x, 0))
    worst = tmp.sort_values("_rank", ascending=False).drop_duplicates("supplier_name")[["supplier_name", "escalation_bucket"]]
    worst = worst.rename(columns={"escalation_bucket": "worst_escalation"})

    if not fu.empty and "supplier_name" in fu.columns:
        out_fu = fu.merge(worst, on="supplier_name", how="left")
        out_fu["worst_escalation"] = out_fu["worst_escalation"].fillna("")
    else:
        out_fu = fu

    # Render quick view (optional)
    with st.expander("SLA escalation details", expanded=False):
        st.dataframe(esc, use_container_width=True, height=240)

    return esc, out_fu, out_fu
