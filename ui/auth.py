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


def _access_code_value(env_var: str = "DSH_ACCESS_CODE", default_code: str = "early2026") -> str:
    return os.getenv(env_var, default_code) or ""


def _already_authed_in_session(
    *,
    env_var: str = "DSH_ACCESS_CODE",
    default_code: str = "early2026",
) -> bool:
    """
    If app.py already ran the gates, those widget values will be in session_state.
    We treat that as canonical and do NOT render duplicate gates.

    We check multiple historical keys for backward compatibility.
    """
    access_code = _access_code_value(env_var=env_var, default_code=default_code)

    # Early access code keys we've used historically
    code_keys = ["auth_early_access_code", "auth_access_code", "early_access_code"]
    code_val = ""
    for k in code_keys:
        v = st.session_state.get(k)
        if isinstance(v, str) and v.strip():
            code_val = v.strip()
            break

    if code_val != access_code:
        return False

    # Email keys we've used historically
    email_keys = ["auth_email", "auth_work_email"]
    email_val = ""
    for k in email_keys:
        v = st.session_state.get(k)
        if isinstance(v, str) and v.strip():
            email_val = v.strip().lower()
            break

    allowed = get_allowed_emails()

    # If allowlist is disabled, code match is enough.
    if not allowed:
        return True

    return bool(email_val) and (email_val in allowed)


# -------------------------------------------------
# Backward-compatible wrapper (so older imports work)
# -------------------------------------------------
def early_access_gate(access_code: str):
    """
    Compatibility wrapper for older code that imports:
      from ui.auth import early_access_gate

    IMPORTANT:
      - uses the SAME widget key as the main app gate to avoid duplicates
      - is idempotent (won't re-render if already authed)
    """
    access_code = access_code or ""
    # If app.py already validated, do nothing.
    if st.session_state.get("auth_early_access_code", "").strip() == access_code:
        return

    st.subheader("Early access")
    code = st.text_input("Enter early access code", type="password", key="auth_early_access_code")
    if code != access_code:
        st.info("This app is currently in early access. Enter your code to continue.")
        st.stop()


def require_early_access_code_gate(
    *,
    public_review_mode: bool = False,
    env_var: str = "DSH_ACCESS_CODE",
    default_code: str = "early2026",
    key: str = "auth_early_access_code",
) -> None:
    """
    Early access gate:
      - bypassed when public_review_mode=True
      - compares against env var DSH_ACCESS_CODE (or default_code)
      - idempotent if the user already passed gates via app.py
    """
    if public_review_mode:
        return

    # If already authed, do nothing.
    if _already_authed_in_session(env_var=env_var, default_code=default_code):
        return

    access_code = _access_code_value(env_var=env_var, default_code=default_code)

    st.subheader("Early access")
    code = st.text_input("Enter early access code", type="password", key=key)
    if code != access_code:
        st.info("This app is currently in early access. Enter your code to continue.")
        st.stop()


def require_email_access_gate(
    *,
    public_review_mode: bool = False,
    key: str = "auth_email",
) -> None:
    """
    Email allowlist gate:
      - bypassed when public_review_mode=True
      - allowlist from st.secrets['ALLOWED_EMAILS'] + env DSH_ALLOWED_EMAILS
      - if allowlist is empty: verification disabled (accept all emails)
      - idempotent if the user already passed gates via app.py
    """
    if public_review_mode:
        return

    # If already authed, do nothing.
    if _already_authed_in_session():
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

    Now idempotent: if app.py already authenticated, this does nothing.
    """
    if public_review_mode:
        return

    if _already_authed_in_session():
        return

    require_early_access_code_gate(public_review_mode=public_review_mode)
    require_email_access_gate(public_review_mode=public_review_mode)
