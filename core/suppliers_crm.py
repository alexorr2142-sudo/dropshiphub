# core/suppliers_crm.py
from __future__ import annotations

from pathlib import Path
import pandas as pd


# -------------------------------
# Workspace-safe slugging
# -------------------------------
def _safe_slug(s: str) -> str:
    s = (s or "").strip()
    keep = []
    for ch in s:
        if ch.isalnum() or ch in ["-", "_", " "]:
            keep.append(ch)
    out = "".join(keep).strip().replace(" ", "_")
    return out[:60] if out else "workspace"


def suppliers_path(suppliers_dir: Path, account_id: str, store_id: str) -> Path:
    return suppliers_dir / _safe_slug(account_id) / _safe_slug(store_id) / "suppliers.csv"


# -------------------------------
# Load / Save
# -------------------------------
def load_suppliers(suppliers_dir: Path, account_id: str, store_id: str) -> pd.DataFrame:
    p = suppliers_path(suppliers_dir, account_id, store_id)
    if p.exists():
        try:
            return pd.read_csv(p)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def save_suppliers(suppliers_dir: Path, account_id: str, store_id: str, df: pd.DataFrame) -> Path:
    p = suppliers_path(suppliers_dir, account_id, store_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)
    return p


# -------------------------------
# Styling
# -------------------------------
def style_supplier_table(df: pd.DataFrame):
    """
    Highlights suppliers missing supplier_email.
    Returns a Styler.
    """
    if df is None or df.empty or "supplier_email" not in df.columns:
        return df.style if hasattr(df, "style") else df

    def _row_style(row):
        email = str(row.get("supplier_email", "")).strip()
        if email == "" or email.lower() in ["nan", "none"]:
            return ["background-color: #fff1cc;"] * len(row)
        return [""] * len(row)

    return df.style.apply(_row_style, axis=1)


# -------------------------------
# Followup enrichment
# -------------------------------
def normalize_supplier_key(s: str) -> str:
    return (str(s) if s is not None else "").strip().lower()


def enrich_followups_with_suppliers(followups: pd.DataFrame, suppliers_df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds supplier_email/channel/language/timezone to followups by supplier_name match.
    Does not crash if columns are missing.
    """
    if followups is None or followups.empty or suppliers_df is None or suppliers_df.empty:
        return followups

    f = followups.copy()
    s = suppliers_df.copy()

    if "supplier_name" not in f.columns or "supplier_name" not in s.columns:
        return followups

    f["_supplier_key"] = f["supplier_name"].map(normalize_supplier_key)
    s["_supplier_key"] = s["supplier_name"].map(normalize_supplier_key)

    cols = ["_supplier_key"]
    for c in ["supplier_email", "supplier_channel", "language", "timezone"]:
        if c in s.columns:
            cols.append(c)

    s2 = s[cols].drop_duplicates(subset=["_supplier_key"])

    merged = f.merge(s2, on="_supplier_key", how="left", suffixes=("", "_crm"))

    # Prefer followups supplier_email unless blank; then fill from CRM
    if "supplier_email" in f.columns:
        merged["supplier_email"] = merged["supplier_email"].fillna("").astype(str)
        merged["supplier_email"] = merged["supplier_email"].where(
            merged["supplier_email"].str.strip() != "",
            merged.get("supplier_email_crm", "").fillna("").astype(str),
        )
    else:
        merged["supplier_email"] = merged.get("supplier_email_crm", "").fillna("").astype(str)

    # Add other CRM fields if missing in followups
    for c in ["supplier_channel", "language", "timezone"]:
        if c not in merged.columns and f"{c}_crm" in merged.columns:
            merged[c] = merged[f"{c}_crm"]

    drop_cols = [c for c in merged.columns if c.endswith("_crm")] + ["_supplier_key"]
    merged = merged.drop(columns=[c for c in drop_cols if c in merged.columns])

    return merged


# -------------------------------
# Exceptions: missing supplier contact
# -------------------------------
def add_missing_supplier_contact_exceptions(exceptions: pd.DataFrame, followups: pd.DataFrame) -> pd.DataFrame:
    """
    Adds exceptions rows for suppliers who need followup but have no supplier_email.
    """
    if followups is None or followups.empty:
        return exceptions

    f = followups.copy()
    if "supplier_name" not in f.columns:
        return exceptions

    # Determine which followups are meaningful
    needs = pd.Series([True] * len(f))
    if "item_count" in f.columns:
        try:
            needs = pd.to_numeric(f["item_count"], errors="coerce").fillna(0) > 0
        except Exception:
            needs = pd.Series([True] * len(f))

    email = f.get("supplier_email", pd.Series([""] * len(f))).fillna("").astype(str).str.strip()
    missing = needs & (email == "")
    if missing.sum() == 0:
        return exceptions

    missing_suppliers = sorted(f.loc[missing, "supplier_name"].dropna().unique().tolist())
    rows = []
    for sname in missing_suppliers:
        rows.append(
            {
                "order_id": "",
                "sku": "",
                "issue_type": "Missing supplier contact",
                "customer_country": "",
                "supplier_name": sname,
                "quantity_ordered": "",
                "quantity_shipped": "",
                "line_status": "",
                "explanation": "A supplier follow-up is needed, but this supplier has no email saved in the Supplier Directory.",
                "next_action": "Add supplier_email in Supplier Directory (upload suppliers.csv) or update the CRM row.",
                "customer_risk": "Medium",
            }
        )

    add_df = pd.DataFrame(rows)

    if exceptions is None or exceptions.empty:
        return add_df

    return pd.concat([exceptions, add_df], ignore_index=True, sort=False)
