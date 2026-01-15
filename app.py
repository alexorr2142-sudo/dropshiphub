# app.py
from __future__ import annotations

import os
import json
import io
import zipfile
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# ============================================================
# Optional feature imports (do NOT crash if missing)
# ============================================================
render_sla_escalations = None
IssueTrackerStore = None

build_customer_impact_view = None
render_customer_impact_view = None

render_customer_comms_ui = None
render_comms_pack_download = None

build_daily_action_list = None
render_daily_action_list = None

render_kpi_trends = None

build_supplier_accountability_view = None
render_supplier_accountability = None

try:
    from ui.sla_escalations_ui import render_sla_escalations  # type: ignore
except Exception:
    render_sla_escalations = None

try:
    from core.issue_tracker import IssueTrackerStore  # type: ignore
except Exception:
    IssueTrackerStore = None

try:
    from core.customer_impact import build_customer_impact_view  # type: ignore
except Exception:
    build_customer_impact_view = None

try:
    from ui.customer_impact_ui import render_customer_impact_view  # type: ignore
except Exception:
    render_customer_impact_view = None

# ✅ Customer Comms (your compact, non-repetitive email UI)
try:
    from ui.customer_comms_ui import render_customer_comms_ui  # type: ignore
except Exception:
    render_customer_comms_ui = None

try:
    from ui.comms_pack_ui import render_comms_pack_download  # type: ignore
except Exception:
    render_comms_pack_download = None

try:
    from core.actions import build_daily_action_list  # type: ignore
except Exception:
    build_daily_action_list = None

try:
    from ui.actions_ui import render_daily_action_list  # type: ignore
except Exception:
    render_daily_action_list = None

try:
    from ui.kpi_trends_ui import render_kpi_trends  # type: ignore
except Exception:
    render_kpi_trends = None

try:
    from core.supplier_accountability import build_supplier_accountability_view  # type: ignore
except Exception:
    build_supplier_accountability_view = None

try:
    from ui.supplier_accountability_ui import render_supplier_accountability  # type: ignore
except Exception:
    render_supplier_accountability = None


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


# ============================================================
# Helpers: Copy button
# ============================================================
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


# ============================================================
# Helpers: urgency + styling
# ============================================================
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


# ============================================================
# Helpers: Issue Tracker requires issue_id in followups_full
# ============================================================
def ensure_issue_id(followups_full: pd.DataFrame) -> pd.DataFrame:
    """
    Ensures followups_full contains an issue_id column.
    - If issue_id exists: leave as-is.
    - Else: generate stable-ish ids from supplier_name + order_ids + (optional) sku-ish text.
    """
    if followups_full is None or followups_full.empty:
        return followups_full

    if "issue_id" in followups_full.columns:
        return followups_full

    df = followups_full.copy()

    supplier = df.get("supplier_name", pd.Series([""] * len(df))).fillna("").astype(str)
    order_ids = df.get("order_ids", df.get("order_id", pd.Series([""] * len(df)))).fillna("").astype(str)
    body = df.get("body", pd.Series([""] * len(df))).fillna("").astype(str)

    def _mk(i: int) -> str:
        raw = f"{supplier.iloc[i]}|{order_ids.iloc[i]}|{body.iloc[i][:120]}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    df["issue_id"] = [ _mk(i) for i in range(len(df)) ]
    return df


