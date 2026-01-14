# app.py
import os
import json
import io
import zipfile
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# --- Local modules (your repo files) ---
try:
    from normalize import normalize_orders, normalize_shipments, normalize_tracking
    from reconcile import reconcile_all
    from explain import enhance_explanations
except Exception as e:
    st.set_page_config(page_title="Dropship Hub", layout="wide")
    st.title("Dropship Hub")
    st.error("Import error: one of your local .py files is missing or has an error.")
    st.code(str(e))
    st.stop()


# -------------------------------
# Clipboard / Copy buttons
# -------------------------------
def copy_button(text: str, label: str, key: str):
    safe_text = (
        str(text)
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )
    html = f"""
    <div style="margin: 0.25rem 0;">
      <button
        id="btn-{key}"
        style="
          padding: 0.45rem 0.75rem;
          border-radius: 0.5rem;
          border: 1px solid rgba(49, 51, 63, 0.2);
          background: white;
          cursor: pointer;
          font-size: 0.9rem;
        "
        onclick="navigator.clipboard.writeText(`{safe_text}`)
          .then(() => {{
            const b = document.getElementById('btn-{key}');
            const old = b.innerText;
            b.innerText = 'Copied ✅';
            setTimeout(() => b.innerText = old, 1200);
          }})
          .catch(() => alert('Copy failed. Your browser may block clipboard access.'));">
        {label}
      </button>
    </div>
    """
    components.html(html, height=55)


# -------------------------------
# Exceptions urgency + styling (Step B)
# -------------------------------
def add_urgency_column(exceptions_df: pd.DataFrame) -> pd.DataFrame:
    df = exceptions_df.copy()

    def classify_row(row) -> str:
        issue_type = str(row.get("issue_type", "")).lower()
        explanation = str(row.get("explanation", "")).lower()
        next_action = str(row.get("next_action", "")).lower()
        risk = str(row.get("customer_risk", "")).lower()
        line_status = str(row.get("line_status", "")).lower()
        blob = " ".join([issue_type, explanation, next_action, risk, line_status])

        critical_terms = [
            "late", "past due", "overdue", "late unshipped",
            "missing tracking", "no tracking", "tracking missing",
            "carrier exception", "exception", "lost", "stuck", "seized",
            "returned to sender", "address missing", "missing address",
        ]
        if any(t in blob for t in critical_terms):
            return "Critical"

        high_terms = [
            "partial", "partial shipment",
            "mismatch", "quantity mismatch",
            "invalid tracking", "tracking invalid",
            "carrier unknown", "unknown carrier",
        ]
        if any(t in blob for t in high_terms):
            return "High"

        medium_terms = ["verify", "check", "confirm", "format", "invalid", "missing", "contact"]
        if any(t in blob for t in medium_terms):
            return "Medium"

        return "Low"

    df["Urgency"] = df.apply(classify_row, axis=1)
    df["Urgency"] = pd.Categorical(
        df["Urgency"],
        categories=["Critical", "High", "Medium", "Low"],
        ordered=True,
    )
    return df


def style_exceptions_table(df: pd.DataFrame):
    if "Urgency" not in df.columns:
        return df.style

    colors = {
        "Critical": "background-color: #ffd6d6;",
        "High": "background-color: #fff1cc;",
        "Medium": "background-color: #f3f3f3;",
        "Low": ""
    }

    def row_style(row):
        u = str(row.get("Urgency", "Low"))
        return [colors.get(u, "")] * len(row)

    return df.style.apply(row_style, axis=1)


# -------------------------------
# Basic auth helpers (Step C)
# (You want "accept all emails" -> keep allowlist empty)
# -------------------------------
def _parse_allowed_emails_from_env() -> list[str]:
    raw = os.getenv("DSH_ALLOWED_EMAILS", "").strip()
    if not raw:
        return []
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def get_allowed_emails() -> list[str]:
    allowed = []
    try:
        allowed = st.secrets.get("ALLOWED_EMAILS", [])
        if isinstance(allowed, str):
            allowed = [allowed]
        allowed = [str(e).strip().lower() for e in allowed if str(e).strip()]
    except Exception:
        allowed = []
    allowed_env = _parse_allowed_emails_from_env()
    return sorted(set(allowed + allowed_env))


