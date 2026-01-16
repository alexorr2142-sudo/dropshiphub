# ui/sidebar.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.suppliers import load_suppliers, save_suppliers


def render_sidebar_context(
    data_dir: Path,
    workspaces_dir: Path,
    suppliers_dir: Path,
    *,
    key_prefix: str = "sb",
) -> dict:
    """
    Renders sidebar controls and returns:
      account_id, store_id, platform_hint,
      default_currency, default_promised_ship_days,
      suppliers_df, demo_mode
    """

    with st.sidebar:
        # ----------------
        # Plan
        # ----------------
        st.header("Plan")
        st.selectbox(
            "Current plan",
            ["Early Access (Free)", "Pro", "Team"],
            index=0,
            key=f"{key_prefix}_plan",
        )
        with st.expander("Upgrade / Pricing (placeholder)", expanded=False):
            st.markdown(
                """
**Early Access (Free)**
- CSV uploads
- Exceptions + supplier follow-ups
- Supplier Directory (CRM)
- Supplier scorecards

**Pro**
- Saved workspaces + run history
- Automations (coming soon)

**Team**
- Role-based access (coming soon)
- Audit trail (coming soon)
                """.strip()
            )

        # ----------------
        # Tenant
        # ----------------
        st.divider()
        st.header("Tenant")
        account_id = st.text_input(
            "account_id",
            value="demo_account",
            key=f"{key_prefix}_account_id",
        )
        store_id = st.text_input(
            "store_id",
            value="demo_store",
            key=f"{key_prefix}_store_id",
        )
        platform_hint = st.selectbox(
            "platform hint",
            ["shopify", "amazon", "etsy", "other"],
            index=0,
            key=f"{key_prefix}_platform_hint",
        )

        # ----------------
        # Defaults
        # ----------------
        st.divider()
        st.header("Defaults")
        default_currency = st.text_input(
            "Default currency",
            value="USD",
            key=f"{key_prefix}_currency",
        )
        default_promised_ship_days = st.number_input(
            "Default promised ship days (SLA)",
            min_value=1,
            max_value=30,
            value=3,
            key=f"{key_prefix}_sla_days",
        )

        # ----------------
        # Demo Mode (Sticky)
        # ----------------
        st.divider()
        st.header("Demo Mode (Sticky)")

        # ✅ IMPORTANT: do NOT use global key="demo_mode" here
        demo_mode = st.toggle(
            "Use demo data (sticky)",
            key=f"{key_prefix}_demo_mode",
            help="Keeps demo data and your edits across interactions until you turn it off.",
        )

        # Keep a canonical boolean in session_state for other modules to read safely
        # Streamlit may throw if 'demo_mode' is (or was) bound to a widget key elsewhere.
        demo_mode_bool = bool(demo_mode)
        try:
            st.session_state["demo_mode"] = demo_mode_bool
        except Exception:
            # Fallback key that will not collide with any widget
            st.session_state["app_demo_mode"] = demo_mode_bool

        # ----------------
        # Supplier Directory (CRM)
        # ----------------
        st.divider()
        st.header("Supplier Directory (CRM)")

        # Load saved suppliers for this tenant (once per tenant change)
        cache_key = f"{key_prefix}_suppliers_df_cache"
        cache_tenant_key = f"{key_prefix}_suppliers_df_cache_tenant"

        cur_tenant = f"{account_id}::{store_id}"
        if st.session_state.get(cache_tenant_key) != cur_tenant:
            st.session_state[cache_tenant_key] = cur_tenant
            st.session_state[cache_key] = load_suppliers(suppliers_dir, account_id, store_id)

        f_suppliers = st.file_uploader(
            "Upload suppliers.csv",
            type=["csv"],
            key=f"{key_prefix}_suppliers_uploader",
        )
        if f_suppliers is not None:
            try:
                uploaded_suppliers = pd.read_csv(f_suppliers)
                st.session_state[cache_key] = uploaded_suppliers
                p = save_suppliers(suppliers_dir, account_id, store_id, uploaded_suppliers)
                st.success(f"Saved ✅ {p.as_posix()}")
            except Exception as e:
                st.error("Failed to read suppliers CSV.")
                st.code(str(e))

        with st.expander("View Supplier Directory", expanded=False):
            suppliers_df_preview = st.session_state.get(cache_key, pd.DataFrame())
            if suppliers_df_preview is None or suppliers_df_preview.empty:
                st.caption("No supplier directory loaded yet. Upload suppliers.csv to auto-fill follow-up emails.")
            else:
                show_cols = [
                    c
                    for c in ["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"]
                    if c in suppliers_df_preview.columns
                ]
                st.dataframe(
                    suppliers_df_preview[show_cols] if show_cols else suppliers_df_preview,
                    use_container_width=True,
                    height=220,
                )
                if "supplier_email" in suppliers_df_preview.columns:
                    missing_emails = (
                        suppliers_df_preview["supplier_email"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .eq("")
                        .sum()
                    )
                    st.caption(f"Missing supplier_email: {int(missing_emails)} row(s)")

        st.caption("Tip: Upload suppliers.csv once per account/store to auto-fill follow-up emails.")

    suppliers_df = st.session_state.get(f"{key_prefix}_suppliers_df_cache", pd.DataFrame())

    # Read canonical demo mode without crashing even if Streamlit blocked 'demo_mode'
    effective_demo_mode = bool(
        st.session_state.get("demo_mode", st.session_state.get("app_demo_mode", False))
    )

    return {
        "account_id": account_id,
        "store_id": store_id,
        "platform_hint": platform_hint,
        "default_currency": default_currency,
        "default_promised_ship_days": int(default_promised_ship_days),
        "suppliers_df": suppliers_df,
        "demo_mode": effective_demo_mode,
    }
