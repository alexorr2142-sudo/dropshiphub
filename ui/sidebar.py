# ui/sidebar.py
from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st

from core.suppliers import load_suppliers, save_suppliers
from ui.demo import reset_demo, clear_demo


def render_sidebar_context(
    data_dir: Path,
    workspaces_dir: Path,
    suppliers_dir: Path,
    *,
    key_prefix: str = "sb",
    # Optional extras (so app.py can stay thin later)
    issue_tracker_store_cls=None,   # pass IssueTrackerStore or None
    issue_tracker_path: Path | None = None,
    ops_pack_bytes: bytes | None = None,
    ops_pack_name: str | None = None,
) -> dict:
    """
    Renders the sidebar and returns a context dict:
      account_id, store_id, platform_hint,
      default_currency, default_promised_ship_days,
      suppliers_df, demo_mode

    Optional:
      - Issue Tracker maintenance tools (prune/clear resolved)
      - Daily Ops Pack download button
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
        account_id = st.text_input("account_id", value="demo_account", key=f"{key_prefix}_account_id")
        store_id = st.text_input("store_id", value="demo_store", key=f"{key_prefix}_store_id")
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
        default_currency = st.text_input("Default currency", value="USD", key=f"{key_prefix}_currency")
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
        demo_mode = st.toggle(
            "Use demo data (sticky)",
            key="demo_mode",  # global key on purpose (shared across modules)
            help="Keeps demo data and your edits across interactions until you reset or turn off demo mode.",
        )

        if demo_mode:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Reset demo", use_container_width=True, key=f"{key_prefix}_demo_reset"):
                    reset_demo(data_dir)
                    st.success("Demo reset ✅")
                    st.rerun()
            with c2:
                if st.button("Clear demo", use_container_width=True, key=f"{key_prefix}_demo_clear"):
                    st.session_state["demo_mode"] = False
                    clear_demo()
                    st.rerun()

        # ----------------
        # Issue Tracker Maintenance (optional)
        # ----------------
        if issue_tracker_store_cls is not None and issue_tracker_path is not None:
            st.divider()
            with st.expander("Issue Tracker Maintenance", expanded=False):
                prune_days = st.number_input(
                    "Prune resolved older than (days)",
                    min_value=1,
                    max_value=365,
                    value=30,
                    step=1,
                    key=f"{key_prefix}_issue_prune_days",
                )

                cmt1, cmt2 = st.columns(2)
                with cmt1:
                    if st.button("🧹 Prune old resolved", use_container_width=True, key=f"{key_prefix}_issue_prune_btn"):
                        try:
                            store = issue_tracker_store_cls(issue_tracker_path)
                            removed = store.prune_resolved_older_than_days(int(prune_days))
                            st.success(f"Pruned {removed} resolved item(s).")
                            st.rerun()
                        except Exception as e:
                            st.error("Failed to prune resolved issues.")
                            st.code(str(e))

                with cmt2:
                    if st.button("🗑️ Clear ALL resolved", use_container_width=True, key=f"{key_prefix}_issue_clear_btn"):
                        try:
                            store = issue_tracker_store_cls(issue_tracker_path)
                            removed = store.clear_resolved()
                            st.success(f"Cleared {removed} resolved item(s).")
                            st.rerun()
                        except Exception as e:
                            st.error("Failed to clear resolved issues.")
                            st.code(str(e))

        # ----------------
        # Supplier Directory (CRM)
        # ----------------
        st.divider()
        st.header("Supplier Directory (CRM)")

        # IMPORTANT:
        # This key is global intentionally so the dataframe persists and can be used elsewhere.
        if "suppliers_df" not in st.session_state:
            st.session_state["suppliers_df"] = load_suppliers(suppliers_dir, account_id, store_id)

        f_suppliers = st.file_uploader(
            "Upload suppliers.csv",
            type=["csv"],
            key=f"{key_prefix}_suppliers_uploader",
        )
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
                show_cols = [
                    c for c in ["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"]
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

        # ----------------
        # Daily Ops Pack (optional)
        # ----------------
        if ops_pack_bytes is not None and ops_pack_name:
            st.divider()
            st.header("Daily Ops Pack")
            st.download_button(
                "⬇️ Download Daily Ops Pack ZIP",
                data=ops_pack_bytes,
                file_name=str(ops_pack_name),
                mime="application/zip",
                use_container_width=True,
                key=f"{key_prefix}_ops_pack_dl",
            )

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