def require_email_access_gate():
    st.subheader("Access")
    _ = st.text_input("Work email", key="auth_email").strip().lower()

    allowed = get_allowed_emails()
    if allowed:
        if not _:
            st.info("Enter your work email to continue.")
            st.stop()
        if _ not in allowed:
            st.error("This email is not authorized for early access.")
            st.caption("Ask the admin to add your email to the allowlist.")
            st.stop()
        st.success("Email verified ✅")
    else:
        # Accept all emails (your requested behavior)
        st.caption("Email verification is currently disabled (accepting all emails).")


# -------------------------------
# Step 7/7.5: Workspaces (Save/Load/History/Delete)
# -------------------------------
def _safe_slug(s: str) -> str:
    s = (s or "").strip()
    keep = []
    for ch in s:
        if ch.isalnum() or ch in ["-", "_", " "]:
            keep.append(ch)
    out = "".join(keep).strip().replace(" ", "_")
    return out[:60] if out else "workspace"


def workspace_root(workspaces_dir: Path, account_id: str, store_id: str) -> Path:
    return workspaces_dir / _safe_slug(account_id) / _safe_slug(store_id)


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
    workspace_name = _safe_slug(workspace_name)
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_dir = ws_root / workspace_name / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Outputs
    exceptions.to_csv(run_dir / "exceptions.csv", index=False)
    followups.to_csv(run_dir / "followups.csv", index=False)
    order_rollup.to_csv(run_dir / "order_rollup.csv", index=False)
    line_status_df.to_csv(run_dir / "line_status.csv", index=False)

    # Inputs (debug/repeatability)
    orders.to_csv(run_dir / "orders_normalized.csv", index=False)
    shipments.to_csv(run_dir / "shipments_normalized.csv", index=False)
    tracking.to_csv(run_dir / "tracking_normalized.csv", index=False)

    # Supplier CRM snapshot
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


# -------------------------------
# Supplier CRM (Step 8)
# -------------------------------
def normalize_supplier_key(s: str) -> str:
    return (str(s) if s is not None else "").strip().lower()


def suppliers_path(suppliers_dir: Path, account_id: str, store_id: str) -> Path:
    return suppliers_dir / _safe_slug(account_id) / _safe_slug(store_id) / "suppliers.csv"


def load_suppliers(suppliers_dir: Path, account_id: str, store_id: str) -> pd.DataFrame:
    p = suppliers_path(suppliers_dir, account_id, store_id)
    if p.exists():
        try:
            df = pd.read_csv(p)
            return df
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def save_suppliers(suppliers_dir: Path, account_id: str, store_id: str, df: pd.DataFrame) -> Path:
    p = suppliers_path(suppliers_dir, account_id, store_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)
    return p


def style_supplier_table(df: pd.DataFrame):
    # highlight missing emails
    if "supplier_email" not in df.columns:
        return df.style

    def _row_style(row):
        email = str(row.get("supplier_email", "")).strip()
        if email == "" or email.lower() in ["nan", "none"]:
            return ["background-color: #fff1cc;"] * len(row)
        return [""] * len(row)

    return df.style.apply(_row_style, axis=1)


