# core/paths.py
from pathlib import Path
import streamlit as st

def init_paths(base_dir: Path):
    data_dir = base_dir / "data"

    workspaces_dir = data_dir / "workspaces"
    if workspaces_dir.exists() and not workspaces_dir.is_dir():
        st.error(
            "Workspace storage path is invalid: `data/workspaces` exists but is a FILE, not a folder.\n\n"
            "Fix: delete or rename `data/workspaces` in your repo, then redeploy."
        )
        st.stop()
    workspaces_dir.mkdir(parents=True, exist_ok=True)

    suppliers_dir = data_dir / "suppliers"
    if suppliers_dir.exists() and not suppliers_dir.is_dir():
        st.error(
            "Supplier storage path is invalid: `data/suppliers` exists but is a FILE, not a folder.\n\n"
            "Fix: delete or rename `data/suppliers` in your repo, then redeploy."
        )
        st.stop()
    suppliers_dir.mkdir(parents=True, exist_ok=True)

    return base_dir, data_dir, workspaces_dir, suppliers_dir
