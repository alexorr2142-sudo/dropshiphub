# core/suppliers.py
from __future__ import annotations

from pathlib import Path
import pandas as pd

from core.workspaces import safe_slug


def normalize_supplier_key(s: str) -> str:
    return (str(s) if s is not None else "").strip().lower()


def suppliers_path(suppliers_dir: Path, account_id: str, store_id: str) -> Path:
    return suppliers_dir / safe_slug(account_id) / safe_slug(store_id) / "suppliers.csv"


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
    (df if isinstance(df, pd.DataFrame) else pd.DataFrame()).to_csv(p, index=False)
    return p


def enrich_followups_with_suppliers(followups: pd.DataFrame, suppliers_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-joins supplier directory fields onto followups by normalized supplier_name.

    Adds / fills:
      - supplier_email
      - supplier_channel
      - language
      - timezone

    Never crashes; returns original followups on any mismatch.
    """
    if followups is None or not isinstance(followups, pd.DataFrame) or followups.empty:
        return followups
    if suppliers_df is None or not isinstance(suppliers_df, pd.DataFrame) or suppliers_df.empty:
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

    # If directory has none of the enrichment cols, return as-is
    if cols == ["_supplier_key"]:
        return followups

    s2 = s[cols].drop_duplicates(subset=["_supplier_key"])
    merged = f.merge(s2, on="_supplier_key", how="left", suffixes=("", "_crm"))

    # Fill supplier_email if blank / missing
    crm_email = merged.get("supplier_email_crm", pd.Series([""] * len(merged), index=merged.index)).fillna("")
    if "supplier_email" in merged.columns:
        merged["supplier_email"] = merged["supplier_email"].fillna("")
        merged["supplier_email"] = merged["supplier_email"].where(
            merged["supplier_email"].astype(str).str.strip() != "",
            crm_email,
        )
    else:
        merged["supplier_email"] = crm_email

    # Copy other CRM fields if they didn't exist on followups
    for c in ["supplier_channel", "language", "timezone"]:
        crm_col = f"{c}_crm"
        if c not in merged.columns and crm_col in merged.columns:
            merged[c] = merged[crm_col]

    # Cleanup
    drop_cols = [c for c in merged.columns if c.endswith("_crm")] + ["_supplier_key"]
    merged = merged.drop(columns=[c for c in drop_cols if c in merged.columns], errors="ignore")

    return merged


def add_missing_supplier_contact_exceptions(exceptions: pd.DataFrame, followups: pd.DataFrame) -> pd.DataFrame:
    """
    If any followup row requires action (item_count > 0 when present) but has no supplier_email,
    injects a synthetic exception row per supplier to prompt filling the Supplier Directory.
    """
    if followups is None or not isinstance(followups, pd.DataFrame) or followups.empty:
        return exceptions

    f = followups.copy()
    if "supplier_name" not in f.columns:
        return exceptions

    # Determine which followups "need" contact
    needs = pd.Series(True, index=f.index)
    if "item_count" in f.columns:
        try:
            needs = f["item_count"].fillna(0).astype(float) > 0
        except Exception:
            needs = pd.Series(True, index=f.index)

    email = f.get("supplier_email", pd.Series("", index=f.index)).fillna("").astype(str).str.strip()
    missing = needs & (email == "")
    if int(missing.sum()) == 0:
        return exceptions

    missing_suppliers = sorted(f.loc[missing, "supplier_name"].dropna().astype(str).unique().tolist())
    rows = [
        {
            "order_id": "",
            "sku": "",
            "issue_type": "Missing supplier contact",
            "customer_country": "",
            "supplier_name": sname,
            "quantity_ordered": "",
            "quantity_shipped": "",
            "line_status": "",
            "explanation": (
                "A supplier follow-up is needed, but this supplier has no email saved in the Supplier Directory."
            ),
            "next_action": "Add supplier_email in Supplier Directory (upload suppliers.csv) or update the CRM row.",
            "customer_risk": "Medium",
        }
        for sname in missing_suppliers
    ]
    add_df = pd.DataFrame(rows)

    if exceptions is None or not isinstance(exceptions, pd.DataFrame) or exceptions.empty:
        return add_df

    return pd.concat([exceptions, add_df], ignore_index=True, sort=False)