def enrich_followups_with_suppliers(followups: pd.DataFrame, suppliers_df: pd.DataFrame) -> pd.DataFrame:
    if followups is None or followups.empty or suppliers_df is None or suppliers_df.empty:
        return followups

    f = followups.copy()
    s = suppliers_df.copy()

    if "supplier_name" not in f.columns or "supplier_name" not in s.columns:
        return followups

    # normalize key
    f["_supplier_key"] = f["supplier_name"].map(normalize_supplier_key)
    s["_supplier_key"] = s["supplier_name"].map(normalize_supplier_key)

    # keep only relevant columns
    cols = ["_supplier_key"]
    for c in ["supplier_email", "supplier_channel", "language", "timezone"]:
        if c in s.columns:
            cols.append(c)
    s2 = s[cols].drop_duplicates(subset=["_supplier_key"])

    merged = f.merge(s2, on="_supplier_key", how="left", suffixes=("", "_crm"))

    # Fill/overwrite supplier_email if missing
    if "supplier_email" in f.columns:
        merged["supplier_email"] = merged["supplier_email"].fillna("")
        merged["supplier_email"] = merged["supplier_email"].where(
            merged["supplier_email"].astype(str).str.strip() != "",
            merged.get("supplier_email_crm", "").fillna(""),
        )
    else:
        merged["supplier_email"] = merged.get("supplier_email_crm", "").fillna("")

    # bring other CRM fields if not already present
    for c in ["supplier_channel", "language", "timezone"]:
        if c in merged.columns:
            continue
        if f"{c}_crm" in merged.columns:
            merged[c] = merged[f"{c}_crm"]

    # cleanup
    drop_cols = [c for c in merged.columns if c.endswith("_crm")] + ["_supplier_key"]
    merged = merged.drop(columns=[c for c in drop_cols if c in merged.columns])

    return merged


def add_missing_supplier_contact_exceptions(exceptions: pd.DataFrame, followups: pd.DataFrame) -> pd.DataFrame:
    """
    If a supplier needs a follow-up but has no email after CRM merge, create an exception row.
    """
    if followups is None or followups.empty:
        return exceptions

    f = followups.copy()

    if "supplier_name" not in f.columns:
        return exceptions

    # consider a supplier "needs follow-up" if item_count exists and > 0; otherwise if body exists.
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

    # concat with alignment
    return pd.concat([exceptions, add_df], ignore_index=True, sort=False)


# -------------------------------
# Page setup
# -------------------------------
st.set_page_config(page_title="Dropship Hub", layout="wide")

# -------------------------------
# Early Access Gate
# -------------------------------
ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")

st.title("Dropship Hub — Early Access")
st.caption("Drop ship made easy — exceptions, follow-ups, and visibility in one hub.")

code = st.text_input("Enter early access code", type="password", key="access_code")

if code != ACCESS_CODE:
    st.info("This app is currently in early access. Enter your code to continue.")
    st.stop()

# Email gate (accept-all mode)
require_email_access_gate()

# -------------------------------
# Paths
# -------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# Ensure workspaces dir exists (and isn't a file)
WORKSPACES_DIR = DATA_DIR / "workspaces"
if WORKSPACES_DIR.exists() and not WORKSPACES_DIR.is_dir():
    st.error(
        "Workspace storage path is invalid: `data/workspaces` exists but is a FILE, not a folder.\n\n"
        "Fix: delete or rename `data/workspaces` in your repo, then redeploy."
    )
    st.stop()
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

# Ensure suppliers dir exists (and isn't a file)
SUPPLIERS_DIR = DATA_DIR / "suppliers"
if SUPPLIERS_DIR.exists() and not SUPPLIERS_DIR.is_dir():
    st.error(
        "Supplier storage path is invalid: `data/suppliers` exists but is a FILE, not a folder.\n\n"
        "Fix: delete or rename `data/suppliers` in your repo, then redeploy."
    )
    st.stop()
