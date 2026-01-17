"""Backwards-compatible reconciliation API.

Keep this file small (<300 lines). Implementation lives in core/reconcile_engine.py
"""

from __future__ import annotations

from core.reconcile_engine import reconcile_all

__all__ = ["reconcile_all"]
