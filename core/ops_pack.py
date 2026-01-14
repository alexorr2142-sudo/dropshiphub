# core/ops_pack.py
import io
import json
import zipfile
import pandas as pd

def make_daily_ops_pack_bytes(
    exceptions: pd.DataFrame,
    followups: pd.DataFrame,
    order_rollup: pd.DataFrame,
    line_status_df: pd.DataFrame,
    kpis: dict,
    supplier_scorecards: pd.DataFrame | None = None,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("exceptions.csv", (exceptions if exceptions is not None else pd.DataFrame()).to_csv(index=False))
        z.writestr("supplier_followups.csv", (followups if followups is not None else pd.DataFrame()).to_csv(index=False))
        z.writestr("order_rollup.csv", (order_rollup if order_rollup is not None else pd.DataFrame()).to_csv(index=False))
        z.writestr("order_line_status.csv", (line_status_df if line_status_df is not None else pd.DataFrame()).to_csv(index=False))

        if supplier_scorecards is not None and not supplier_scorecards.empty:
            z.writestr("supplier_scorecards.csv", supplier_scorecards.to_csv(index=False))

        z.writestr("kpis.json", json.dumps(kpis if isinstance(kpis, dict) else {}, indent=2))

        z.writestr(
            "README.txt",
            (
                "Dropship Hub — Daily Ops Pack\n"
                "Files:\n"
                " - exceptions.csv: SKU-level issues to action\n"
                " - supplier_followups.csv: supplier messages to send\n"
                " - order_rollup.csv: one row per order\n"
                " - order_line_status.csv: full line-level status\n"
                " - supplier_scorecards.csv: per-supplier performance snapshot (if available)\n"
                " - kpis.json: dashboard KPI snapshot\n"
            ),
        )
    buf.seek(0)
    return buf.read()