SUPPLIERS_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------
# Sidebar: plan + tenant + defaults + Supplier CRM
# -------------------------------
with st.sidebar:
    st.header("Plan")
    _plan = st.selectbox("Current plan", ["Early Access (Free)", "Pro", "Team"], index=0)
    with st.expander("Upgrade / Pricing (placeholder)", expanded=False):
        st.markdown(
            """
**Early Access (Free)**
- CSV uploads
- Exceptions + supplier follow-ups
- Supplier Directory (CRM)

**Pro**
- Saved workspaces + run history
- Supplier scorecards (coming soon)
- Automations (coming soon)

**Team**
- Role-based access (coming soon)
- Audit trail (coming soon)
- Shared templates (coming soon)
            """.strip()
        )

    st.divider()
    st.header("Tenant")
    account_id = st.text_input("account_id", value="demo_account")
    store_id = st.text_input("store_id", value="demo_store")
    platform_hint = st.selectbox("platform hint", ["shopify", "amazon", "etsy", "other"], index=0)

    st.divider()
    st.header("Defaults")
    default_currency = st.text_input("Default currency", value="USD")
    default_promised_ship_days = st.number_input(
        "Default promised ship days (SLA)",
        min_value=1,
        max_value=30,
        value=3,
    )

    st.divider()
    st.header("Supplier Directory (CRM)")

    # Load any previously saved suppliers for this tenant
    if "suppliers_df" not in st.session_state:
        st.session_state["suppliers_df"] = load_suppliers(SUPPLIERS_DIR, account_id, store_id)

    f_suppliers = st.file_uploader("Upload suppliers.csv", type=["csv"], key="suppliers_uploader")
    if f_suppliers is not None:
        try:
            uploaded_suppliers = pd.read_csv(f_suppliers)
            st.session_state["suppliers_df"] = uploaded_suppliers
            p = save_suppliers(SUPPLIERS_DIR, account_id, store_id, uploaded_suppliers)
            st.success(f"Saved ✅ {p.as_posix()}")
        except Exception as e:
            st.error("Failed to read suppliers CSV.")
            st.code(str(e))

    with st.expander("View Supplier Directory", expanded=False):
        suppliers_df = st.session_state.get("suppliers_df", pd.DataFrame())
        if suppliers_df is None or suppliers_df.empty:
            st.caption("No supplier directory loaded yet. Upload suppliers.csv to auto-fill follow-up emails.")
        else:
            show_cols = [c for c in ["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"] if c in suppliers_df.columns]
            if not show_cols:
                st.dataframe(suppliers_df, use_container_width=True, height=220)
            else:
                st.dataframe(style_supplier_table(suppliers_df[show_cols]), use_container_width=True, height=220)

            # quick stats
            if "supplier_email" in suppliers_df.columns:
                missing_emails = suppliers_df["supplier_email"].fillna("").astype(str).str.strip().eq("").sum()
                st.caption(f"Missing supplier_email: {int(missing_emails)} row(s) (highlighted)")

    st.divider()
    st.caption("Tip: Upload suppliers.csv once per account/store to auto-fill follow-up emails.")

# Pull into local variable after sidebar is defined
suppliers_df = st.session_state.get("suppliers_df", pd.DataFrame())

# -------------------------------
# Onboarding checklist
# -------------------------------
st.divider()
with st.expander("Onboarding checklist", expanded=True):
    st.markdown(
        """
1. Click **Try demo data** to see the workflow instantly  
2. Upload **Orders CSV** (Shopify export)  
3. Upload **Shipments CSV** (supplier / agent export)  
4. (Optional) Upload **Tracking CSV**  
5. Review **Exceptions** and use **Supplier Follow-ups** to message suppliers  
6. (Optional) Upload **suppliers.csv** to auto-fill supplier emails and channels  
        """.strip()
    )

# -------------------------------
# Demo Mode
# -------------------------------
st.subheader("Start here")
use_demo = st.button("Try demo data (no uploads)")

raw_orders = None
raw_shipments = None
raw_tracking = None

if use_demo:
    try:
        raw_orders = pd.read_csv(DATA_DIR / "raw_orders.csv")
        raw_shipments = pd.read_csv(DATA_DIR / "raw_shipments.csv")
        raw_tracking = pd.read_csv(DATA_DIR / "raw_tracking.csv")
        st.success("Demo data loaded ✅")
    except Exception as e:
        st.error("Couldn't load demo data. Make sure data/raw_orders.csv, raw_shipments.csv, raw_tracking.csv exist.")
        st.code(str(e))
        st.stop()

