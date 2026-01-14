# ui/auth.py
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

def early_access_gate(access_code: str):
    st.title("Dropship Hub — Early Access")
    st.caption("Drop ship made easy — exceptions, follow-ups, and visibility in one hub.")
    code = st.text_input("Enter early access code", type="password", key="access_code")
    if code != access_code:
        st.info("This app is currently in early access. Enter your code to continue.")
        st.stop()

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