# ============================================================
# Daily Ops Pack ZIP (in-memory)
# ============================================================
def make_daily_ops_pack_bytes(
    exceptions: pd.DataFrame,
    followups: pd.DataFrame,
    order_rollup: pd.DataFrame,
    line_status_df: pd.DataFrame,
    kpis: dict,
    supplier_scorecards: pd.DataFrame | None = None,
    customer_impact: pd.DataFrame | None = None,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("exceptions.csv", (exceptions if exceptions is not None else pd.DataFrame()).to_csv(index=False))
        z.writestr("supplier_followups.csv", (followups if followups is not None else pd.DataFrame()).to_csv(index=False))
        z.writestr("order_rollup.csv", (order_rollup if order_rollup is not None else pd.DataFrame()).to_csv(index=False))
        z.writestr("order_line_status.csv", (line_status_df if line_status_df is not None else pd.DataFrame()).to_csv(index=False))

        if supplier_scorecards is not None and not supplier_scorecards.empty:
            z.writestr("supplier_scorecards.csv", supplier_scorecards.to_csv(index=False))

        if customer_impact is not None and not customer_impact.empty:
            z.writestr("customer_impact.csv", customer_impact.to_csv(index=False))

        z.writestr("kpis.json", json.dumps(kpis if isinstance(kpis, dict) else {}, indent=2))
        z.writestr(
            "README.txt",
            (
                "Dropship Hub — Daily Ops Pack\n"
                "Files:\n"
                " - exceptions.csv: SKU-level issues to action\n"
                " - supplier_followups.csv: supplier messages to send (OPEN)\n"
                " - order_rollup.csv: one row per order\n"
                " - order_line_status.csv: full line-level status\n"
                " - supplier_scorecards.csv: supplier performance snapshot\n"
                " - customer_impact.csv: customer comms candidates\n"
                " - kpis.json: dashboard KPIs\n"
            ),
        )
    buf.seek(0)
    return buf.read()


# ============================================================
# Basic auth helpers
# ============================================================
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
        st.caption("Email verification is currently disabled (accepting all emails).")


# ============================================================
# Workspaces + Supplier CRM (minimal local persistence)
# ============================================================
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


def suppliers_path(suppliers_dir: Path, account_id: str, store_id: str) -> Path:
    return suppliers_dir / _safe_slug(account_id) / _safe_slug(store_id) / "suppliers.csv"


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


def normalize_supplier_key(s: str) -> str:
    return (str(s) if s is not None else "").strip().lower()


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


# ============================================================
# Page setup
# ============================================================
st.set_page_config(page_title="Dropship Hub", layout="wide")

ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")

st.title("Dropship Hub — Early Access")
st.caption("Drop ship made easy — exceptions, follow-ups, and visibility in one hub.")

code = st.text_input("Enter early access code", type="password", key="access_code")
if code != ACCESS_CODE:
    st.info("This app is currently in early access. Enter your code to continue.")
    st.stop()

require_email_access_gate()


# ============================================================
# Paths
# ============================================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

WORKSPACES_DIR = DATA_DIR / "workspaces"
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

SUPPLIERS_DIR = DATA_DIR / "suppliers"
SUPPLIERS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Sidebar: Tenant + Defaults + Supplier Directory + Issue Tracker Maintenance
# ============================================================
with st.sidebar:
    st.header("Tenant")
    account_id = st.text_input("account_id", value="demo_account")
    store_id = st.text_input("store_id", value="demo_store")
    platform_hint = st.selectbox("platform hint", ["shopify", "amazon", "etsy", "other"], index=0)

    st.divider()
    st.header("Defaults")
    default_currency = st.text_input("Default currency", value="USD")
    default_promised_ship_days = st.number_input("Default promised ship days (SLA)", 1, 30, 3)

    st.divider()
    st.header("Supplier Directory (CRM)")
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
        sdf = st.session_state.get("suppliers_df", pd.DataFrame())
        st.dataframe(sdf, use_container_width=True, height=220)

    # Issue tracker maintenance (optional)
    if IssueTrackerStore is not None:
        st.divider()
        with st.expander("Issue Tracker Maintenance", expanded=False):
            prune_days = st.number_input("Prune resolved older than (days)", 1, 365, 30)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🧹 Prune old resolved", use_container_width=True):
                    store = IssueTrackerStore()
                    removed = store.prune_resolved_older_than_days(int(prune_days))
                    st.success(f"Pruned {removed} resolved item(s).")
                    st.rerun()
            with c2:
                if st.button("🗑️ Clear ALL resolved", use_container_width=True):
                    store = IssueTrackerStore()
                    removed = store.clear_resolved()
                    st.success(f"Cleared {removed} resolved item(s).")
                    st.rerun()

suppliers_df = st.session_state.get("suppliers_df", pd.DataFrame())


# ============================================================
# Onboarding checklist (14 steps)
# ============================================================
st.divider()
with st.expander("Onboarding checklist (14 steps)", expanded=False):
    st.markdown(
        """
1. Enter **Early Access Code**  
2. Verify your **work email**  
3. Set **Tenant**: `account_id`, `store_id`, `platform_hint`  
4. Set **Defaults**: currency + promised ship days (SLA)  
5. Upload **Orders CSV**  
6. Upload **Shipments CSV**  
7. Upload **Tracking CSV** (optional)  
8. Download **Templates** if needed  
9. Upload **suppliers.csv** for auto-filled supplier emails  
10. Review **Dashboard** KPIs  
11. Work **Ops Triage** (Critical + High first)  
12. Work **Exceptions Queue** (filters + export)  
13. Use **Ops Outreach (Comms)** (Supplier + Customer + Pack)  
14. Review **Trends** (Scorecards + KPI Trends) and take action  
        """.strip()
    )


# ============================================================
# Upload section
# ============================================================
st.divider()
st.subheader("Upload your data")
c1, c2, c3 = st.columns(3)
with c1:
    f_orders = st.file_uploader("Orders CSV", type=["csv"])
with c2:
    f_shipments = st.file_uploader("Shipments CSV", type=["csv"])
with c3:
    f_tracking = st.file_uploader("Tracking CSV (optional)", type=["csv"])

if f_orders is None or f_shipments is None:
    st.info("Upload Orders + Shipments to begin.")
    st.stop()

try:
    raw_orders = pd.read_csv(f_orders)
    raw_shipments = pd.read_csv(f_shipments)
    raw_tracking = pd.read_csv(f_tracking) if f_tracking else pd.DataFrame()
except Exception as e:
    st.error("Failed to read one of your uploads.")
    st.code(str(e))
    st.stop()


# ============================================================
# Normalize
# ============================================================
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
    st.warning("Schema issues detected (recommended to fix):")
    for e in errs:
        st.write("- ", e)
else:
    st.success("Looks good ✅")


# ============================================================
# Reconcile
# ============================================================
st.divider()
st.subheader("Running reconciliation")
try:
    line_status_df, exceptions, followups, order_rollup, kpis = reconcile_all(orders, shipments, tracking)
except Exception as e:
    st.error("Reconciliation failed. Usually a required column is missing after normalization.")
    st.code(str(e))
    st.stop()

try:
    exceptions = enhance_explanations(exceptions)
except Exception:
    pass

# Enrich followups with CRM + add "Missing supplier contact" exceptions
followups = enrich_followups_with_suppliers(followups, suppliers_df)
exceptions = add_missing_supplier_contact_exceptions(exceptions, followups)

# Urgency once
if exceptions is not None and not exceptions.empty and "Urgency" not in exceptions.columns:
    exceptions = add_urgency_column(exceptions)

# followups_full / open
followups_full = followups.copy() if isinstance(followups, pd.DataFrame) else pd.DataFrame()
followups_full = ensure_issue_id(followups_full)
followups_open = followups_full.copy()

# SLA Escalations UI
escalations_df = pd.DataFrame()
if render_sla_escalations is not None:
    try:
        escalations_df, followups_full_from_ui, _open_from_ui = render_sla_escalations(
            line_status_df=line_status_df,
            followups=followups_full,
            promised_ship_days=int(default_promised_ship_days),
        )
        if isinstance(followups_full_from_ui, pd.DataFrame) and not followups_full_from_ui.empty:
            followups_full = ensure_issue_id(followups_full_from_ui.copy())
    except Exception as e:
        st.warning("SLA Escalations failed to render.")
        st.code(str(e))

# Compute OPEN from FULL using issue tracker store
if IssueTrackerStore is not None and not followups_full.empty and "issue_id" in followups_full.columns:
    try:
        store = IssueTrackerStore()
        issue_map = store.load()
        followups_open = followups_full.copy()
        followups_open["_resolved_tmp"] = followups_open["issue_id"].astype(str).map(
            lambda k: bool(issue_map.get(str(k), {}).get("resolved", False))
        )
        followups_open = followups_open[followups_open["_resolved_tmp"] == False].copy()
        followups_open = followups_open.drop(columns=["_resolved_tmp"], errors="ignore")
    except Exception as e:
        st.warning("Issue Tracker OPEN/FULL filtering failed.")
        st.code(str(e))
        followups_open = followups_full.copy()
else:
    followups_open = followups_full.copy()

followups_for_ops = followups_open


# ============================================================
# Customer Impact
# ============================================================
customer_impact = pd.DataFrame()
if build_customer_impact_view is not None:
    try:
        customer_impact = build_customer_impact_view(exceptions=exceptions, max_items=50)
    except Exception as e:
        st.warning("Customer impact build failed.")
        st.code(str(e))
        customer_impact = pd.DataFrame()


# ============================================================
# Daily Ops Pack ZIP
# ============================================================
pack_date = datetime.now().strftime("%Y%m%d")
pack_name = f"daily_ops_pack_{pack_date}.zip"
ops_pack_bytes = make_daily_ops_pack_bytes(
    exceptions=exceptions if exceptions is not None else pd.DataFrame(),
    followups=followups_for_ops if followups_for_ops is not None else pd.DataFrame(),
    order_rollup=order_rollup if order_rollup is not None else pd.DataFrame(),
    line_status_df=line_status_df if line_status_df is not None else pd.DataFrame(),
    kpis=kpis if isinstance(kpis, dict) else {},
    supplier_scorecards=pd.DataFrame(),  # keep lightweight; scorecards may be elsewhere
    customer_impact=customer_impact,
)

with st.sidebar:
    st.divider()
    st.header("Daily Ops Pack")
    st.download_button(
        "⬇️ Download Daily Ops Pack ZIP",
        data=ops_pack_bytes,
        file_name=pack_name,
        mime="application/zip",
        use_container_width=True,
    )


# ============================================================
# Dashboard KPIs
# ============================================================
st.divider()
st.subheader("Dashboard")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Order lines", int((kpis or {}).get("total_order_lines", 0)))
k2.metric("% Shipped/Delivered", f"{(kpis or {}).get('pct_shipped_or_delivered', 0)}%")
k3.metric("% Delivered", f"{(kpis or {}).get('pct_delivered', 0)}%")
k4.metric("% Unshipped", f"{(kpis or {}).get('pct_unshipped', 0)}%")
k5.metric("% Late Unshipped", f"{(kpis or {}).get('pct_late_unshipped', 0)}%")


# ============================================================
# Ops Triage
# ============================================================
st.divider()
st.subheader("Ops Triage (Start here)")

if exceptions is None or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
    counts = exceptions["Urgency"].value_counts().to_dict() if "Urgency" in exceptions.columns else {}
    a, b, c, d = st.columns(4)
    a.metric("Critical", int(counts.get("Critical", 0)))
    b.metric("High", int(counts.get("High", 0)))
    c.metric("Medium", int(counts.get("Medium", 0)))
    d.metric("Low", int(counts.get("Low", 0)))

    if "triage_filter" not in st.session_state:
        st.session_state["triage_filter"] = "All"

    def set_triage(val: str):
        st.session_state["triage_filter"] = val

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.button("All", on_click=set_triage, args=("All",), use_container_width=True)
    with f2:
        st.button("Critical + High", on_click=set_triage, args=("CriticalHigh",), use_container_width=True)
    with f3:
        st.button("Missing tracking", on_click=set_triage, args=("MissingTracking",), use_container_width=True)
    with f4:
        st.button("Late unshipped", on_click=set_triage, args=("LateUnshipped",), use_container_width=True)

    triage = exceptions.copy()
    mode = st.session_state["triage_filter"]

    if mode == "CriticalHigh" and "Urgency" in triage.columns:
        triage = triage[triage["Urgency"].isin(["Critical", "High"])]

    if mode == "MissingTracking":
        blob = (
            triage.get("issue_type", "").astype(str).fillna("") + " " +
            triage.get("explanation", "").astype(str).fillna("") + " " +
            triage.get("next_action", "").astype(str).fillna("")
        ).str.lower()
        triage = triage[blob.str.contains("missing tracking|no tracking|tracking missing|invalid tracking", regex=True, na=False)]

    if mode == "LateUnshipped":
        blob = (
            triage.get("issue_type", "").astype(str).fillna("") + " " +
            triage.get("explanation", "").astype(str).fillna("") + " " +
            triage.get("line_status", "").astype(str).fillna("")
        ).str.lower()
        triage = triage[blob.str.contains("late unshipped|overdue|past due|late", regex=True, na=False)]

    preferred_cols = [
        "Urgency", "order_id", "sku", "issue_type", "customer_country",
        "supplier_name", "quantity_ordered", "quantity_shipped",
        "line_status", "explanation", "next_action", "customer_risk",
    ]
    show_cols = [c for c in preferred_cols if c in triage.columns]

    sort_cols = [c for c in ["Urgency", "order_id"] if c in triage.columns]
    if sort_cols:
        triage = triage.sort_values(sort_cols, ascending=True)

    st.dataframe(style_exceptions_table(triage[show_cols].head(10)), use_container_width=True, height=320)


# ============================================================
# Exceptions Queue
# ============================================================
st.divider()
st.subheader("Exceptions Queue (Action this first)")

if exceptions is None or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
    fcol1, fcol2, fcol3, fcol4 = st.columns(4)

    with fcol1:
        issue_types = sorted(exceptions["issue_type"].dropna().unique().tolist()) if "issue_type" in exceptions.columns else []
        issue_filter = st.multiselect("Issue types", issue_types, default=issue_types)

    with fcol2:
        countries = sorted([c for c in exceptions.get("customer_country", pd.Series([], dtype="object")).dropna().unique().tolist() if str(c).strip() != ""])
        country_filter = st.multiselect("Customer country", countries, default=countries)

    with fcol3:
        suppliers = sorted([s for s in exceptions.get("supplier_name", pd.Series([], dtype="object")).dropna().unique().tolist() if str(s).strip() != ""])
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

    # ✅ Safe sort (no errors= argument)
    sort_cols = [c for c in ["Urgency", "order_id"] if c in filtered.columns]
    if sort_cols:
        filtered = filtered.sort_values(sort_cols, ascending=True)

    preferred_cols = [
        "Urgency", "order_id", "sku", "issue_type", "customer_country",
        "supplier_name", "quantity_ordered", "quantity_shipped",
        "line_status", "explanation", "next_action", "customer_risk",
    ]
    show_cols = [c for c in preferred_cols if c in filtered.columns]
    st.dataframe(style_exceptions_table(filtered[show_cols]), use_container_width=True, height=420)

    st.download_button(
        "Download Exceptions CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="exceptions_queue.csv",
        mime="text/csv",
    )


# ============================================================
# ✅ Ops Outreach (Comms) — grouped, non-repetitive
# ============================================================
st.divider()
st.subheader("Ops Outreach (Comms)")

tab_supplier, tab_customer, tab_pack = st.tabs(["Supplier Follow-ups", "Customer Emails", "Comms Pack"])

with tab_supplier:
    if followups_for_ops is None or followups_for_ops.empty:
        st.info("No follow-ups needed.")
    else:
        summary_cols = [c for c in ["supplier_name", "supplier_email", "worst_escalation", "urgency", "item_count", "order_ids"] if c in followups_for_ops.columns]
        st.dataframe(followups_for_ops[summary_cols] if summary_cols else followups_for_ops, use_container_width=True, height=260)

        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "Download OPEN Follow-ups CSV (Unresolved)",
                data=followups_for_ops.to_csv(index=False).encode("utf-8"),
                file_name="supplier_followups_open.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                "Download FULL Follow-ups CSV (Includes resolved/notes)",
                data=followups_full.to_csv(index=False).encode("utf-8"),
                file_name="supplier_followups_full.csv",
                mime="text/csv",
                use_container_width=True,
            )

        # Email preview + 3-bullet supplier generator
        if "supplier_name" in followups_for_ops.columns:
            st.divider()
            st.markdown("### Supplier Email Generator (3 bullet questions)")
            chosen = st.selectbox("Supplier", followups_for_ops["supplier_name"].tolist(), key="supplier_email_gen_select")
            row = followups_for_ops[followups_for_ops["supplier_name"] == chosen].iloc[0]

            supplier_email = str(row.get("supplier_email", "")).strip()
            order_ids = str(row.get("order_ids", row.get("order_id", ""))).strip()
            item_count = str(row.get("item_count", "")).strip()
            worst = str(row.get("worst_escalation", "")).strip()

            subject_default = f"Urgent: Shipment status + tracking update needed ({chosen})"
            subject = st.text_input("Subject", value=subject_default, key="supplier_email_gen_subject")

            bullets = [
                f"Please confirm what is causing the delay / issue for these orders: {order_ids}".strip(),
                "What is the updated ship date (or delivery ETA) for each impacted order?",
                "Please provide tracking numbers (or carrier + tracking) and confirm the next action you are taking today.",
            ]
            body_default = (
                f"Hi {chosen},\n\n"
                f"We’re following up on impacted shipments.\n\n"
                f"Summary:\n"
                f"- Orders: {order_ids}\n"
                f"- Items: {item_count}\n"
                f"- SLA/Escalation: {worst}\n\n"
                f"Questions:\n"
                f"• {bullets[0]}\n"
                f"• {bullets[1]}\n"
                f"• {bullets[2]}\n\n"
                f"Thanks,\n"
                f"Ops Team"
            )

            body = st.text_area("Body", value=body_default, height=240, key="supplier_email_gen_body")

            c1, c2, c3 = st.columns(3)
            with c1:
                copy_button(supplier_email, "Copy supplier email", key=f"copy_supplier_email_{chosen}")
            with c2:
                copy_button(subject, "Copy subject", key=f"copy_supplier_subject_{chosen}")
            with c3:
                copy_button(body, "Copy body", key=f"copy_supplier_body_{chosen}")

            st.download_button(
                "Download supplier email as .txt",
                data=(f"To: {supplier_email}\nSubject: {subject}\n\n{body}").encode("utf-8"),
                file_name=f"supplier_email_{str(chosen).replace(' ', '_').lower()}.txt",
                mime="text/plain",
                use_container_width=True,
            )

