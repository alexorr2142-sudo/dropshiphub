# onboarding_ui.py (root-level)
from __future__ import annotations

"""
Backward-compatible onboarding wrapper.

Why this exists:
- The repo has BOTH:
    - onboarding_ui.py   (root)
    - ui/onboarding_ui.py (package)

If any legacy code imports the root module (import onboarding_ui),
we must ensure it does NOT render legacy "Dropship Hub" headers or gates.

This file:
- contains ZERO Streamlit UI at import-time
- delegates to ui.onboarding_ui when available
- preserves function names to avoid breaking existing workflows
"""

from typing import Callable, Optional


def _safe_import_render() -> Optional[Callable[..., None]]:
    try:
        # Preferred: new module in /ui
        from ui.onboarding_ui import render_onboarding_checklist  # type: ignore

        return render_onboarding_checklist
    except Exception:
        return None


def render_onboarding_checklist(*, title: str = "ClearOps onboarding checklist (14 steps)", expanded: bool = True) -> None:
    """
    Compatibility entrypoint:
      - older code may call onboarding_ui.render_onboarding_checklist(...)
      - we route it to ui.onboarding_ui.render_onboarding_checklist when present

    IMPORTANT:
      - This function intentionally does not render any app title/caption/auth.
      - Branding + access gates must live in app.py only.
    """
    fn = _safe_import_render()
    if fn is None:
        # Fail safely: don't crash the app if optional UI is missing
        try:
            import streamlit as st  # local import to avoid side effects at import-time

            st.warning("Onboarding UI module not found (ui/onboarding_ui.py).")
        except Exception:
            pass
        return

    fn(title=title, expanded=expanded)
