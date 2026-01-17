# ui/sidebar.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.suppliers import load_suppliers, save_suppliers
from ui.demo_health import render_demo_health_badge

# Best-effort import: sidebar can pre-load demo state so the health badge is accurate
try:
    from ui.demo import ensure_demo_state  # type: ignore
except Exception:
    ensure_demo_state = None


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
- Exceptions + follow-ups
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
        st.header("ClearOps Demo (Sticky)")

        demo_mode = st.toggle(
            "Use demo data (sticky)",
            key=f"{key_prefix}_demo_mode",
            help="Runs ClearOps with built-in demo data (and your edits) until you turn it off.",
        )

        # Keep a canonical boolean in session_state for other modules to read safely
        demo_mode_bool = bool(demo_mode)
        try:
            st.session_state["demo_mode"] = demo_mode_bool
        except Exception:
            st.session_state["app_demo_mode"] = demo_mode_bool

        # Ensure demo state is initialized BEFORE rendering the health badge
        # (otherwise the badge can show BROKEN on the first rerun)
        if demo_mode_bool and callable(ensure_demo_state):
            try:
                ensure_demo_state(data_dir)
            except Exception:
                # Never let demo preload break the sidebar
                pass

        # Demo health badge
        render_demo_health_badge(data_dir)

        # ----------------
        # Supplier Directory (CRM)
        # ----------------
        st.divider()
        st.header("Supplier Directory (CRM)")

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
                st.caption("No supplier directory loaded yet. Upload suppliers.csv to auto-fill follow-ups.")
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

        st.caption("Tip: Upload suppliers.csv once per account/store to auto-fill follow-ups.")

    suppliers_df = st.session_state.get(f"{key_prefix}_suppliers_df_cache", pd.DataFrame())

    effective_demo_mode = bool(st.session_state.get("demo_mode", st.session_state.get("app_demo_mode", False)))

    return {
        "account_id": account_id,
        "store_id": store_id,
        "platform_hint": platform_hint,
        "default_currency": default_currency,
        "default_promised_ship_days": int(default_promised_ship_days),
        "suppliers_df": suppliers_df,
        "demo_mode": effective_demo_mode,
    }