with tab_customer:
    # ✅ No more back-to-back repetition: we show one compact UI
    if customer_impact is None or customer_impact.empty:
        st.caption("No customer-impact items detected (or customer impact module not available).")
    else:
        with st.expander("Customer impact candidates (table)", expanded=False):
            if render_customer_impact_view is not None:
                try:
                    render_customer_impact_view(customer_impact)
                except Exception as e:
                    st.warning("Customer impact UI failed.")
                    st.code(str(e))
                    st.dataframe(customer_impact, use_container_width=True, height=260)
            else:
                st.dataframe(customer_impact, use_container_width=True, height=260)

        if render_customer_comms_ui is not None:
            try:
                render_customer_comms_ui(customer_impact)
            except Exception as e:
                st.warning("Customer comms UI failed to render.")
                st.code(str(e))
        else:
            st.warning("customer_comms_ui not available; customer emails UI is disabled.")
            st.caption("Fix: ensure ui/customer_comms_ui.py exists and imports cleanly.")

with tab_pack:
    if render_comms_pack_download is not None:
        try:
            render_comms_pack_download(followups=followups_for_ops, customer_impact=customer_impact)
        except Exception as e:
            st.warning("Comms pack UI failed.")
            st.code(str(e))
    else:
        st.caption("Comms pack UI not available (ui/comms_pack_ui.py missing or import failed).")


