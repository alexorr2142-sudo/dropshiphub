# ui/sidebar.py
from pathlib import Path
import pandas as pd
import streamlit as st

from core.suppliers import load_suppliers, save_suppliers
from core.styling import style_supplier_table

def render_sidebar_context(data_dir: Path, workspaces_dir: Path, suppliers_dir: Path) -> dict:
    with st.sidebar:
        st.header("Plan")
        _plan = st.selectbox("Current plan", ["Early Access (Free)", "Pro", "Team"], index=0)
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

        st.divider()
        st.header("Tenant")
        account_id = st.text_input("account_id", value="demo_account")
        store_id = st.text_input("store_id", value="demo_store")
        platform_hint = st.selectbox("platform hint", ["shopify", "amazon", "etsy", "other"], index=0)

        st.divider()
        st.header("Defaults")
        default_currency = st.text_input("Default currency", value="USD")
        default_promised_ship_days = st.number_input(
            "Default promised ship days (SLA)",
            min_value=1,
            max_value=30,
            value=3,
        )

        st.divider()
        st.header("Demo Mode (Sticky)")
        demo_mode = st.toggle(
            "Use demo data (sticky)",
            key="demo_mode",
            help="Keeps demo data and your edits across interactions until you reset or turn off demo mode.",
        )

        if demo_mode:
            cdm1, cdm2 = st.columns(2)
            with cdm1:
                if st.button("Reset demo", use_container_width=True):
                    # reset happens in ui.demo.ensure_demo_state on rerun; just rerun
                    from ui.demo import _reset_demo_tables
                    try:
                        _reset_demo_tables(data_dir)
                        st.success("Demo reset ✅")
                        st.rerun()
                    except Exception as e:
                        st.error("Couldn't reset demo data.")
                        st.code(str(e))
            with cdm2:
                if st.button("Clear demo", use_container_width=True):
                    st.session_state["demo_mode"] = False
                    st.rerun()

        st.divider()
        st.header("Supplier Directory (CRM)")

        if "suppliers_df" not in st.session_state:
            st.session_state["suppliers_df"] = load_suppliers(suppliers_dir, account_id, store_id)

        f_suppliers = st.file_uploader("Upload suppliers.csv", type=["csv"], key="suppliers_uploader")
        if f_suppliers is not None:
            try:
                uploaded_suppliers = pd.read_csv(f_suppliers)
                st.session_state["suppliers_df"] = uploaded_suppliers
                p = save_suppliers(suppliers_dir, account_id, store_id, uploaded_suppliers)
                st.success(f"Saved ✅ {p.as_posix()}")
            except Exception as e:
                st.error("Failed to read suppliers CSV.")
                st.code(str(e))

        with st.expander("View Supplier Directory", expanded=False):
            suppliers_df_preview = st.session_state.get("suppliers_df", pd.DataFrame())
            if suppliers_df_preview is None or suppliers_df_preview.empty:
                st.caption("No supplier directory loaded yet. Upload suppliers.csv to auto-fill follow-up emails.")
            else:
                show_cols = [c for c in ["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"] if c in suppliers_df_preview.columns]
                if not show_cols:
                    st.dataframe(suppliers_df_preview, use_container_width=True, height=220)
                else:
                    st.dataframe(style_supplier_table(suppliers_df_preview[show_cols]), use_container_width=True, height=220)

                if "supplier_email" in suppliers_df_preview.columns:
                    missing_emails = suppliers_df_preview["supplier_email"].fillna("").astype(str).str.strip().eq("").sum()
                    st.caption(f"Missing supplier_email: {int(missing_emails)} row(s) (highlighted)")

        st.divider()
        st.caption("Tip: Upload suppliers.csv once per account/store to auto-fill follow-up emails.")

    suppliers_df = st.session_state.get("suppliers_df", pd.DataFrame())

    return {
        "account_id": account_id,
        "store_id": store_id,
        "platform_hint": platform_hint,
        "default_currency": default_currency,
        "default_promised_ship_days": int(default_promised_ship_days),
        "suppliers_df": suppliers_df,
        "demo_mode": bool(st.session_state.get("demo_mode", False)),
    }