# -------------------------------
# Upload section
# -------------------------------
st.divider()
st.subheader("Upload your data")

col1, col2, col3 = st.columns(3)
with col1:
    f_orders = st.file_uploader("Orders CSV (Shopify export or generic)", type=["csv"])
with col2:
    f_shipments = st.file_uploader("Shipments CSV (supplier export)", type=["csv"])
with col3:
    f_tracking = st.file_uploader("Tracking CSV (optional)", type=["csv"])

# -------------------------------
# Template downloads
# -------------------------------
st.subheader("Download templates")

shipments_template = pd.DataFrame(
    columns=[
        "Supplier",
        "Supplier Order ID",
        "Order ID",
        "SKU",
        "Quantity",
        "Ship Date",
        "Carrier",
        "Tracking",
        "From Country",
        "To Country",
    ]
)

tracking_template = pd.DataFrame(
    columns=[
        "Carrier",
        "Tracking Number",
        "Order ID",
        "Supplier Order ID",
        "Status",
        "Last Update",
        "Delivered At",
        "Exception",
    ]
)

suppliers_template = pd.DataFrame(
    columns=["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"]
)

t1, t2, t3 = st.columns(3)
with t1:
    st.download_button(
        "Shipments template CSV",
        data=shipments_template.to_csv(index=False).encode("utf-8"),
        file_name="shipments_template.csv",
        mime="text/csv",
    )
with t2:
    st.download_button(
        "Tracking template CSV",
        data=tracking_template.to_csv(index=False).encode("utf-8"),
        file_name="tracking_template.csv",
        mime="text/csv",
    )
with t3:
    st.download_button(
        "Suppliers template CSV",
        data=suppliers_template.to_csv(index=False).encode("utf-8"),
        file_name="suppliers_template.csv",
        mime="text/csv",
    )

# -------------------------------
# Run pipeline: demo OR uploads
# -------------------------------
has_uploads = (f_orders is not None) and (f_shipments is not None)

if not (use_demo or has_uploads):
    st.info("Upload Orders + Shipments, or click **Try demo data** to begin.")
    st.stop()

# Load uploads if not demo
if not use_demo:
    try:
        raw_orders = pd.read_csv(f_orders)
        raw_shipments = pd.read_csv(f_shipments)
        raw_tracking = pd.read_csv(f_tracking) if f_tracking else pd.DataFrame()
    except Exception as e:
        st.error("Failed to read one of your CSV uploads.")
        st.code(str(e))
        st.stop()

# -------------------------------
# Normalize
# -------------------------------
st.divider()
st.subheader("Data checks")

orders, meta_o = normalize_orders(
    raw_orders,
    account_id=account_id,
    store_id=store_id,
    platform_hint=platform_hint,
    default_currency=default_currency,
    default_promised_ship_days=int(default_promised_ship_days),
)
shipments, meta_s = normalize_shipments(raw_shipments, account_id=account_id, store_id=store_id)

tracking = pd.DataFrame()
meta_t = {"validation_errors": []}
if raw_tracking is not None and isinstance(raw_tracking, pd.DataFrame) and not raw_tracking.empty:
    tracking, meta_t = normalize_tracking(raw_tracking, account_id=account_id, store_id=store_id)

errs = meta_o.get("validation_errors", []) + meta_s.get("validation_errors", []) + meta_t.get("validation_errors", [])

if errs:
    st.warning("We found some schema issues. You can still proceed, but fixing these improves accuracy:")
    for e in errs:
        st.write("- ", e)
else:
    st.success("Looks good ✅")

# -------------------------------
# Reconcile
# -------------------------------
st.divider()
st.subheader("Running reconciliation")

try:
    line_status_df, exceptions, followups, order_rollup, kpis = reconcile_all(orders, shipments, tracking)
except Exception as e:
    st.error("Reconciliation failed. This usually means a required column is missing after normalization.")
    st.code(str(e))
    st.stop()

# AI explanations (safe fallback)
try:
    exceptions = enhance_explanations(exceptions)
