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
# Backward-compatible wrapper (so app.py imports work)
# -------------------------------------------------
def early_access_gate(access_code: str):
    """
    Compatibility wrapper for older app.py imports:
      from ui.auth import early_access_gate

    Uses the same widget key as the newer gate to avoid duplicates.
    """
    st.subheader("Early access")
    code = st.text_input("Enter early access code", type="password", key="auth_access_code")
    if code != (access_code or ""):
        st.info("This app is currently in early access. Enter your code to continue.")
        st.stop()


def require_early_access_code_gate(
    *,
    public_review_mode: bool = False,
    env_var: str = "DSH_ACCESS_CODE",
    default_code: str = "early2026",
    key: str = "auth_access_code",
) -> None:
    """
    Early access gate:
      - bypassed when public_review_mode=True
      - compares against env var DSH_ACCESS_CODE (or default_code)
    """
    if public_review_mode:
        return

    access_code = os.getenv(env_var, default_code)

    st.subheader("Early access")
    code = st.text_input("Enter early access code", type="password", key=key)
    if code != access_code:
        st.info("This app is currently in early access. Enter your code to continue.")
        st.stop()


def require_email_access_gate(
    *,
    public_review_mode: bool = False,
    key: str = "auth_work_email",
) -> None:
    """
    Email allowlist gate:
      - bypassed when public_review_mode=True
      - allowlist from st.secrets['ALLOWED_EMAILS'] + env DSH_ALLOWED_EMAILS
      - if allowlist is empty: verification disabled (accept all emails)
    """
    if public_review_mode:
        return

    st.subheader("Access")
    email = st.text_input("Work email", key=key).strip().lower()
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


def require_access(
    *,
    public_review_mode: bool = False,
) -> None:
    """
    Single entrypoint to enforce access:
      1) early access code
      2) email allowlist
    """
    require_early_access_code_gate(public_review_mode=public_review_mode)
    require_email_access_gate(public_review_mode=public_review_mode)
