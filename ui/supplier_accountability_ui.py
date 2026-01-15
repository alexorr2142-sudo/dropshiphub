import streamlit as st
import pandas as pd


def render_supplier_accountability(accountability: pd.DataFrame | None):
    """
    Renders supplier accountability in a way that supports BOTH schemas:

    Schema A (older / conversation-style):
      supplier_name, open_issues, critical, high, worst_escalation, next_action, owner, last_contacted

    Schema B (current core/supplier_accountability.py scorecard-based):
      supplier_name, pain_score, total_lines, exception_lines, exception_rate, critical, high,
      missing_tracking_flags, late_flags, carrier_exception_flags
    """
    st.subheader("Supplier Accountability")

    if accountability is None or accountability.empty:
        st.caption("No supplier accountability items available for this run.")
        return

    df = accountability.copy()

    # Choose a preferred column order depending on what exists
    schema_a_preferred = [
        "supplier_name",
        "worst_escalation",
        "open_issues",
        "critical",
        "high",
        "next_action",
        "owner",
        "last_contacted",
    ]

    schema_b_preferred = [
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

    if "pain_score" in df.columns:
        preferred = schema_b_preferred
    else:
        preferred = schema_a_preferred

    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]

    # Filters
    c1, c2, c3 = st.columns(3)
    with c1:
        supplier = st.text_input("Filter supplier (contains)", value="", key="acct_filter_supplier")
    with c2:
        # If open_issues exists, filter on it. Else use exception_lines as the "open issues" proxy.
        if "open_issues" in df.columns:
            min_metric_label = "Min open issues"
            metric_col = "open_issues"
        elif "exception_lines" in df.columns:
            min_metric_label = "Min exception lines"
            metric_col = "exception_lines"
        else:
            min_metric_label = "Min rows (no metric)"
            metric_col = None

        min_open = st.number_input(min_metric_label, min_value=0, value=0, step=1, key="acct_filter_min_open")
    with c3:
        show_top = st.slider("Show top N", min_value=5, max_value=100, value=25, step=5, key="acct_filter_topn")

    if "supplier_name" in df.columns and supplier.strip():
        df = df[df["supplier_name"].fillna("").astype(str).str.lower().str.contains(supplier.strip().lower())]

    if metric_col and metric_col in df.columns:
        try:
            df[metric_col] = pd.to_numeric(df[metric_col], errors="coerce").fillna(0)
            df = df[df[metric_col] >= float(min_open)]
        except Exception:
            pass

    # Sorting
    if "pain_score" in df.columns:
        try:
            df["pain_score"] = pd.to_numeric(df["pain_score"], errors="coerce").fillna(0)
        except Exception:
            pass
        df = df.sort_values(["pain_score"], ascending=False, errors="ignore")
    else:
        sort_cols = [c for c in ["open_issues", "critical", "high"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(sort_cols, ascending=False, errors="ignore")

    df = df.head(int(show_top))

    st.dataframe(df[cols], use_container_width=True, height=360)

    st.download_button(
        "Download Supplier Accountability CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="supplier_accountability.csv",
        mime="text/csv",
        use_container_width=True,
    )
