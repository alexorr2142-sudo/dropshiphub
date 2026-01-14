# ui/workspaces_ui.py
from pathlib import Path
import pandas as pd
import streamlit as st

from core.workspaces import (
    workspace_root,
    list_runs,
    save_run,
    load_run,
    make_run_zip_bytes,
    delete_run_dir,
    build_run_history_df,
)

def render_workspaces_sidebar_and_maybe_override_outputs(
    workspaces_dir: Path,
    account_id: str,
    store_id: str,
    platform_hint: str,
    orders: pd.DataFrame,
    shipments: pd.DataFrame,
    tracking: pd.DataFrame,
    exceptions: pd.DataFrame,
    followups: pd.DataFrame,
    order_rollup: pd.DataFrame,
    line_status_df: pd.DataFrame,
    kpis: dict,
    suppliers_df: pd.DataFrame,
):
    ws_root = workspace_root(workspaces_dir, account_id, store_id)
    ws_root.mkdir(parents=True, exist_ok=True)

    if "loaded_run" not in st.session_state:
        st.session_state["loaded_run"] = None

    with st.sidebar:
        st.divider()
        st.header("Workspaces")
        workspace_name = st.text_input("Workspace name", value="default", key="ws_name")

        if st.button("💾 Save this run", key="btn_save_run"):
            run_dir = save_run(
                ws_root=ws_root,
                workspace_name=workspace_name,
                account_id=account_id,
                store_id=store_id,
                platform_hint=platform_hint,
                orders=orders,
                shipments=shipments,
                tracking=tracking,
                exceptions=exceptions,
                followups=followups,
                order_rollup=order_rollup,
                line_status_df=line_status_df,
                kpis=kpis,
                suppliers_df=suppliers_df,
            )
            st.success(f"Saved ✅ {workspace_name}/{run_dir.name}")
            st.session_state["loaded_run"] = str(run_dir)

        runs = list_runs(ws_root)

        if runs:
            run_labels = [
                f"{r['workspace_name']} / {r['run_id']}  (exceptions: {r.get('meta', {}).get('row_counts', {}).get('exceptions', '?')})"
                for r in runs
            ]
            chosen_idx = st.selectbox(
                "Load previous run",
                options=list(range(len(runs))),
                format_func=lambda i: run_labels[i],
                key="ws_load_select",
            )

            cL1, cL2 = st.columns(2)
            with cL1:
                if st.button("📂 Load", key="btn_load_run"):
                    st.session_state["loaded_run"] = str(runs[chosen_idx]["path"])
                    st.success("Loaded ✅")
            with cL2:
                if st.session_state["loaded_run"]:
                    run_dir = Path(st.session_state["loaded_run"])
                    zip_bytes = make_run_zip_bytes(run_dir)
                    st.download_button(
                        "⬇️ Run Pack",
                        data=zip_bytes,
                        file_name=f"runpack_{run_dir.parent.name}_{run_dir.name}.zip",
                        mime="application/zip",
                        key="btn_zip_runpack",
                    )

            with st.expander("Run history (7.5)", expanded=False):
                history_df = build_run_history_df(runs)
                st.dataframe(history_df, use_container_width=True, height=220)

                st.divider()
                st.markdown("**Delete a saved run**")
                st.caption("This permanently deletes the selected run folder on disk.")

                delete_idx = st.selectbox(
                    "Select run to delete",
                    options=list(range(len(runs))),
                    format_func=lambda i: f"{runs[i]['workspace_name']} / {runs[i]['run_id']}",
                    key="ws_delete_select",
                )

                confirm = st.checkbox("I understand this cannot be undone", key="ws_delete_confirm")
                if st.button("🗑️ Delete run", disabled=not confirm, key="btn_delete_run"):
                    target = Path(runs[delete_idx]["path"])
                    loaded_path = st.session_state.get("loaded_run")
                    delete_run_dir(target)

                    if loaded_path and Path(loaded_path) == target:
                        st.session_state["loaded_run"] = None

                    st.success("Deleted ✅")
                    st.rerun()
        else:
            st.caption("No saved runs yet. Click **Save this run** to create your first run history entry.")

    # If a run is loaded, override outputs (+ suppliers snapshot if present)
    if st.session_state.get("loaded_run"):
        loaded = load_run(Path(st.session_state["loaded_run"]))
        exceptions = loaded.get("exceptions", exceptions)
        followups = loaded.get("followups", followups)
        order_rollup = loaded.get("order_rollup", order_rollup)
        line_status_df = loaded.get("line_status_df", line_status_df)

        loaded_suppliers = loaded.get("suppliers_df", pd.DataFrame())
        if loaded_suppliers is not None and not loaded_suppliers.empty:
            suppliers_df = loaded_suppliers
            st.session_state["suppliers_df"] = loaded_suppliers

        meta = loaded.get("meta", {}) or {}
        st.info(f"Viewing saved run: **{meta.get('workspace_name','')} / {meta.get('created_at','')}**")

    return exceptions, followups, order_rollup, line_status_df, suppliers_df
