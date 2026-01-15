# app.py
import os
import json
import io
import zipfile
import shutil
import inspect
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

# ✅ NEW: customer comms UI (email-first)
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

# ✅ supplier accountability core + ui
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
# Helpers
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
          .catch(() => alert('Copy failed. Your browser may block clipboard access.'));"
      >
        {label}
      </button>
    </div>
    """
    components.html(html, height=55)


def call_with_accepted_kwargs(fn, **kwargs):
    """
    Calls fn with only the kwargs it actually accepts.
    Prevents 'unexpected keyword argument' crashes when core signatures differ.
    """
    sig = inspect.signature(fn)
    accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return fn(**accepted)


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
    df["Urgency"] = pd.Categorical(df["Urgency"], categories=["Critical", "High", "Medium", "Low"], ordered=True)
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


# -------------------------------
# Access gate
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
    email = st.text_input("Work email", key="auth_work_email").strip().lower()
    allowed = get_allowed_emails()

    if allowed:
        if not email:
            st.info("Enter your work email to continue.")
            st.stop()
        if email not in allowed:
            st.error("This email is not authorized for early access.")
            st.caption("Ask the admin to add your email to the allowlist.")
            st.stop()
        st.success("Email verified ✅")
    else:
        st.caption("Email verification is currently disabled (accepting all emails).")


# -------------------------------
# Workspaces (local disk)
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
    followups_full: pd.DataFrame,
    order_rollup: pd.DataFrame,
    line_status_df: pd.DataFrame,
    kpis: dict,
    suppliers_df: pd.DataFrame,
) -> Path:
    workspace_name = _safe_slug(workspace_name)
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_dir = ws_root / workspace_name / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    exceptions.to_csv(run_dir / "exceptions.csv", index=False)
    followups_full.to_csv(run_dir / "followups.csv", index=False)
    order_rollup.to_csv(run_dir / "order_rollup.csv", index=False)
    line_status_df.to_csv(run_dir / "line_status.csv", index=False)

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
            "followups": int(len(followups_full)),
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
# Supplier CRM
# -------------------------------
def normalize_supplier_key(s: str) -> str:
    return (str(s) if s is not None else "").strip().lower()


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


def style_supplier_table(df: pd.DataFrame):
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


# -------------------------------
# Scorecards
# -------------------------------
def _contains_any(s: str, terms: list[str]) -> bool:
    s = (s or "").lower()
    return any(t in s for t in terms)


def build_supplier_scorecard_from_run(line_status_df: pd.DataFrame, exceptions_df: pd.DataFrame) -> pd.DataFrame:
    if line_status_df is None or line_status_df.empty:
        return pd.DataFrame()
    df = line_status_df.copy()
    if "supplier_name" not in df.columns:
        return pd.DataFrame()

    df["supplier_name"] = df["supplier_name"].fillna("").astype(str)
    df = df[df["supplier_name"].str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame()

    base = df.groupby("supplier_name").size().reset_index(name="total_lines")

    exc = None
    if exceptions_df is not None and not exceptions_df.empty and "supplier_name" in exceptions_df.columns:
        exc = exceptions_df.copy()
        exc["supplier_name"] = exc["supplier_name"].fillna("").astype(str)
        exc = exc[exc["supplier_name"].str.strip() != ""].copy()
        if not exc.empty:
            if "Urgency" not in exc.columns:
                exc = add_urgency_column(exc)
            exc_counts = exc.groupby("supplier_name").size().reset_index(name="exception_lines")
            crit = exc[exc["Urgency"] == "Critical"].groupby("supplier_name").size().reset_index(name="critical")
            high = exc[exc["Urgency"] == "High"].groupby("supplier_name").size().reset_index(name="high")
        else:
            exc_counts = pd.DataFrame(columns=["supplier_name", "exception_lines"])
            crit = pd.DataFrame(columns=["supplier_name", "critical"])
            high = pd.DataFrame(columns=["supplier_name", "high"])
    else:
        exc_counts = pd.DataFrame(columns=["supplier_name", "exception_lines"])
        crit = pd.DataFrame(columns=["supplier_name", "critical"])
        high = pd.DataFrame(columns=["supplier_name", "high"])

    out = (
        base.merge(exc_counts, on="supplier_name", how="left")
            .merge(crit, on="supplier_name", how="left")
            .merge(high, on="supplier_name", how="left")
    )
    out["exception_lines"] = out["exception_lines"].fillna(0).astype(int)
    out["critical"] = out["critical"].fillna(0).astype(int)
    out["high"] = out["high"].fillna(0).astype(int)
    out["exception_rate"] = (out["exception_lines"] / out["total_lines"]).round(4)

    if exc is not None and not exc.empty:
        def _flag_count(term_list):
            tmp = exc.copy()
            blob = (
                tmp.get("issue_type", "").astype(str).fillna("") + " " +
                tmp.get("explanation", "").astype(str).fillna("") + " " +
                tmp.get("next_action", "").astype(str).fillna("")
            ).str.lower()
            tmp["_flag"] = blob.apply(lambda x: _contains_any(x, term_list))
            return tmp[tmp["_flag"]].groupby("supplier_name").size().reset_index(name="count")

        missing_tracking_terms = ["missing tracking", "no tracking", "tracking missing", "invalid tracking"]
        late_terms = ["late", "overdue", "past due", "late unshipped"]
        carrier_terms = ["carrier exception", "exception", "stuck", "lost", "returned to sender"]

        mt = _flag_count(missing_tracking_terms).rename(columns={"count": "missing_tracking_flags"})
        lt = _flag_count(late_terms).rename(columns={"count": "late_flags"})
        ct = _flag_count(carrier_terms).rename(columns={"count": "carrier_exception_flags"})

        out = out.merge(mt, on="supplier_name", how="left").merge(lt, on="supplier_name", how="left").merge(ct, on="supplier_name", how="left")
        for c in ["missing_tracking_flags", "late_flags", "carrier_exception_flags"]:
            out[c] = out.get(c, 0).fillna(0).astype(int)
    else:
        out["missing_tracking_flags"] = 0
        out["late_flags"] = 0
        out["carrier_exception_flags"] = 0

    out = out.sort_values(["exception_rate", "critical", "high"], ascending=[False, False, False])
    return out


def _parse_run_id_to_dt(run_id: str):
    try:
        return datetime.strptime(run_id, "%Y%m%dT%H%M%SZ")
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_recent_scorecard_history(ws_root_str: str, max_runs: int = 25) -> pd.DataFrame:
    ws_root = Path(ws_root_str)
    runs = list_runs(ws_root)[:max_runs]

    all_rows = []
    for r in runs:
        run_dir = Path(r["path"])
        run_id = r.get("run_id", run_dir.name)
        run_dt = _parse_run_id_to_dt(run_id)

        line_path = run_dir / "line_status.csv"
        exc_path = run_dir / "exceptions.csv"
        if not line_path.exists():
            continue

        try:
            line_df = pd.read_csv(line_path)
        except Exception:
            continue

        try:
            exc_df = pd.read_csv(exc_path) if exc_path.exists() else pd.DataFrame()
        except Exception:
            exc_df = pd.DataFrame()

        sc = build_supplier_scorecard_from_run(line_df, exc_df)
        if sc is None or sc.empty:
            continue

        sc = sc.copy()
        sc["run_id"] = run_id
        sc["run_dt"] = run_dt
        all_rows.append(sc)

    if not all_rows:
        return pd.DataFrame()

    return pd.concat(all_rows, ignore_index=True, sort=False)


# -------------------------------
# Sticky Demo Mode
# -------------------------------
def _init_demo_tables_if_needed(data_dir: Path):
    if "demo_mode" not in st.session_state:
        st.session_state["demo_mode"] = False

    if st.session_state.get("demo_mode", False):
        if "demo_raw_orders" not in st.session_state:
            st.session_state["demo_raw_orders"] = pd.read_csv(data_dir / "raw_orders.csv")
        if "demo_raw_shipments" not in st.session_state:
            st.session_state["demo_raw_shipments"] = pd.read_csv(data_dir / "raw_shipments.csv")
        if "demo_raw_tracking" not in st.session_state:
            st.session_state["demo_raw_tracking"] = pd.read_csv(data_dir / "raw_tracking.csv")
    else:
        for k in ["demo_raw_orders", "demo_raw_shipments", "demo_raw_tracking"]:
            st.session_state.pop(k, None)


def _reset_demo_tables(data_dir: Path):
    st.session_state["demo_raw_orders"] = pd.read_csv(data_dir / "raw_orders.csv")
    st.session_state["demo_raw_shipments"] = pd.read_csv(data_dir / "raw_shipments.csv")
    st.session_state["demo_raw_tracking"] = pd.read_csv(data_dir / "raw_tracking.csv")


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


# -------------------------------
# Paths
# -------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

WORKSPACES_DIR = DATA_DIR / "workspaces"
if WORKSPACES_DIR.exists() and not WORKSPACES_DIR.is_dir():
    st.error("Workspace storage path invalid: `data/workspaces` exists but is a FILE.")
    st.stop()
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

SUPPLIERS_DIR = DATA_DIR / "suppliers"
if SUPPLIERS_DIR.exists() and not SUPPLIERS_DIR.is_dir():
    st.error("Supplier storage path invalid: `data/suppliers` exists but is a FILE.")
    st.stop()
SUPPLIERS_DIR.mkdir(parents=True, exist_ok=True)


# -------------------------------
# Sidebar
# -------------------------------
with st.sidebar:
    st.header("Plan")
    _plan = st.selectbox("Current plan", ["Early Access (Free)", "Pro", "Team"], index=0)

    st.divider()
    st.header("Tenant")
    account_id = st.text_input("account_id", value="demo_account")
    store_id = st.text_input("store_id", value="demo_store")
    platform_hint = st.selectbox("platform hint", ["shopify", "amazon", "etsy", "other"], index=0)

    st.divider()
    st.header("Defaults")
    default_currency = st.text_input("Default currency", value="USD")
    default_promised_ship_days = st.number_input("Default promised ship days (SLA)", min_value=1, max_value=30, value=3)

    st.divider()
    st.header("Demo Mode (Sticky)")
    demo_mode = st.toggle(
        "Use demo data (sticky)",
        key="demo_mode",
        help="Keeps demo data and your edits across interactions until you reset or turn off demo mode.",
    )

    _init_demo_tables_if_needed(DATA_DIR)

    if demo_mode:
        cdm1, cdm2 = st.columns(2)
        with cdm1:
            if st.button("Reset demo", use_container_width=True):
                _reset_demo_tables(DATA_DIR)
                st.success("Demo reset ✅")
                st.rerun()
        with cdm2:
            if st.button("Clear demo", use_container_width=True):
                st.session_state["demo_mode"] = False
                _init_demo_tables_if_needed(DATA_DIR)
                st.rerun()

    # ✅ Issue Tracker maintenance
    if IssueTrackerStore is not None:
        st.divider()
        with st.expander("Issue Tracker Maintenance", expanded=False):
            prune_days = st.number_input("Prune resolved older than (days)", min_value=1, max_value=365, value=30, step=1)
            cmt1, cmt2 = st.columns(2)
            with cmt1:
                if st.button("🧹 Prune old resolved", use_container_width=True):
                    store = IssueTrackerStore()
                    removed = store.prune_resolved_older_than_days(int(prune_days))
                    st.success(f"Pruned {removed} resolved item(s).")
                    st.rerun()
            with cmt2:
                if st.button("🗑️ Clear ALL resolved", use_container_width=True):
                    store = IssueTrackerStore()
                    removed = store.clear_resolved()
                    st.success(f"Cleared {removed} resolved item(s).")
                    st.rerun()

    st.divider()
    st.header("Supplier Directory (CRM)")
    if "suppliers_df" not in st.session_state:
        st.session_state["suppliers_df"] = load_suppliers(SUPPLIERS_DIR, account_id, store_id)

    f_suppliers = st.file_uploader("Upload suppliers.csv", type=["csv"], key="suppliers_uploader")
    if f_suppliers is not None:
        uploaded_suppliers = pd.read_csv(f_suppliers)
        st.session_state["suppliers_df"] = uploaded_suppliers
        p = save_suppliers(SUPPLIERS_DIR, account_id, store_id, uploaded_suppliers)
        st.success(f"Saved ✅ {p.as_posix()}")

    with st.expander("View Supplier Directory", expanded=False):
        suppliers_df_preview = st.session_state.get("suppliers_df", pd.DataFrame())
        if suppliers_df_preview is None or suppliers_df_preview.empty:
            st.caption("No supplier directory loaded yet.")
        else:
            show_cols = [c for c in ["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"] if c in suppliers_df_preview.columns]
            if show_cols:
                st.dataframe(style_supplier_table(suppliers_df_preview[show_cols]), use_container_width=True, height=220)
            else:
                st.dataframe(suppliers_df_preview, use_container_width=True, height=220)

suppliers_df = st.session_state.get("suppliers_df", pd.DataFrame())


# -------------------------------
# Diagnostics (top)
# -------------------------------
with st.expander("Diagnostics", expanded=False):
    diag = {
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
    }
    st.json(diag)

    ws_root_diag = workspace_root(WORKSPACES_DIR, account_id, store_id)
    st.write(f"ws_root: `{ws_root_diag.as_posix()}`")
    st.write(f"saved runs: {len(list_runs(ws_root_diag))}")


# -------------------------------
# Onboarding checklist (14)
# -------------------------------
st.divider()
with st.expander("Onboarding checklist (14 steps)", expanded=True):
    st.markdown(
        """
