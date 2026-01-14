# core/suppliers.py
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
    df.to_csv(p, index=False)
    return p

def enrich_followups_with_suppliers(followups: pd.DataFrame, suppliers_df: pd.DataFrame) -> pd.DataFrame:
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

    if "supplier_email" in f.columns:
        merged["supplier_email"] = merged["supplier_email"].fillna("")
        merged["supplier_email"] = merged["supplier_email"].where(
            merged["supplier_email"].astype(str).str.strip() != "",
            merged.get("supplier_email_crm", "").fillna(""),
        )
    else:
        merged["supplier_email"] = merged.get("supplier_email_crm", "").fillna("")

    for c in ["supplier_channel", "language", "timezone"]:
        if c not in merged.columns and f"{c}_crm" in merged.columns:
            merged[c] = merged[f"{c}_crm"]

    drop_cols = [c for c in merged.columns if c.endswith("_crm")] + ["_supplier_key"]
    merged = merged.drop(columns=[c for c in drop_cols if c in merged.columns])

    return merged

def add_missing_supplier_contact_exceptions(exceptions: pd.DataFrame, followups: pd.DataFrame) -> pd.DataFrame:
    if followups is None or followups.empty:
        return exceptions

    f = followups.copy()
    if "supplier_name" not in f.columns:
        return exceptions

    needs = pd.Series([True] * len(f))
    if "item_count" in f.columns:
        try:
            needs = f["item_count"].fillna(0).astype(float) > 0
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
