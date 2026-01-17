# core/workspaces_io.py
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.workspaces_utils import safe_slug

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

    # Inputs (normalized)
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


# ------------------------------
# NEW: Save RAW input snapshots
# ------------------------------
def save_raw_inputs_snapshot(
    ws_root: Path,
    workspace_name: str,
    *,
    account_id: str,
    store_id: str,
    platform_hint: str = "",
    raw_orders: pd.DataFrame,
    raw_shipments: pd.DataFrame,
    raw_tracking: pd.DataFrame | None = None,
    note: str = "",
    source: str = "demo_fork",
) -> Path:
    """
    Saves the *raw* (pre-normalize) inputs as a "snapshot run" under a workspace.
    This does NOT replace your normal save_run(); it complements it.

    Output files written:
      - raw_orders.csv
      - raw_shipments.csv
      - raw_tracking.csv (optional, written even if empty for consistency)
      - meta.json

    You can use this to preserve demo edits even before running a pipeline,
    and without touching app.py.
    """
    workspace_name = safe_slug(workspace_name)
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "_raw"
    run_dir = ws_root / workspace_name / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (raw_orders if isinstance(raw_orders, pd.DataFrame) else pd.DataFrame()).to_csv(
        run_dir / "raw_orders.csv", index=False
    )
    (raw_shipments if isinstance(raw_shipments, pd.DataFrame) else pd.DataFrame()).to_csv(
        run_dir / "raw_shipments.csv", index=False
    )
    rt = raw_tracking if isinstance(raw_tracking, pd.DataFrame) else pd.DataFrame()
    rt.to_csv(run_dir / "raw_tracking.csv", index=False)

    meta = {
        "created_at": run_id,
        "workspace_name": workspace_name,
        "account_id": account_id,
        "store_id": store_id,
        "platform_hint": platform_hint,
        "source": source,
        "note": note,
        "row_counts": {
            "raw_orders": int(len(raw_orders)) if isinstance(raw_orders, pd.DataFrame) else 0,
            "raw_shipments": int(len(raw_shipments)) if isinstance(raw_shipments, pd.DataFrame) else 0,
            "raw_tracking": int(len(rt)),
        },
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return run_dir


# ------------------------------
# NEW: Convert RAW snapshot -> full run (safe, additive)
# ------------------------------
def convert_raw_snapshot_to_full_run(
    *,
    ws_root: Path,
    snapshot_dir: Path,
    target_workspace_name: str,
    account_id: str,
    store_id: str,
    platform_hint: str = "",
    note: str = "",
) -> tuple[Path | None, str | None]:
    """
    Converts a RAW snapshot folder (containing raw_orders.csv/raw_shipments.csv[/raw_tracking.csv])
    into a standard "full run" folder by reusing existing save_run().

    IMPORTANT:
      - This does not attempt to run the pipeline. It preserves RAW inputs by storing them into
        the "normalized" slots (orders_normalized.csv, etc.) so the run is loadable everywhere.
      - All other run outputs are saved as empty DataFrames (exceptions/followups/etc.) to keep
        backward compatibility and avoid crashes.

    Returns:
      (new_run_dir | None, error_message | None)
    """
    try:
        snapshot_dir = Path(snapshot_dir)
        if not snapshot_dir.exists() or not snapshot_dir.is_dir():
            return None, f"Snapshot folder not found: {snapshot_dir.as_posix()}"

        raw_orders_path = snapshot_dir / "raw_orders.csv"
        raw_shipments_path = snapshot_dir / "raw_shipments.csv"
        raw_tracking_path = snapshot_dir / "raw_tracking.csv"

        missing = [p.name for p in [raw_orders_path, raw_shipments_path] if not p.exists()]
        if missing:
            return None, "Snapshot missing required file(s): " + ", ".join(missing)

        raw_orders = pd.read_csv(raw_orders_path)
        raw_shipments = pd.read_csv(raw_shipments_path)
        raw_tracking = pd.read_csv(raw_tracking_path) if raw_tracking_path.exists() else pd.DataFrame()

        # Save as a standard run with empty outputs (safe placeholders)
        empty = pd.DataFrame()
        run_dir = save_run(
            ws_root=ws_root,
            workspace_name=target_workspace_name,
            account_id=account_id,
            store_id=store_id,
            platform_hint=platform_hint or "",
            orders=raw_orders,
            shipments=raw_shipments,
            tracking=raw_tracking,
            exceptions=empty,
            followups=empty,
            order_rollup=empty,
            line_status_df=empty,
            kpis={},
            suppliers_df=empty,
        )

        # Enrich meta to indicate conversion provenance (non-breaking)
        try:
            meta_path = run_dir / "meta.json"
            meta = {}
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = meta or {}
            meta["source"] = "converted_from_raw_snapshot"
            meta["source_snapshot_dir"] = snapshot_dir.as_posix()
            if note:
                meta["note"] = note
            (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            # non-critical
            pass

        return run_dir, None

    except Exception as e:
        return None, str(e)


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

    # Standard outputs / inputs
    out["exceptions"] = _read_csv("exceptions.csv")
    out["followups"] = _read_csv("followups.csv")
    out["order_rollup"] = _read_csv("order_rollup.csv")
    out["line_status_df"] = _read_csv("line_status.csv")
    out["orders"] = _read_csv("orders_normalized.csv")
    out["shipments"] = _read_csv("shipments_normalized.csv")
    out["tracking"] = _read_csv("tracking_normalized.csv")
    out["suppliers_df"] = _read_csv("suppliers.csv")

    # Raw snapshot files (if present)
    out["raw_orders"] = _read_csv("raw_orders.csv")
    out["raw_shipments"] = _read_csv("raw_shipments.csv")
    out["raw_tracking"] = _read_csv("raw_tracking.csv")
    return out


