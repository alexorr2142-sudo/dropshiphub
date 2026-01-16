# ui/auth.py
from __future__ import annotations

import os
import streamlit as st


# -------------------------------
# Internal session flags
# -------------------------------
_ACCESS_CODE_OK_FLAG = "_clearops_access_code_ok"
_ACCESS_EMAIL_OK_FLAG = "_clearops_access_email_ok"


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


def _get_first_session_value(keys: list[str]) -> str:
    """
    Returns the first non-empty string found in st.session_state for any of the given keys.
    """
    for k in keys:
        try:
            v = st.session_state.get(k, "")
        except Exception:
            v = ""
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _mark_access_code_ok() -> None:
    st.session_state[_ACCESS_CODE_OK_FLAG] = True


def _mark_access_email_ok() -> None:
    st.session_state[_ACCESS_EMAIL_OK_FLAG] = True


def _access_code_already_ok() -> bool:
    return bool(st.session_state.get(_ACCESS_CODE_OK_FLAG, False))


def _access_email_already_ok() -> bool:
    return bool(st.session_state.get(_ACCESS_EMAIL_OK_FLAG, False))


# -------------------------------------------------
# Backward-compatible wrapper (so app.py imports work)
# -------------------------------------------------
def early_access_gate(access_code: str):
    """
    Compatibility wrapper for older app.py imports:
      from ui.auth import early_access_gate

    Bugfix:
      - Do not render a second gate if the user already passed elsewhere.
      - Recognize codes entered using app.py's keys to avoid duplicate prompts.
    """
    if _access_code_already_ok():
        return

    # If app.py already collected a code, honor it.
    existing = _get_first_session_value(
        [
            "auth_early_access_code",  # app.py (new)
            "auth_access_code",        # this module (old/default)
            "early_access_code",       # legacy
        ]
    )
    if existing and existing == (access_code or ""):
        _mark_access_code_ok()
        return

    st.subheader("Early access")
    code = st.text_input("Enter early access code", type="password", key="auth_access_code")
    if code != (access_code or ""):
        st.info("This app is currently in early access. Enter your code to continue.")
        st.stop()

    _mark_access_code_ok()


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

    Bugfix:
      - Idempotent: once passed, it won't render again on the same session.
      - Recognizes code entered under app.py key to avoid duplicate prompts.
    """
    if public_review_mode:
        return

    if _access_code_already_ok():
        return

    access_code = os.getenv(env_var, default_code)

    # If another part of the app already collected a code, honor it.
    existing = _get_first_session_value(
        [
            "auth_early_access_code",  # app.py (new)
            key,                       # caller-provided key (default: auth_access_code)
            "auth_access_code",        # this module legacy/default
            "early_access_code",       # legacy
        ]
    )
    if existing and existing == access_code:
        _mark_access_code_ok()
        return

    st.subheader("Early access")
    code = st.text_input("Enter early access code", type="password", key=key)
    if code != access_code:
        st.info("This app is currently in early access. Enter your code to continue.")
        st.stop()

    _mark_access_code_ok()


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

    Bugfix:
      - Idempotent: once passed, it won't render again on the same session.
      - Recognizes email entered under app.py key to avoid duplicate prompts.
    """
    if public_review_mode:
        return

    if _access_email_already_ok():
        return

    allowed = get_allowed_emails()

    # If allowlist is empty, email verification is disabled.
    # Mark as OK and do not render (prevents duplicate "Access" blocks).
    if not allowed:
        _mark_access_email_ok()
        return

    # If another part of the app already collected email, honor it.
    existing_email = _get_first_session_value(
        [
            "auth_email",        # app.py
            key,                 # caller-provided (default: auth_work_email)
            "auth_work_email",   # this module default
            "auth_email",        # legacy variants
        ]
    ).lower()

    if existing_email and existing_email in allowed:
        _mark_access_email_ok()
        return

    st.subheader("Access")
    email = st.text_input("Work email", key=key).strip().lower()

    if not email:
        st.info("Enter your work email to continue.")
        st.stop()
    if email not in allowed:
        st.error("This email is not authorized for early access.")
        st.caption("Ask the admin to add your email to the allowlist.")
        st.stop()

    st.success("Email verified ✅")
    _mark_access_email_ok()


def require_access(
    *,
    public_review_mode: bool = False,
) -> None:
    """
    Single entrypoint to enforce access:
      1) early access code
      2) email allowlist

    Bugfix:
      - Safe to call multiple times from multiple pages/modules.
      - Won't duplicate UI once gates are satisfied.
    """
    require_early_access_code_gate(public_review_mode=public_review_mode)
    require_email_access_gate(public_review_mode=public_review_mode)
