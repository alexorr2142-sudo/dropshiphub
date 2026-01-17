# core/ops_pack.py
from __future__ import annotations

import io
import json
import zipfile
from typing import Optional

import pandas as pd


def _df_or_empty(x) -> pd.DataFrame:
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()


def make_daily_ops_pack_bytes(
    exceptions: pd.DataFrame,
    followups: pd.DataFrame,
    order_rollup: pd.DataFrame,
    line_status_df: pd.DataFrame,
    kpis: dict,
    supplier_scorecards: Optional[pd.DataFrame] = None,
    customer_impact: Optional[pd.DataFrame] = None,
) -> bytes:
    """
    Creates the Daily Ops Pack ZIP bytes.

    Contents (best effort):
      - exceptions.csv
      - supplier_followups.csv
      - order_rollup.csv
      - order_line_status.csv
      - supplier_scorecards.csv (optional)
      - customer_impact.csv (optional)
      - kpis.json
      - README.txt
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("exceptions.csv", _df_or_empty(exceptions).to_csv(index=False))
        z.writestr("supplier_followups.csv", _df_or_empty(followups).to_csv(index=False))
        z.writestr("order_rollup.csv", _df_or_empty(order_rollup).to_csv(index=False))
        z.writestr("order_line_status.csv", _df_or_empty(line_status_df).to_csv(index=False))

        if isinstance(supplier_scorecards, pd.DataFrame) and not supplier_scorecards.empty:
            z.writestr("supplier_scorecards.csv", supplier_scorecards.to_csv(index=False))

        if isinstance(customer_impact, pd.DataFrame) and not customer_impact.empty:
            z.writestr("customer_impact.csv", customer_impact.to_csv(index=False))

        z.writestr("kpis.json", json.dumps(kpis if isinstance(kpis, dict) else {}, indent=2))

        z.writestr(
            "README.txt",
            (
                "ClearOps — Daily Ops Pack\n"
                "Files:\n"
                " - exceptions.csv: SKU-level issues to action\n"
                " - supplier_followups.csv: supplier messages to send (OPEN/unresolved)\n"
                " - order_rollup.csv: one row per order\n"
                " - order_line_status.csv: full line-level status\n"
                " - supplier_scorecards.csv: per-supplier performance snapshot (if available)\n"
                " - customer_impact.csv: customer comms candidates (if available)\n"
                " - kpis.json: dashboard KPI snapshot\n"
            ),
        )
    buf.seek(0)
    return buf.read()
