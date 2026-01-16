# app.py
from __future__ import annotations

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
# BRAND (single source of truth)
# ============================================================
BRAND_NAME = os.getenv("APP_BRAND_NAME", "ClearOps")
TAGLINE = os.getenv(
    "APP_TAGLINE",
    "Operational clarity — exceptions, follow-ups, and visibility in one hub.",
)

# MUST be first Streamlit call (best practice)
st.set_page_config(page_title=BRAND_NAME, layout="wide")


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
# IMPORTANT: If these imports fail, we still show ClearOps branding.
try:
    from normalize import normalize_orders, normalize_shipments, normalize_tracking
    from reconcile import reconcile_all
    from explain import enhance_explanations
except Exception as e:
    st.title(BRAND_NAME)
    st.caption(TAGLINE)
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
    """Calls fn with only the kwargs it actually accepts."""
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
                f"{BRAND_NAME} — Daily Ops Pack\n"
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
    email = st.text_input("Work email", key="auth_email").strip().lower()
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


# ============================================================
# Main header (ALWAYS ClearOps now)
# ============================================================
st.title(BRAND_NAME)
st.caption(TAGLINE)

# A tiny "build stamp" so you can tell Streamlit deployed the latest code
st.caption(
    f"Build stamp: `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%SZ')}` "
    f"(repo: `{os.getenv('STREAMLIT_APP_NAME','')}`)"
)

ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")

# BUGFIX: avoid StreamlitDuplicateElementKey collisions if any other module uses "early_access_code"
code = st.text_input("Enter early access code", type="password", key="auth_early_access_code")

if code != ACCESS_CODE:
    st.info("This app is currently in early access. Enter your code to continue.")
    st.stop()

require_email_access_gate()

# ------------------------------------------------------------
# The rest of your file can remain exactly the same below
# (Paths, sidebar, demo mode, normalize, reconcile, UI, etc.)
# ------------------------------------------------------------
