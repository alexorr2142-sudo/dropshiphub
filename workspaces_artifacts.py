# core/workspaces_artifacts.py
from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import pandas as pd

def make_run_zip_bytes(run_dir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in run_dir.rglob("*"):
            if p.is_file():
                z.write(p, arcname=p.relative_to(run_dir))
    buf.seek(0)
    return buf.read()


def delete_run_dir(run_dir: Path) -> None:
    if run_dir.exists() and run_dir.is_dir():
        shutil.rmtree(run_dir, ignore_errors=True)


def build_run_history_df(runs: list[dict]) -> pd.DataFrame:
    rows = []
    for r in runs:
        meta = r.get("meta", {}) or {}
        counts = meta.get("row_counts", {}) or {}
        kpis = meta.get("kpis", {}) or {}
        rows.append(
            {
                "workspace": r.get("workspace_name", ""),
                "run_id": r.get("run_id", ""),
                "created_at": meta.get("created_at", r.get("created_at", "")),
                "exceptions": counts.get("exceptions", ""),
                "followups": counts.get("followups", ""),
                "suppliers": counts.get("suppliers", ""),
                "pct_unshipped": kpis.get("pct_unshipped", ""),
                "pct_late_unshipped": kpis.get("pct_late_unshipped", ""),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty and "created_at" in df.columns:
        df = df.sort_values("created_at", ascending=False)
    return df
