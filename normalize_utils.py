from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
from dateutil import parser


@dataclass(frozen=True)
class ColumnRule:
    name: str
    required: bool = True
    alt: Optional[list[str]] = None


def clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def lower_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    return out


def to_utc(series: pd.Series) -> pd.Series:
    """Parse mixed datetime strings -> timezone-aware UTC timestamps."""

    def parse_one(x):
        if pd.isna(x) or str(x).strip() == "":
            return pd.NaT
        try:
            dt = parser.parse(str(x))
            if dt.tzinfo is None:
                # assume already UTC if no tz given
                return pd.Timestamp(dt).tz_localize("UTC")
            return pd.Timestamp(dt).tz_convert("UTC")
        except Exception:
            return pd.NaT

    return series.apply(parse_one)


def to_int(series: pd.Series, default: int = 0) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce").fillna(default).astype(int)
    return out


def to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)


def safe_str(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def validation(errors: List[str]) -> Dict[str, Any]:
    return {"ok": len(errors) == 0, "errors": errors}


def require_cols(df: pd.DataFrame, rules: List[ColumnRule], table: str) -> List[str]:
    errs: List[str] = []
    cols = set([c.lower() for c in df.columns])

    for rule in rules:
        names = [rule.name] + (rule.alt or [])
        present = any(n.lower() in cols for n in names)
        if rule.required and not present:
            errs.append(f"{table}: missing required column '{rule.name}'")

    return errs