1. Enter **Early Access Code**  
2. Verify your **work email** (allowlist gate)  
3. Set **Tenant**: `account_id`, `store_id`, `platform_hint`  
4. Set **Defaults**: currency + promised ship days (SLA)  
5. (Optional) Turn on **Demo Mode (Sticky)** to explore instantly  
6. (Demo Mode) Use **Edit demo data** to simulate real scenarios  
7. Upload **Orders CSV** (required if not using demo)  
8. Upload **Shipments CSV** (required if not using demo)  
9. Upload **Tracking CSV** (optional but recommended)  
10. Download **Templates** if you need the correct format  
11. Upload **suppliers.csv** to enable auto-filled supplier emails  
12. Review **Ops Triage** (Critical + High first)  
13. Work **Exceptions Queue** (filter by supplier/country/urgency)  
14. Use **Ops Outreach (Comms)** then **Save Run** to build trends/history
        """.strip()
    )


# -------------------------------
# Start Here (Demo editor)
# -------------------------------
st.subheader("Start here")

if st.session_state.get("demo_mode", False):
    st.success("Demo mode is ON (sticky). Your demo edits persist until you reset/clear.")
    with st.expander("Edit demo data (these edits persist)", expanded=True):
        e1, e2, e3 = st.columns(3)
        with e1:
            st.caption("raw_orders.csv (demo)")
            st.session_state["demo_raw_orders"] = st.data_editor(
                st.session_state.get("demo_raw_orders", pd.DataFrame()),
                use_container_width=True,
                height=280,
                num_rows="dynamic",
                key="demo_orders_editor",
            )
        with e2:
            st.caption("raw_shipments.csv (demo)")
            st.session_state["demo_raw_shipments"] = st.data_editor(
                st.session_state.get("demo_raw_shipments", pd.DataFrame()),
                use_container_width=True,
                height=280,
                num_rows="dynamic",
                key="demo_shipments_editor",
            )
        with e3:
            st.caption("raw_tracking.csv (demo)")
            st.session_state["demo_raw_tracking"] = st.data_editor(
                st.session_state.get("demo_raw_tracking", pd.DataFrame()),
                use_container_width=True,
                height=280,
                num_rows="dynamic",
                key="demo_tracking_editor",
            )
else:
    st.info("Turn on **Demo Mode (Sticky)** in the sidebar to play with demo data (edits persist).")


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
# Templates
# -------------------------------
st.subheader("Download templates")

shipments_template = pd.DataFrame(
    columns=["Supplier", "Supplier Order ID", "Order ID", "SKU", "Quantity", "Ship Date", "Carrier", "Tracking", "From Country", "To Country"]
)
tracking_template = pd.DataFrame(
    columns=["Carrier", "Tracking Number", "Order ID", "Supplier Order ID", "Status", "Last Update", "Delivered At", "Exception"]
)
suppliers_template = pd.DataFrame(columns=["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"])

t1, t2, t3 = st.columns(3)
with t1:
    st.download_button("Shipments template CSV", data=shipments_template.to_csv(index=False).encode("utf-8"), file_name="shipments_template.csv", mime="text/csv")
with t2:
    st.download_button("Tracking template CSV", data=tracking_template.to_csv(index=False).encode("utf-8"), file_name="tracking_template.csv", mime="text/csv")
with t3:
    st.download_button("Suppliers template CSV", data=suppliers_template.to_csv(index=False).encode("utf-8"), file_name="suppliers_template.csv", mime="text/csv")


# -------------------------------
# Run pipeline: demo OR uploads
# -------------------------------
raw_orders = None
raw_shipments = None
raw_tracking = None

demo_mode_active = st.session_state.get("demo_mode", False)
has_uploads = (f_orders is not None) and (f_shipments is not None)

if not (demo_mode_active or has_uploads):
    st.info("Upload Orders + Shipments, or turn on **Demo Mode (Sticky)** in the sidebar to begin.")
    st.stop()

if demo_mode_active:
    raw_orders = st.session_state.get("demo_raw_orders", pd.DataFrame())
    raw_shipments = st.session_state.get("demo_raw_shipments", pd.DataFrame())
    raw_tracking = st.session_state.get("demo_raw_tracking", pd.DataFrame())

    if raw_orders is None or raw_orders.empty:
        st.error("Demo orders are empty. Click **Reset demo** in the sidebar.")
        st.stop()
    if raw_shipments is None or raw_shipments.empty:
        st.error("Demo shipments are empty. Click **Reset demo** in the sidebar.")
        st.stop()
else:
    raw_orders = pd.read_csv(f_orders)
    raw_shipments = pd.read_csv(f_shipments)
    raw_tracking = pd.read_csv(f_tracking) if f_tracking else pd.DataFrame()


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

line_status_df, exceptions, followups, order_rollup, kpis = reconcile_all(orders, shipments, tracking)

try:
    exceptions = enhance_explanations(exceptions)
except Exception:
    pass

followups = enrich_followups_with_suppliers(followups, suppliers_df)
exceptions = add_missing_supplier_contact_exceptions(exceptions, followups)


# -------------------------------
# SLA Escalations + Issue Tracker (Resolved + Notes)
# -------------------------------
followups_full = followups.copy() if isinstance(followups, pd.DataFrame) else pd.DataFrame()
followups_open = followups_full.copy()
escalations_df = pd.DataFrame()

if render_sla_escalations is not None:
    try:
        escalations_df, followups_full_from_ui, _open_from_ui = render_sla_escalations(
            line_status_df=line_status_df,
            followups=followups_full,
            promised_ship_days=int(default_promised_ship_days),
        )
        if isinstance(followups_full_from_ui, pd.DataFrame) and not followups_full_from_ui.empty:
            followups_full = followups_full_from_ui.copy()
    except Exception:
        pass

# OPEN derived from FULL via Issue Tracker flags
if IssueTrackerStore is not None and not followups_full.empty and "issue_id" in followups_full.columns:
    store = IssueTrackerStore()
    issue_map = store.load()

    followups_open = followups_full.copy()
    followups_open["_resolved_tmp"] = followups_open["issue_id"].astype(str).map(
        lambda k: bool(issue_map.get(str(k), {}).get("resolved", False))
    )
    followups_open = followups_open[followups_open["_resolved_tmp"] == False].copy()
    followups_open = followups_open.drop(columns=["_resolved_tmp"], errors="ignore")
else:
    followups_open = followups_full.copy()

followups = followups_open


# -------------------------------
# Workspaces UI (sidebar)
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
            exceptions=exceptions if exceptions is not None else pd.DataFrame(),
            followups_full=followups_full if followups_full is not None else pd.DataFrame(),
            order_rollup=order_rollup if order_rollup is not None else pd.DataFrame(),
            line_status_df=line_status_df if line_status_df is not None else pd.DataFrame(),
            kpis=kpis if isinstance(kpis, dict) else {},
            suppliers_df=suppliers_df if suppliers_df is not None else pd.DataFrame(),
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

        with st.expander("Run history", expanded=False):
            history_df = build_run_history_df(runs)
            st.dataframe(history_df, use_container_width=True, height=220)

            st.divider()
            st.markdown("**Delete a saved run**")
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

# override if loaded
if st.session_state.get("loaded_run"):
    loaded = load_run(Path(st.session_state["loaded_run"]))
    exceptions = loaded.get("exceptions", exceptions)
    followups_full = loaded.get("followups", followups_full)
    order_rollup = loaded.get("order_rollup", order_rollup)
    line_status_df = loaded.get("line_status_df", line_status_df)

    loaded_suppliers = loaded.get("suppliers_df", pd.DataFrame())
    if loaded_suppliers is not None and not loaded_suppliers.empty:
        suppliers_df = loaded_suppliers
        st.session_state["suppliers_df"] = loaded_suppliers

    if IssueTrackerStore is not None and isinstance(followups_full, pd.DataFrame) and not followups_full.empty and "issue_id" in followups_full.columns:
        store = IssueTrackerStore()
        issue_map = store.load()

        followups_open = followups_full.copy()
        followups_open["_resolved_tmp"] = followups_open["issue_id"].astype(str).map(
            lambda k: bool(issue_map.get(str(k), {}).get("resolved", False))
        )
        followups_open = followups_open[followups_open["_resolved_tmp"] == False].copy()
        followups_open = followups_open.drop(columns=["_resolved_tmp"], errors="ignore")
    else:
        followups_open = followups_full.copy() if isinstance(followups_full, pd.DataFrame) else pd.DataFrame()

    followups = followups_open
    meta = loaded.get("meta", {}) or {}
    st.info(f"Viewing saved run: **{meta.get('workspace_name','')} / {meta.get('created_at','')}**")


# -------------------------------
# Urgency + scorecards
# -------------------------------
if exceptions is not None and not exceptions.empty and "Urgency" not in exceptions.columns:
    exceptions = add_urgency_column(exceptions)

scorecard = build_supplier_scorecard_from_run(line_status_df, exceptions)


# -------------------------------
# Customer impact build
# -------------------------------
customer_impact = pd.DataFrame()
if build_customer_impact_view is not None:
    try:
        customer_impact = build_customer_impact_view(exceptions=exceptions, max_items=50)
    except Exception:
        customer_impact = pd.DataFrame()


# -------------------------------
# Daily Ops Pack ZIP
# -------------------------------
pack_date = datetime.now().strftime("%Y%m%d")
pack_name = f"daily_ops_pack_{pack_date}.zip"
ops_pack_bytes = make_daily_ops_pack_bytes(
    exceptions=exceptions if exceptions is not None else pd.DataFrame(),
    followups=followups_open if followups_open is not None else (followups if followups is not None else pd.DataFrame()),
    order_rollup=order_rollup if order_rollup is not None else pd.DataFrame(),
    line_status_df=line_status_df if line_status_df is not None else pd.DataFrame(),
    kpis=kpis if isinstance(kpis, dict) else {},
    supplier_scorecards=scorecard,
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
        key="btn_daily_ops_pack_sidebar",
    )


# -------------------------------
# Dashboard KPIs
# -------------------------------
st.divider()
st.subheader("Dashboard")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Order lines", int((kpis or {}).get("total_order_lines", 0)))
k2.metric("% Shipped/Delivered", f"{(kpis or {}).get('pct_shipped_or_delivered', 0)}%")
k3.metric("% Delivered", f"{(kpis or {}).get('pct_delivered', 0)}%")
k4.metric("% Unshipped", f"{(kpis or {}).get('pct_unshipped', 0)}%")
k5.metric("% Late Unshipped", f"{(kpis or {}).get('pct_late_unshipped', 0)}%")

if build_daily_action_list is not None and render_daily_action_list is not None:
    try:
        actions = build_daily_action_list(exceptions=exceptions, followups=followups_open, max_items=10)
        render_daily_action_list(actions)
    except Exception:
        pass

if render_kpi_trends is not None:
    try:
        render_kpi_trends(workspaces_dir=WORKSPACES_DIR, account_id=account_id, store_id=store_id)
    except Exception:
        pass


# -------------------------------
# Ops Triage
# -------------------------------
st.divider()
st.subheader("Ops Triage (Start here)")

if exceptions is None or exceptions.empty:
    st.info("No exceptions found 🎉")
else:
    counts = exceptions["Urgency"].value_counts().to_dict() if "Urgency" in exceptions.columns else {}
    cA, cB, cC, cD = st.columns(4)
    cA.metric("Critical", int(counts.get("Critical", 0)))
    cB.metric("High", int(counts.get("High", 0)))
    cC.metric("Medium", int(counts.get("Medium", 0)))
    cD.metric("Low", int(counts.get("Low", 0)))

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

    preferred_cols = ["Urgency", "order_id", "sku", "issue_type", "customer_country", "supplier_name", "quantity_ordered", "quantity_shipped", "line_status", "explanation", "next_action", "customer_risk"]
    show_cols = [c for c in preferred_cols if c in triage.columns]
    sort_cols = [c for c in ["Urgency", "order_id"] if c in triage.columns]
    if sort_cols:
        triage = triage.sort_values(sort_cols, ascending=True)

    st.dataframe(style_exceptions_table(triage[show_cols].head(10)), use_container_width=True, height=320)
    st.download_button("⬇️ Download Daily Ops Pack ZIP", data=ops_pack_bytes, file_name=pack_name, mime="application/zip")


# ============================================================
# ✅ Ops Outreach (Comms) — grouped, tabbed, non-repetitive
# Put BEFORE Exceptions Queue so it’s “do the work” flow
# ============================================================
st.divider()
st.subheader("Ops Outreach (Comms)")

tab1, tab2, tab3 = st.tabs(["Supplier Follow-ups", "Customer Emails", "Comms Pack"])

with tab1:
    st.caption("Supplier-facing outreach based on OPEN follow-ups (unresolved only).")

    followups_for_ops = followups_open if isinstance(followups_open, pd.DataFrame) else followups

    if followups_for_ops is None or followups_for_ops.empty:
        st.info("No supplier follow-ups needed.")
    else:
        summary_cols = [c for c in ["supplier_name", "supplier_email", "worst_escalation", "urgency", "item_count", "order_ids"] if c in followups_for_ops.columns]
        st.dataframe(followups_for_ops[summary_cols] if summary_cols else followups_for_ops, use_container_width=True, height=220)

        # Supplier email preview + 3 bullet questions generator
        if "supplier_name" in followups_for_ops.columns and len(followups_for_ops) > 0:
            chosen = st.selectbox("Supplier", followups_for_ops["supplier_name"].tolist(), key="supplier_email_preview_select")
            row = followups_for_ops[followups_for_ops["supplier_name"] == chosen].iloc[0]

            supplier_email = str(row.get("supplier_email", "")).strip()
            order_ids = str(row.get("order_ids", "")).strip()
            worst = str(row.get("worst_escalation", "")).strip()

            default_subject = str(row.get("subject", "")).strip()
            if not default_subject:
                default_subject = f"Urgent: shipment status update needed ({chosen})"

            st.markdown("#### Supplier Email Generator (3 questions)")
            subj = st.text_input("Subject", value=default_subject, key="supplier_email_subject")

            bullets = [
                "Can you confirm what’s causing the delay / issue on these shipments?",
                "What is the updated ship date (or delivery ETA) for each impacted order?",
                "Please share tracking numbers (or confirm next step + timeline if tracking is not available yet).",
            ]
            bullet_text = "\n".join([f"• {b}" for b in bullets])

            body_default = "\n".join(
                [
                    f"Hi {chosen},",
                    "",
                    "We’re seeing issues on the following order(s):",
                    f"{order_ids if order_ids else '(order list unavailable)'}",
                    "",
                    "Can you help with the following:",
                    bullet_text,
                    "",
                    "Thanks,",
                ]
            )
            body = st.text_area("Body", value=body_default, height=240, key="supplier_email_body")

            c1, c2, c3 = st.columns(3)
            with c1:
                copy_button(supplier_email, "Copy supplier email", key=f"copy_supplier_email_{chosen}")
            with c2:
                copy_button(subj, "Copy subject", key=f"copy_supplier_subject_{chosen}")
            with c3:
                copy_button(body, "Copy body", key=f"copy_supplier_body_{chosen}")

            st.download_button(
                "Download supplier email as .txt",
                data=(f"To: {supplier_email}\nSubject: {subj}\n\n{body}").encode("utf-8"),
                file_name=f"supplier_email_{str(chosen)}".replace(" ", "_").lower() + ".txt",
                mime="text/plain",
                key="btn_download_supplier_email_txt",
            )

        # Supplier accountability (optional) — safe signature matching
        if build_supplier_accountability_view is not None and render_supplier_accountability is not None:
            st.divider()
            st.markdown("#### Supplier Accountability (Auto)")
            try:
                accountability = call_with_accepted_kwargs(
                    build_supplier_accountability_view,
                    followups=followups_for_ops,
                    followups_df=followups_for_ops,
                    escalations=escalations_df,
                    escalations_df=escalations_df,
                    line_status_df=line_status_df,
                    line_status=line_status_df,
                    exceptions=exceptions,
                    exceptions_df=exceptions,
                )
                render_supplier_accountability(accountability)
            except Exception as e:
                st.warning("Supplier accountability failed to render.")
                st.code(str(e))

with tab2:
    st.caption("Customer-facing updates (email-first).")

    if customer_impact is None or customer_impact.empty:
        st.info("No customer-impact items detected for this run.")
    else:
        # Prefer the dedicated Customer Comms UI (compact, non-repetitive)
        if render_customer_comms_ui is not None:
            try:
                render_customer_comms_ui(customer_impact=customer_impact)
            except TypeError:
                # alternate signature
                render_customer_comms_ui(customer_impact)
        else:
            # Compact fallback generator
            cols = customer_impact.columns.tolist()
            order_col = "order_id" if "order_id" in cols else ("order" if "order" in cols else None)
            email_col = "customer_email" if "customer_email" in cols else ("email" if "email" in cols else None)
            reason_col = "reason" if "reason" in cols else ("issue_summary" if "issue_summary" in cols else None)

            if order_col:
                opts = customer_impact[order_col].fillna("").astype(str).tolist()
                chosen_order = st.selectbox("Select order", opts, key="cust_email_order_select")
                crow = customer_impact[customer_impact[order_col].astype(str) == str(chosen_order)].iloc[0]
            else:
                chosen_order = "(customer item)"
                crow = customer_impact.iloc[0]

            cust_email = str(crow.get(email_col, "")).strip() if email_col else ""
            reason = str(crow.get(reason_col, "")).strip() if reason_col else ""

            subj_default = f"Update on your order {chosen_order}".strip()
            c_subject = st.text_input("Subject", value=subj_default, key="cust_email_subject")

            body_lines = [
                "Hi there,",
                "",
                f"We’re reaching out with an update on your order {chosen_order}.",
            ]
            if reason:
                body_lines += ["", f"Update: {reason}"]
            body_lines += [
                "",
                "What we’re doing next:",
                "• We’ve contacted the supplier/carrier and requested an immediate status update.",
                "• We’re monitoring the shipment and will keep you updated as soon as we have confirmed details.",
                "• If we cannot confirm progress quickly, we will offer next steps (replacement, refund, or alternative).",
                "",
                "Thank you for your patience — we’ll follow up again soon.",
                "",
                "Best,",
            ]
            c_body = st.text_area("Body", value="\n".join(body_lines), height=240, key="cust_email_body")

            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                copy_button(cust_email, "Copy customer email", key=f"copy_customer_email_{chosen_order}")
            with cc2:
                copy_button(c_subject, "Copy subject", key=f"copy_customer_subject_{chosen_order}")
            with cc3:
                copy_button(c_body, "Copy body", key=f"copy_customer_body_{chosen_order}")

with tab3:
    st.caption("Download combined comms artifacts (supplier + customer).")
    if render_comms_pack_download is not None:
        render_comms_pack_download(followups=followups_open, customer_impact=customer_impact)
    else:
        st.info("Comms pack UI module not available.")


# -------------------------------
# Exceptions Queue
# -------------------------------
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

    sort_cols = [c for c in ["Urgency", "order_id"] if c in filtered.columns]
    if sort_cols:
        filtered = filtered.sort_values(sort_cols, ascending=True)

    preferred_cols = ["Urgency", "order_id", "sku", "issue_type", "customer_country", "supplier_name", "quantity_ordered", "quantity_shipped", "line_status", "explanation", "next_action", "customer_risk"]
    show_cols = [c for c in preferred_cols if c in filtered.columns]

    st.dataframe(style_exceptions_table(filtered[show_cols]), use_container_width=True, height=420)
    st.download_button("Download Exceptions CSV", data=filtered.to_csv(index=False).encode("utf-8"), file_name="exceptions_queue.csv", mime="text/csv")


# -------------------------------
# Supplier Scorecards
# -------------------------------
st.divider()
st.subheader("Supplier Scorecards (Performance + Trends)")

if scorecard is None or scorecard.empty:
    st.info("Scorecards require `supplier_name` in your normalized line status data.")
else:
    sc1, sc2 = st.columns(2)
    with sc1:
        top_n = st.slider("Show top N suppliers", min_value=5, max_value=50, value=15, step=5)
    with sc2:
        min_lines = st.number_input("Min total lines", min_value=1, max_value=1000000, value=1, step=1)

    view = scorecard[scorecard["total_lines"] >= int(min_lines)].head(int(top_n))

    show_cols = ["supplier_name", "total_lines", "exception_lines", "exception_rate", "critical", "high", "missing_tracking_flags", "late_flags", "carrier_exception_flags"]
    show_cols = [c for c in show_cols if c in view.columns]
    st.dataframe(view[show_cols], use_container_width=True, height=320)

    st.download_button("Download Supplier Scorecards CSV", data=scorecard.to_csv(index=False).encode("utf-8"), file_name="supplier_scorecards.csv", mime="text/csv")

    with st.expander("Trend over time (from saved runs)", expanded=True):
        runs_for_trend = list_runs(ws_root)
        if not runs_for_trend:
            st.caption("No saved runs yet. Click **Save this run** to build trend history.")
        else:
            max_runs = st.slider("Use last N saved runs", 5, 50, 25, 5)
            hist = load_recent_scorecard_history(str(ws_root), max_runs=int(max_runs))

            if hist is None or hist.empty:
                st.caption("No historical scorecards found yet (save a run first).")
            else:
                supplier_options = sorted(hist["supplier_name"].dropna().unique().tolist())
                chosen_supplier = st.selectbox("Supplier", supplier_options, key="scorecard_trend_supplier")

                s_hist = hist[hist["supplier_name"] == chosen_supplier].copy().sort_values("run_dt")
                chart_df = s_hist[["run_dt", "exception_rate"]].dropna()
                if not chart_df.empty:
                    st.line_chart(chart_df.set_index("run_dt"))

                tcols = ["run_id", "total_lines", "exception_lines", "exception_rate", "critical", "high"]
                tcols = [c for c in tcols if c in s_hist.columns]
                st.dataframe(s_hist[tcols].sort_values("run_id", ascending=False), use_container_width=True, height=220)


# -------------------------------
# SLA Escalations panel (table)
# -------------------------------
if isinstance(escalations_df, pd.DataFrame) and not escalations_df.empty:
    st.divider()
    st.subheader("SLA Escalations (Supplier-level)")
    st.dataframe(escalations_df, use_container_width=True, height=260)