except Exception:
    pass

# -------------------------------
# Step 8: Enrich followups + add missing supplier contact exceptions
# -------------------------------
followups = enrich_followups_with_suppliers(followups, suppliers_df)
exceptions = add_missing_supplier_contact_exceptions(exceptions, followups)

# -------------------------------
# Step 7 + 7.5: Workspaces UI (Save/Load/History/Delete)
# -------------------------------
ws_root = workspace_root(WORKSPACES_DIR, account_id, store_id)
ws_root.mkdir(parents=True, exist_ok=True)

if "loaded_run" not in st.session_state:
    st.session_state["loaded_run"] = None

with st.sidebar:
    st.divider()
    st.header("Workspaces")

    workspace_name = st.text_input("Workspace name", value="default", key="ws_name")

    if st.button("💾 Save this run", key="btn_save_run"):
        run_dir = save_run(
            ws_root=ws_root,
            workspace_name=workspace_name,
            account_id=account_id,
            store_id=store_id,
            platform_hint=platform_hint,
            orders=orders,
            shipments=shipments,
            tracking=tracking,
            exceptions=exceptions,
            followups=followups,
            order_rollup=order_rollup,
            line_status_df=line_status_df,
            kpis=kpis,
            suppliers_df=suppliers_df,
        )
        st.success(f"Saved ✅ {workspace_name}/{run_dir.name}")
        st.session_state["loaded_run"] = str(run_dir)

    runs = list_runs(ws_root)

    if runs:
        run_labels = [
            f"{r['workspace_name']} / {r['run_id']}  (exceptions: {r.get('meta', {}).get('row_counts', {}).get('exceptions', '?')})"
            for r in runs
        ]
        chosen_idx = st.selectbox(
            "Load previous run",
            options=list(range(len(runs))),
            format_func=lambda i: run_labels[i],
            key="ws_load_select",
        )

        cL1, cL2 = st.columns(2)
        with cL1:
            if st.button("📂 Load", key="btn_load_run"):
                st.session_state["loaded_run"] = str(runs[chosen_idx]["path"])
                st.success("Loaded ✅")
        with cL2:
            if st.session_state["loaded_run"]:
                run_dir = Path(st.session_state["loaded_run"])
                zip_bytes = make_run_zip_bytes(run_dir)
                st.download_button(
                    "⬇️ Run Pack",
                    data=zip_bytes,
                    file_name=f"runpack_{run_dir.parent.name}_{run_dir.name}.zip",
                    mime="application/zip",
                    key="btn_zip_runpack",
                )

        with st.expander("Run history (7.5)", expanded=False):
            history_df = build_run_history_df(runs)
            st.dataframe(history_df, use_container_width=True, height=220)

            st.divider()
            st.markdown("**Delete a saved run**")
            st.caption("This permanently deletes the selected run folder on disk.")

            delete_idx = st.selectbox(
                "Select run to delete",
                options=list(range(len(runs))),
                format_func=lambda i: f"{runs[i]['workspace_name']} / {runs[i]['run_id']}",
                key="ws_delete_select",
            )

            confirm = st.checkbox("I understand this cannot be undone", key="ws_delete_confirm")
            if st.button("🗑️ Delete run", disabled=not confirm, key="btn_delete_run"):
                target = Path(runs[delete_idx]["path"])
                loaded_path = st.session_state.get("loaded_run")
                delete_run_dir(target)

                if loaded_path and Path(loaded_path) == target:
                    st.session_state["loaded_run"] = None

                st.success("Deleted ✅")
                st.rerun()
    else:
        st.caption("No saved runs yet. Click **Save this run** to create your first run history entry.")

