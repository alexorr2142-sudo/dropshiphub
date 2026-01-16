# ui/workspaces_ui.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


@dataclass
class WorkspacesResult:
    ws_root: Path
    workspace_name: str
    loaded_run_dir: Optional[Path]
    # Back-compat outputs (optional)
    exceptions: Optional[pd.DataFrame] = None
    followups_full: Optional[pd.DataFrame] = None
    order_rollup: Optional[pd.DataFrame] = None
    line_status_df: Optional[pd.DataFrame] = None
    suppliers_df: Optional[pd.DataFrame] = None


def _is_raw_snapshot_run(run: dict) -> bool:
    """
    Best-effort detection for demo RAW snapshot runs.

    We treat a run as "RAW snapshot" if:
      - run_id contains "_raw", OR
      - the run folder name contains "_raw"
    """
    try:
        rid = str(run.get("run_id", "") or "")
        if "_raw" in rid:
            return True
        p = run.get("path")
        if p:
            return "_raw" in Path(p).name
    except Exception:
        return False
    return False


def render_workspaces_sidebar(
    workspaces_dir: Path,
    account_id: str,
    store_id: str,
    *,
    platform_hint: Optional[str] = None,
    # current run snapshots (needed only for Save)
    orders: Optional[pd.DataFrame] = None,
    shipments: Optional[pd.DataFrame] = None,
    tracking: Optional[pd.DataFrame] = None,
    exceptions: Optional[pd.DataFrame] = None,
    followups_full: Optional[pd.DataFrame] = None,
    order_rollup: Optional[pd.DataFrame] = None,
    line_status_df: Optional[pd.DataFrame] = None,
    kpis: Optional[dict] = None,
    suppliers_df: Optional[pd.DataFrame] = None,
    # optional display
    issue_tracker_path: Optional[Path] = None,
    key_prefix: str = "ws",
) -> WorkspacesResult:
    """
    Sidebar UI for:
      - Save run
      - Load previous run
      - Download run pack
      - View history
      - Delete run
      - RAW demo snapshot actions (Load into Demo Mode / Convert to full run) [safe signals only]

    Returns:
      WorkspacesResult with:
        - ws_root
        - workspace_name
        - loaded_run_dir (Path | None)

    Notes:
      - This function does NOT decide "open vs resolved"; it stores/loads followups as provided.
      - Back-compat: will also return overridden outputs if a run is loaded.
      - RAW snapshot actions are implemented as session_state *requests* that other modules
        may choose to handle. If nothing handles them, the app still works.
    """
    ws_root = workspace_root(workspaces_dir, account_id, store_id)
    ws_root.mkdir(parents=True, exist_ok=True)

    loaded_key = f"{key_prefix}_loaded_run"
    if loaded_key not in st.session_state:
        st.session_state[loaded_key] = None

    # Requests for other modules (safe, optional)
    req_load_demo_key = f"{key_prefix}_req_load_snapshot_into_demo"
    req_convert_key = f"{key_prefix}_req_convert_snapshot_to_run"
    if req_load_demo_key not in st.session_state:
        st.session_state[req_load_demo_key] = None
    if req_convert_key not in st.session_state:
        st.session_state[req_convert_key] = None

    with st.sidebar:
        st.divider()
        st.header("Workspaces")

        if issue_tracker_path is not None:
            st.caption(f"Issue tracker file: `{issue_tracker_path.as_posix()}`")

        workspace_name = st.text_input("Workspace name", value="default", key=f"{key_prefix}_name")

        # --- Save run ---
        if st.button("💾 Save this run", key=f"{key_prefix}_btn_save"):
            if orders is None or shipments is None:
                st.error("Cannot save: orders/shipments not available.")
            else:
                run_dir = save_run(
                    ws_root=ws_root,
                    workspace_name=workspace_name,
                    account_id=account_id,
                    store_id=store_id,
                    platform_hint=platform_hint or "",
                    orders=orders if orders is not None else pd.DataFrame(),
                    shipments=shipments if shipments is not None else pd.DataFrame(),
                    tracking=tracking if tracking is not None else pd.DataFrame(),
                    exceptions=exceptions if exceptions is not None else pd.DataFrame(),
                    followups_full=followups_full if followups_full is not None else pd.DataFrame(),
                    order_rollup=order_rollup if order_rollup is not None else pd.DataFrame(),
                    line_status_df=line_status_df if line_status_df is not None else pd.DataFrame(),
                    kpis=kpis if isinstance(kpis, dict) else {},
                    suppliers_df=suppliers_df if suppliers_df is not None else pd.DataFrame(),
                )
                st.success(f"Saved ✅ {workspace_name}/{run_dir.name}")
                st.session_state[loaded_key] = str(run_dir)

        runs = list_runs(ws_root) or []
        raw_runs = [r for r in runs if _is_raw_snapshot_run(r)]
        non_raw_runs = [r for r in runs if r not in raw_runs]

        # --- RAW demo snapshot awareness ---
        if raw_runs:
            with st.expander("🧪 RAW demo snapshots", expanded=False):
                raw_labels = []
                for r in raw_runs:
                    rc = (r.get("meta", {}) or {}).get("row_counts", {}) or {}
                    raw_labels.append(
                        f"{r.get('workspace_name','')} / {r.get('run_id','')}  "
                        f"(exceptions: {rc.get('exceptions','?')}, followups: {rc.get('followups','?')})"
                    )

                raw_idx = st.selectbox(
                    "Select RAW snapshot",
                    options=list(range(len(raw_runs))),
                    format_func=lambda i: raw_labels[i],
                    key=f"{key_prefix}_raw_select",
                )

                target_ws = st.text_input(
                    "Convert target workspace",
                    value=workspace_name,
                    key=f"{key_prefix}_raw_convert_target_ws",
                    help="Where the converted full run should be saved (conversion handler decides final path).",
                )

                r1, r2 = st.columns(2)

                with r1:
                    if st.button("Load snapshot → Demo Mode", key=f"{key_prefix}_btn_raw_load_demo"):
                        try:
                            st.session_state[req_load_demo_key] = {
                                "snapshot_dir": str(raw_runs[raw_idx]["path"]),
                                "source_workspace": str(raw_runs[raw_idx].get("workspace_name", "")),
                                "source_run_id": str(raw_runs[raw_idx].get("run_id", "")),
                            }
                            st.success("Requested ✅ (handled by Demo UI)")
                        except Exception as e:
                            st.warning(f"Could not queue demo-load request: {e}")

                with r2:
                    if st.button("Convert snapshot → full run", key=f"{key_prefix}_btn_raw_convert"):
                        try:
                            st.session_state[req_convert_key] = {
                                "snapshot_dir": str(raw_runs[raw_idx]["path"]),
                                "target_workspace": str(target_ws or workspace_name),
                                "source_workspace": str(raw_runs[raw_idx].get("workspace_name", "")),
                                "source_run_id": str(raw_runs[raw_idx].get("run_id", "")),
                            }
                            st.success("Requested ✅ (handled by Workspaces/Core)")
                        except Exception as e:
                            st.warning(f"Could not queue conversion request: {e}")

                # Show the queued request (helps debugging, never fatal)
                try:
                    queued_demo = st.session_state.get(req_load_demo_key)
                    queued_conv = st.session_state.get(req_convert_key)
                    if queued_demo or queued_conv:
                        st.caption("Queued actions (safe signals):")
                        if queued_demo:
                            st.code(f"{req_load_demo_key} = {queued_demo}")
                        if queued_conv:
                            st.code(f"{req_convert_key} = {queued_conv}")
                except Exception:
                    pass

        # --- Load + run pack (regular saved runs) ---
        if non_raw_runs:
            run_labels = [
                f"{r['workspace_name']} / {r['run_id']}  (exceptions: {r.get('meta', {}).get('row_counts', {}).get('exceptions', '?')})"
                for r in non_raw_runs
            ]
            chosen_idx = st.selectbox(
                "Load previous run",
                options=list(range(len(non_raw_runs))),
                format_func=lambda i: run_labels[i],
                key=f"{key_prefix}_load_select",
            )

            c1, c2 = st.columns(2)
            with c1:
                if st.button("📂 Load", key=f"{key_prefix}_btn_load"):
                    st.session_state[loaded_key] = str(non_raw_runs[chosen_idx]["path"])
                    st.success("Loaded ✅")

            with c2:
                loaded_path = st.session_state.get(loaded_key)
                if loaded_path:
                    run_dir = Path(loaded_path)
                    zip_bytes = make_run_zip_bytes(run_dir)
                    st.download_button(
                        "⬇️ Run Pack",
                        data=zip_bytes,
                        file_name=f"runpack_{run_dir.parent.name}_{run_dir.name}.zip",
                        mime="application/zip",
                        key=f"{key_prefix}_btn_zip_runpack",
                    )

            # --- History + delete ---
            with st.expander("Run history", expanded=False):
                history_df = build_run_history_df(runs)
                st.dataframe(history_df, use_container_width=True, height=220)

                st.divider()
                st.markdown("**Delete a saved run**")
                st.caption("This permanently deletes the selected run folder on disk.")

                delete_idx = st.selectbox(
                    "Select run to delete",
                    options=list(range(len(runs))),
                    format_func=lambda i: f"{runs[i]['workspace_name']} / {runs[i]['run_id']}",
                    key=f"{key_prefix}_delete_select",
                )

                confirm = st.checkbox("I understand this cannot be undone", key=f"{key_prefix}_delete_confirm")
                if st.button("🗑️ Delete run", disabled=not confirm, key=f"{key_prefix}_btn_delete"):
                    target = Path(runs[delete_idx]["path"])
                    loaded_path = st.session_state.get(loaded_key)

                    delete_run_dir(target)

                    if loaded_path and Path(loaded_path) == target:
                        st.session_state[loaded_key] = None

                    st.success("Deleted ✅")
                    st.rerun()
        else:
            if not runs:
                st.caption("No saved runs yet. Click **Save this run** to create your first run history entry.")
            else:
                st.caption("Only RAW demo snapshots found. Expand **RAW demo snapshots** above to act on them.")

    # --- Load override outputs (back-compat) ---
    loaded_run_dir = Path(st.session_state[loaded_key]) if st.session_state.get(loaded_key) else None

    out = WorkspacesResult(
        ws_root=ws_root,
        workspace_name=workspace_name,
        loaded_run_dir=loaded_run_dir,
        exceptions=exceptions,
        followups_full=followups_full,
        order_rollup=order_rollup,
        line_status_df=line_status_df,
        suppliers_df=suppliers_df,
    )

    if loaded_run_dir:
        loaded = load_run(loaded_run_dir)

        out.exceptions = loaded.get("exceptions", out.exceptions)
        out.followups_full = loaded.get("followups", out.followups_full)
        out.order_rollup = loaded.get("order_rollup", out.order_rollup)
        out.line_status_df = loaded.get("line_status_df", out.line_status_df)

        loaded_suppliers = loaded.get("suppliers_df", pd.DataFrame())
        if isinstance(loaded_suppliers, pd.DataFrame) and not loaded_suppliers.empty:
            out.suppliers_df = loaded_suppliers
            st.session_state["suppliers_df"] = loaded_suppliers

        meta = loaded.get("meta", {}) or {}
        st.info(f"Viewing saved run: **{meta.get('workspace_name','')} / {meta.get('created_at','')}**")

    return out


# Backward-compatible wrapper using your old signature.
# This lets you paste this file now without changing app.py yet.
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
    res = render_workspaces_sidebar(
        workspaces_dir=workspaces_dir,
        account_id=account_id,
        store_id=store_id,
        platform_hint=platform_hint,
        orders=orders,
        shipments=shipments,
        tracking=tracking,
        exceptions=exceptions,
        followups_full=followups,
        order_rollup=order_rollup,
        line_status_df=line_status_df,
        kpis=kpis,
        suppliers_df=suppliers_df,
        issue_tracker_path=None,
        key_prefix="ws",
    )
    return res.exceptions, res.followups_full, res.order_rollup, res.line_status_df, res.suppliers_df
