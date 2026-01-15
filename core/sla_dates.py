# core/sla_dates.py
from __future__ import annotations

import pandas as pd


def _pick_first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def add_sla_dates_to_line_status(
    line_status_df: pd.DataFrame,
    orders: pd.DataFrame,
) -> pd.DataFrame:
    """
    Ensures line_status_df includes at least one usable date column for SLA escalations.

    We try to bring over:
      - promised ship / ship-by style columns (preferred)
      - order created date columns (fallback)

    This is safe:
      - If columns don't exist, it does nothing.
      - If order_id missing, it does nothing.
      - It won't crash if weird data exists.
    """
    if line_status_df is None or line_status_df.empty:
        return line_status_df
    if orders is None or orders.empty:
        return line_status_df
    if "order_id" not in line_status_df.columns or "order_id" not in orders.columns:
        return line_status_df

    # Prefer promised / ship-by columns (best for SLA)
    promised_candidates = [
        "promised_ship_date",
        "promised_ship_at",
        "sla_due_date",
        "ship_by_date",
    ]

    # Fallback: created/order date columns
    created_candidates = [
        "order_created_at",
        "order_date",
        "created_at",
        "created_datetime",
        "created",
    ]

    promised_col = _pick_first_col(orders, promised_candidates)
    created_col = _pick_first_col(orders, created_candidates)

    # Build merge cols based on what actually exists
    merge_cols = ["order_id"]
    if promised_col:
        merge_cols.append(promised_col)
    if created_col and created_col not in merge_cols:
        merge_cols.append(created_col)

    # Nothing useful to add
    if len(merge_cols) <= 1:
        return line_status_df

    # Drop duplicates on orders to keep merge clean
    o = orders[merge_cols].drop_duplicates(subset=["order_id"]).copy()

    # Merge onto line_status_df
    out = line_status_df.merge(o, on="order_id", how="left")

    return out
