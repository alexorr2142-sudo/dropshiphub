"""Small helpers shared across Streamlit UI modules."""

from __future__ import annotations

import inspect
from typing import Any, Callable

import pandas as pd


def call_with_accepted_kwargs(fn: Callable[..., Any], **kwargs):
    """Call fn with only the kwargs it accepts."""
    sig = inspect.signature(fn)
    accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return fn(**accepted)


def mailto_fallback(to: str, subject: str, body: str) -> str:
    """Safe mailto generator used when core.email_utils.mailto_link is unavailable."""
    from urllib.parse import quote

    return f"mailto:{quote(to or '')}?subject={quote(subject or '')}&body={quote(body or '')}"


def is_empty_df(x) -> bool:
    return (x is None) or (not isinstance(x, pd.DataFrame)) or x.empty
