# core/kpi_trends.py
import json
from datetime import datetime
from pathlib import Path
import pandas as pd


def _safe_slug(s: str) -> str:
    s = (s or "").strip()
    keep = []
    for ch in s:
        if ch.isalnum() or ch in ["-", "_", " "]:
            keep.append(ch)
    out = "".join(keep).strip().replace(" ", "_")
    return out[:60] if out else "workspace"


def _parse_run_id_to_dt(run_id: str):
    # run_id format: 20260114T173012Z (UTC)
    try:
        return datetime.strptime(run_id, "%Y%m%dT%H%M%SZ")
    except Exception:
        return None


def _workspace_root(workspaces_dir: Path, account_id: str, store_id: str) -> Path:
    return Path(workspaces_dir) / _safe_slug(account_id) / _safe_slug(store_id)


def load_kpi_history(workspaces_dir: Path, account_id: str, store_id: str, max_runs: int = 60) -> pd.DataFrame:
    """
    Reads saved runs under:
      data/workspaces/<account_id>/<store_id>/<workspace_name>/<run_id>/meta.json

    Returns a dataframe sorted by run_dt asc with KPI columns:
      run_id, run_dt, workspace_name, pct_unshipped, pct_late_unshipped, pct_delivered, pct_shipped_or_delivered, total_order_lines
    """
    ws_root = _workspace_root(Path(workspaces_dir), account_id, store_id)
    if not ws_root.exists():
        return pd.DataFrame()

    rows = []
    # workspace_name folders
    for workspace_dir in ws_root.iterdir():
        if not workspace_dir.is_dir():
            continue

        # run_id folders
        for run_dir in workspace_dir.iterdir():
            if not run_dir.is_dir():
                continue

            meta_path = run_dir / "meta.json"
            if not meta_path.exists():
                continue

            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            run_id = meta.get("created_at", run_dir.name)
            run_dt = _parse_run_id_to_dt(run_id)

            kpis = meta.get("kpis", {}) or {}
            counts = meta.get("row_counts", {}) or {}

            rows.append(
                {
                    "workspace_name": workspace_dir.name,
                    "run_id": run_id,
                    "run_dt": run_dt,
                    # KPI fields (best-effort)
                    "pct_unshipped": kpis.get("pct_unshipped", None),
                    "pct_late_unshipped": kpis.get("pct_late_unshipped", None),
                    "pct_delivered": kpis.get("pct_delivered", None),
                    "pct_shipped_or_delivered": kpis.get("pct_shipped_or_delivered", None),
                    "total_order_lines": kpis.get("total_order_lines", counts.get("orders", None)),
                    "exceptions": (meta.get("row_counts", {}) or {}).get("exceptions", None),
                    "followups": (meta.get("row_counts", {}) or {}).get("followups", None),
                }
            )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # normalize numeric columns
    for c in [
        "pct_unshipped",
        "pct_late_unshipped",
        "pct_delivered",
        "pct_shipped_or_delivered",
        "total_order_lines",
        "exceptions",
        "followups",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # sort and cap to most recent N
    df = df.sort_values("run_dt", ascending=True)
    if max_runs and len(df) > int(max_runs):
        df = df.tail(int(max_runs)).copy()

    return df.reset_index(drop=True)


def compute_trend_delta(df: pd.DataFrame, col: str):
    """
    Returns (latest_value, previous_value, delta) for a numeric column.
    """
    if df is None or df.empty or col not in df.columns:
        return (None, None, None)

    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(s) == 0:
        return (None, None, None)
    if len(s) == 1:
        v = float(s.iloc[-1])
        return (v, None, None)

    latest = float(s.iloc[-1])
    prev = float(s.iloc[-2])
    return (latest, prev, latest - prev)
