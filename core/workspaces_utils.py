# core/workspaces.py
import io
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd


def safe_slug(s: str) -> str:
    s = (s or "").strip()
    keep = []
    for ch in s:
        if ch.isalnum() or ch in ["-", "_", " "]:
            keep.append(ch)
    out = "".join(keep).strip().replace(" ", "_")
    return out[:60] if out else "workspace"


def workspace_root(workspaces_dir: Path, account_id: str, store_id: str) -> Path:
    return workspaces_dir / safe_slug(account_id) / safe_slug(store_id)


