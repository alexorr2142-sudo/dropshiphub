# ui/triage_ui.py
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.styling import style_exceptions_table


def render_ops_triage(
    exceptions: pd.DataFrame,
    ops_pack_bytes: bytes,
    pack_name: str,
    *,
    key_prefix: str = "triage",
    top_n: int = 10,
) -> None:
    """
    Renders the Ops Triage panel (Start here):

      - Urgency counts
      - 4 triage modes stored in session_state
      - filter logic for CriticalHigh, MissingTracking, LateUnshipped
      - table preview (top N)
      - download ops pack ZIP
    """
    st.subheader("Ops Triage (Start here)")

    if exceptions is None or not isinstance(exceptions, pd.DataFrame) or exceptions.empty:
        st.info("No exceptions found 🎉")
        return

    # --- counts ---
    counts = exceptions["Urgency"].value_counts().to_dict() if "Urgency" in exceptions.columns else {}
    cA, cB, cC, cD = st.columns(4)
    cA.metric("Critical", int(counts.get("Critical", 0)))
    cB.metric("High", int(counts.get("High", 0)))
    cC.metric("Medium", int(counts.get("Medium", 0)))
    cD.metric("Low", int(counts.get("Low", 0)))

    # --- triage mode state ---
    state_key = f"{key_prefix}_filter"
    if state_key not in st.session_state:
        st.session_state[state_key] = "All"

    def set_triage(val: str):
        st.session_state[state_key] = val

    # --- buttons ---
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.button(
            "All",
            on_click=set_triage,
            args=("All",),
            use_container_width=True,
            key=f"{key_prefix}_btn_all",
        )
    with f2:
        st.button(
            "Critical + High",
            on_click=set_triage,
            args=("CriticalHigh",),
            use_container_width=True,
            key=f"{key_prefix}_btn_crit_high",
        )
    with f3:
        st.button(
            "Missing tracking",
            on_click=set_triage,
            args=("MissingTracking",),
            use_container_width=True,
            key=f"{key_prefix}_btn_missing_tracking",
        )
    with f4:
        st.button(
            "Late unshipped",
            on_click=set_triage,
            args=("LateUnshipped",),
            use_container_width=True,
            key=f"{key_prefix}_btn_late_unshipped",
        )

    triage = exceptions.copy()
    mode = st.session_state.get(state_key, "All")

    # --- filters (match app.py) ---
    if mode == "CriticalHigh" and "Urgency" in triage.columns:
        triage = triage[triage["Urgency"].isin(["Critical", "High"])]

    if mode == "MissingTracking":
        blob = (
            triage.get("issue_type", "").astype(str).fillna("") + " "
            + triage.get("explanation", "").astype(str).fillna("") + " "
            + triage.get("next_action", "").astype(str).fillna("")
        ).str.lower()
        triage = triage[
            blob.str.contains(
                "missing tracking|no tracking|tracking missing|invalid tracking",
                regex=True,
                na=False,
            )
        ]

    if mode == "LateUnshipped":
        blob = (
            triage.get("issue_type", "").astype(str).fillna("") + " "
            + triage.get("explanation", "").astype(str).fillna("") + " "
            + triage.get("line_status", "").astype(str).fillna("")
        ).str.lower()
        triage = triage[blob.str.contains("late unshipped|overdue|past due|late", regex=True, na=False)]

    # --- sort + columns ---
    preferred_cols = [
        "Urgency",
        "order_id",
        "sku",
        "issue_type",
        "customer_country",
        "supplier_name",
        "quantity_ordered",
        "quantity_shipped",
        "line_status",
        "explanation",
        "next_action",
        "customer_risk",
    ]
    show_cols = [c for c in preferred_cols if c in triage.columns]

    sort_cols = [c for c in ["Urgency", "order_id"] if c in triage.columns]
    if sort_cols:
        triage = triage.sort_values(sort_cols, ascending=True)

    # If no preferred cols exist, show the raw df safely
    preview = triage.head(int(top_n)) if not show_cols else triage[show_cols].head(int(top_n))

    st.dataframe(
        style_exceptions_table(preview),
        use_container_width=True,
        height=320,
    )

    # --- download ops pack zip ---
    st.download_button(
        "⬇️ Download Daily Ops Pack ZIP",
        data=ops_pack_bytes,
        file_name=pack_name,
        mime="application/zip",
        key=f"{key_prefix}_dl_ops_pack",
    )