# If a run is loaded, override the outputs used by the UI below (+ suppliers snapshot if present)
if st.session_state.get("loaded_run"):
    loaded = load_run(Path(st.session_state["loaded_run"]))
    exceptions = loaded.get("exceptions", exceptions)
    followups = loaded.get("followups", followups)
    order_rollup = loaded.get("order_rollup", order_rollup)
    line_status_df = loaded.get("line_status_df", line_status_df)

    loaded_suppliers = loaded.get("suppliers_df", pd.DataFrame())
    if loaded_suppliers is not None and not loaded_suppliers.empty:
        suppliers_df = loaded_suppliers
        st.session_state["suppliers_df"] = loaded_suppliers  # keep UI consistent

    meta = loaded.get("meta", {}) or {}
    st.info(f"Viewing saved run: **{meta.get('workspace_name','')} / {meta.get('created_at','')}**")

# -------------------------------
# Dashboard KPIs
# -------------------------------
st.divider()
st.subheader("Dashboard")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Order lines", int(kpis.get("total_order_lines", 0)))
k2.metric("% Shipped/Delivered", f"{kpis.get('pct_shipped_or_delivered', 0)}%")
k3.metric("% Delivered", f"{kpis.get('pct_delivered', 0)}%")
k4.metric("% Unshipped", f"{kpis.get('pct_unshipped', 0)}%")
k5.metric("% Late Unshipped", f"{kpis.get('pct_late_unshipped', 0)}%")

# -------------------------------
# "What am I looking at?" panel
# -------------------------------
st.divider()
with st.expander("What am I looking at?", expanded=True):
    st.markdown(
        """
### How to use this app (daily workflow)

**1) Start with the Exceptions Queue**
- These are the **order lines (SKU-level)** that need attention.
- Common reasons:
  - Orders are **late and unshipped**
  - **Partial shipments**
  - **Missing tracking**
  - **Carrier exceptions**

**2) Use Supplier Follow-ups**
- Copy/paste the email text to request **tracking or an updated ship date**.
- This is the fastest way to reduce customer complaints.

**3) Check Order Rollup**
- One row per order so you can quickly see **overall status**.
- Use this view for customer support updates.

**Tip:** Upload **suppliers.csv** in the sidebar to auto-fill supplier emails and reduce “missing contact” issues.
        """.strip()
    )

# -------------------------------
# Exceptions Queue
# -------------------------------
st.divider()
st.subheader("Exceptions Queue (Action this first)")

if exceptions is None or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
    exceptions = add_urgency_column(exceptions)

    fcol1, fcol2, fcol3, fcol4 = st.columns(4)

    with fcol1:
        issue_types = sorted(exceptions["issue_type"].dropna().unique().tolist()) if "issue_type" in exceptions.columns else []
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types)

    with fcol2:
        countries = sorted(
            [c for c in exceptions.get("customer_country", pd.Series([], dtype="object")).dropna().unique().tolist()
             if str(c).strip() != ""]
        )
        country_filter = st.multiselect("Customer country", countries, default=countries)

    with fcol3:
        suppliers = sorted(
            [s for s in exceptions.get("supplier_name", pd.Series([], dtype="object")).dropna().unique().tolist()
             if str(s).strip() != ""]
        )
        supplier_filter = st.multiselect("Supplier", suppliers, default=suppliers)

    with fcol4:
        urgencies = ["Critical", "High", "Medium", "Low"]
        urgency_filter = st.multiselect("Urgency", urgencies, default=urgencies)

    filtered = exceptions.copy()
    if issue_filter and "issue_type" in filtered.columns:
        filtered = filtered[filtered["issue_type"].isin(issue_filter)]
    if country_filter and "customer_country" in filtered.columns:
        filtered = filtered[filtered["customer_country"].isin(country_filter)]
    if supplier_filter and "supplier_name" in filtered.columns:
        filtered = filtered[filtered["supplier_name"].isin(supplier_filter)]
    if urgency_filter and "Urgency" in filtered.columns:
        filtered = filtered[filtered["Urgency"].isin(urgency_filter)]

    if "Urgency" in filtered.columns:
        counts = filtered["Urgency"].value_counts().to_dict()
        st.write(
            f"**Critical:** {counts.get('Critical', 0)} | "
            f"**High:** {counts.get('High', 0)} | "
            f"**Medium:** {counts.get('Medium', 0)} | "
            f"**Low:** {counts.get('Low', 0)}"
        )

    preferred_cols = [
        "Urgency",
        "order_id",
        "sku",
        "issue_type",
        "customer_country",
        "supplier_name",
        "quantity_ordered",
        "quantity_shipped",
        "line_status",
        "explanation",
        "next_action",
        "customer_risk",
    ]
    show_cols = [c for c in preferred_cols if c in filtered.columns]

    sort_cols = [c for c in ["Urgency", "order_id"] if c in filtered.columns]
    if sort_cols:
        filtered = filtered.sort_values(sort_cols, ascending=True)

    st.dataframe(style_exceptions_table(filtered[show_cols]), use_container_width=True, height=420)

    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
    )

