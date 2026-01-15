import streamlit as st
import pandas as pd


def render_supplier_accountability(accountability: pd.DataFrame | None):
    """
    Simple, safe UI wrapper for supplier accountability view.
    Expected columns (best effort):
      supplier_name, open_issues, critical, high, worst_escalation, next_action, owner
    """
    st.subheader("Supplier Accountability")

    if accountability is None or accountability.empty:
        st.caption("No supplier accountability items available for this run.")
        return

    df = accountability.copy()

    # Prefer a clean column ordering if present
    preferred = [
        "supplier_name",
        "worst_escalation",
        "open_issues",
        "critical",
        "high",
        "next_action",
        "owner",
        "last_contacted",
    ]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]

    # Light filtering controls
    c1, c2, c3 = st.columns(3)
    with c1:
        supplier = st.text_input("Filter supplier (contains)", value="", key="acct_filter_supplier")
    with c2:
        min_open = st.number_input("Min open issues", min_value=0, value=0, step=1, key="acct_filter_min_open")
    with c3:
        show_top = st.slider("Show top N", min_value=5, max_value=100, value=25, step=5, key="acct_filter_topn")

    if "supplier_name" in df.columns and supplier.strip():
        df = df[df["supplier_name"].fillna("").astype(str).str.lower().str.contains(supplier.strip().lower())]

    if "open_issues" in df.columns:
        try:
            df["open_issues"] = pd.to_numeric(df["open_issues"], errors="coerce").fillna(0).astype(int)
            df = df[df["open_issues"] >= int(min_open)]
        except Exception:
            pass

    # Sort: most open issues first, then critical/high
    sort_cols = [c for c in ["open_issues", "critical", "high"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=False)

    df = df.head(int(show_top))

    st.dataframe(df[cols], use_container_width=True, height=360)

    st.download_button(
        "Download Supplier Accountability CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="supplier_accountability.csv",
        mime="text/csv",
        use_container_width=True,
    )