# ============================================================
# SLA Escalations panel
# ============================================================
if isinstance(escalations_df, pd.DataFrame) and not escalations_df.empty:
    st.divider()
    st.subheader("SLA Escalations (Supplier-level)")
    st.dataframe(escalations_df, use_container_width=True, height=260)


# ============================================================
# KPI Trends + Action list (optional) — show errors, don’t swallow
# ============================================================
if build_daily_action_list is not None and render_daily_action_list is not None:
    st.divider()
    try:
        actions = build_daily_action_list(exceptions=exceptions, followups=followups_for_ops, max_items=10)
        render_daily_action_list(actions)
    except Exception as e:
        st.warning("Daily action list failed.")
        st.code(str(e))

if render_kpi_trends is not None:
    st.divider()
    try:
        render_kpi_trends(workspaces_dir=WORKSPACES_DIR, account_id=account_id, store_id=store_id)
    except Exception as e:
        st.warning("KPI Trends failed to render.")
        st.code(str(e))


# ============================================================
# Diagnostics (to verify every feature is loading + why charts missing)
# ============================================================
st.divider()
with st.expander("Diagnostics (feature status)", expanded=False):
    st.markdown("### Optional module load status")
    st.write({
        "render_sla_escalations": render_sla_escalations is not None,
        "IssueTrackerStore": IssueTrackerStore is not None,
        "build_customer_impact_view": build_customer_impact_view is not None,
        "render_customer_impact_view": render_customer_impact_view is not None,
        "render_customer_comms_ui": render_customer_comms_ui is not None,
        "render_comms_pack_download": render_comms_pack_download is not None,
        "build_daily_action_list": build_daily_action_list is not None,
        "render_daily_action_list": render_daily_action_list is not None,
        "render_kpi_trends": render_kpi_trends is not None,
        "build_supplier_accountability_view": build_supplier_accountability_view is not None,
        "render_supplier_accountability": render_supplier_accountability is not None,
    })

    st.markdown("### Data readiness checks")
    def _cols(df):
        return [] if df is None else list(df.columns)

    st.write("exceptions rows:", 0 if exceptions is None else len(exceptions))
    st.write("exceptions cols:", _cols(exceptions))

    st.write("followups_full rows:", 0 if followups_full is None else len(followups_full))
    st.write("followups_full cols:", _cols(followups_full))
    st.write("issue_id present:", (followups_full is not None and not followups_full.empty and "issue_id" in followups_full.columns))

    st.write("followups_open rows:", 0 if followups_for_ops is None else len(followups_for_ops))
    st.write("customer_impact rows:", 0 if customer_impact is None else len(customer_impact))
    st.write("customer_impact cols:", _cols(customer_impact))