# -------------------------------
# Supplier Follow-ups (with Copy buttons)
# -------------------------------
st.divider()
st.subheader("Supplier Follow-ups (Copy/Paste Ready)")

if followups is None or followups.empty:
    st.info("No follow-ups needed.")
else:
    summary_cols = [
        c for c in ["supplier_name", "supplier_email", "urgency", "item_count", "order_ids"]
        if c in followups.columns
    ]
    if summary_cols:
        st.dataframe(followups[summary_cols], use_container_width=True, height=220)
    else:
        st.dataframe(followups, use_container_width=True, height=220)

    st.download_button(
        "Download Supplier Follow-ups CSV",
        data=followups.to_csv(index=False).encode("utf-8"),
        file_name="supplier_followups.csv",
        mime="text/csv",
    )

    # Email preview + copy buttons (email/subject/body)
    if "supplier_name" in followups.columns and "body" in followups.columns and len(followups) > 0:
        st.divider()
        st.markdown("### Email preview (select a supplier)")

        chosen = st.selectbox(
            "Supplier",
            followups["supplier_name"].tolist(),
            key="supplier_email_preview_select",
        )
        row = followups[followups["supplier_name"] == chosen].iloc[0]

        supplier_email = row.get("supplier_email", "") if "supplier_email" in followups.columns else ""
        subject = row.get("subject", "Action required: outstanding shipments") if "subject" in followups.columns else "Action required: outstanding shipments"
        body = row.get("body", "")

        c1, c2, c3 = st.columns(3)
        with c1:
            copy_button(supplier_email, "Copy supplier email", key=f"copy_supplier_email_{chosen}")
        with c2:
            copy_button(subject, "Copy subject", key=f"copy_subject_{chosen}")
        with c3:
            copy_button(body, "Copy body", key=f"copy_body_{chosen}")

        st.text_input("To (supplier email)", value=supplier_email, key="email_to_preview")
        st.text_input("Subject", value=subject, key="email_subject_preview")
        st.text_area("Body", value=body, height=260, key="email_body_preview")

        st.download_button(
            "Download email as .txt",
            data=(f"To: {supplier_email}\nSubject: {subject}\n\n{body}").encode("utf-8"),
            file_name=f"supplier_email_{chosen}.txt".replace(" ", "_").lower(),
            mime="text/plain",
        )

# -------------------------------
# Order-level rollup
# -------------------------------
st.divider()
st.subheader("Order-Level Rollup (One row per order)")

st.dataframe(order_rollup, use_container_width=True, height=320)
st.download_button(
    "Download Order Rollup CSV",
    data=order_rollup.to_csv(index=False).encode("utf-8"),
    file_name="order_rollup.csv",
    mime="text/csv",
)

# -------------------------------
# All order lines
# -------------------------------
st.divider()
st.subheader("All Order Lines (Normalized + Status)")

st.dataframe(line_status_df, use_container_width=True, height=380)
st.download_button(
    "Download Line Status CSV",
    data=line_status_df.to_csv(index=False).encode("utf-8"),
    file_name="order_line_status.csv",
    mime="text/csv",
)

st.caption("MVP note: This version uses CSV uploads. Integrations + automation can be added after early-user feedback.")

