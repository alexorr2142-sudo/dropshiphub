# ui/auth.py
from __future__ import annotations

import os
import streamlit as st


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


# -------------------------------------------------
# Legacy compatibility (NO UI RENDERING)
# -------------------------------------------------
def early_access_gate(access_code: str):
    """
    Legacy shim.
    DO NOT render UI here.
    app.py owns early access UI.
    """
    return


def require_early_access_code_gate(
    *,
    public_review_mode: bool = False,
    env_var: str = "DSH_ACCESS_CODE",
    default_code: str = "early2026",
    key: str = "auth_access_code",
) -> None:
    """
    Legacy shim.
    DO NOT render UI here.
    """
    return


def require_email_access_gate(
    *,
    public_review_mode: bool = False,
    key: str = "auth_work_email",
) -> None:
    """
    Legacy shim.
    Email gate is now owned by app.py.
    """
    return


def require_access(
    *,
    public_review_mode: bool = False,
) -> None:
    """
    Legacy shim.
    """
    return
