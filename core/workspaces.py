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

def list_runs(ws_root: Path) -> list[dict]:
    if not ws_root.exists():
        return []

    runs = []
    for workspace_dir in ws_root.iterdir():
        if not workspace_dir.is_dir():
            continue
        for run_dir in workspace_dir.iterdir():
            if not run_dir.is_dir():
                continue

            meta_path = run_dir / "meta.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}

            created_at = meta.get("created_at", run_dir.name)
            runs.append(
                {
                    "workspace_name": workspace_dir.name,
                    "run_id": run_dir.name,
                    "path": run_dir,
                    "created_at": created_at,
                    "meta": meta,
                }
            )

    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs

def save_run(
    ws_root: Path,
    workspace_name: str,
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
) -> Path:
    workspace_name = safe_slug(workspace_name)
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_dir = ws_root / workspace_name / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Outputs
    exceptions.to_csv(run_dir / "exceptions.csv", index=False)
    followups.to_csv(run_dir / "followups.csv", index=False)
    order_rollup.to_csv(run_dir / "order_rollup.csv", index=False)
    line_status_df.to_csv(run_dir / "line_status.csv", index=False)

    # Inputs
    orders.to_csv(run_dir / "orders_normalized.csv", index=False)
    shipments.to_csv(run_dir / "shipments_normalized.csv", index=False)
    tracking.to_csv(run_dir / "tracking_normalized.csv", index=False)

    if suppliers_df is not None and not suppliers_df.empty:
        suppliers_df.to_csv(run_dir / "suppliers.csv", index=False)

    meta = {
        "created_at": run_id,
        "workspace_name": workspace_name,
        "account_id": account_id,
        "store_id": store_id,
        "platform_hint": platform_hint,
        "kpis": kpis,
        "row_counts": {
            "orders": int(len(orders)),
            "shipments": int(len(shipments)),
            "tracking": int(len(tracking)),
            "exceptions": int(len(exceptions)),
            "followups": int(len(followups)),
            "order_rollup": int(len(order_rollup)),
            "line_status": int(len(line_status_df)),
            "suppliers": int(len(suppliers_df)) if suppliers_df is not None else 0,
        },
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return run_dir

def load_run(run_dir: Path) -> dict:
    out = {"meta": {}}
    meta_path = run_dir / "meta.json"
    if meta_path.exists():
        try:
            out["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            out["meta"] = {}

    def _read_csv(name: str) -> pd.DataFrame:
        p = run_dir / name
        return pd.read_csv(p) if p.exists() else pd.DataFrame()

    out["exceptions"] = _read_csv("exceptions.csv")
    out["followups"] = _read_csv("followups.csv")
    out["order_rollup"] = _read_csv("order_rollup.csv")
    out["line_status_df"] = _read_csv("line_status.csv")
    out["orders"] = _read_csv("orders_normalized.csv")
    out["shipments"] = _read_csv("shipments_normalized.csv")
    out["tracking"] = _read_csv("tracking_normalized.csv")
    out["suppliers_df"] = _read_csv("suppliers.csv")
    return out

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
