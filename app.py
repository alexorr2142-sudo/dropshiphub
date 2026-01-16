# app.py
from __future__ import annotations

import os
import json
import io
import zipfile
import shutil
import inspect
from datetime import datetime, timezone
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

# MUST be first Streamlit call
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

# Optional UI/components
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

# Local pipeline modules
try:
    from normalize import normalize_orders, normalize_shipments, normalize_tracking  # noqa: F401
    from reconcile import reconcile_all  # noqa: F401
    from explain import enhance_explanations  # noqa: F401
except Exception as e:
    st.title(BRAND_NAME)
    st.caption(TAGLINE)
    st.error("Import error: one of your local .py files is missing or has an error.")
    st.code(str(e))
    st.stop()


# ============================================================
# Helpers (unchanged)
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
    sig = inspect.signature(fn)
    accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return fn(**accepted)


# -------------------------------
# Access gate (keep behavior)
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


# ============================================================
# Main header (ONLY ONCE)
# ============================================================
st.title(BRAND_NAME)
st.caption(TAGLINE)

# Build stamp (timezone-aware)
st.caption(
    f"Build stamp: `{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}` "
    f"(repo: `{os.getenv('STREAMLIT_APP_NAME','')}`)"
)

# ============================================================
# Early access gate (ONLY ONCE)
# ============================================================
ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")
code = st.text_input("Enter early access code", type="password", key="auth_early_access_code")
if code != ACCESS_CODE:
    st.info("This app is currently in early access. Enter your code to continue.")
    st.stop()

require_email_access_gate()


# ============================================================
# RENDER THE REST OF THE APP (if present)
# ============================================================
# IMPORTANT: This file is currently acting as a safe orchestrator.
# If you have a separate UI entrypoint function, we call it here.
# This prevents legacy headers / gates from being rendered twice.
try:
    from ui.app_shell import render_app  # type: ignore
except Exception:
    render_app = None  # type: ignore

if render_app is None:
    st.warning(
        "App shell not found (ui/app_shell.py). "
        "Your repo appears to be missing the main rendering logic below the access gates. "
        "If you expected sidebar/demo/pages, paste your full current app.py (the ~480+ line one) "
        "or add ui/app_shell.py with render_app()."
    )
    st.stop()

# Delegate to UI shell (keeps app.py clean)
render_app()
