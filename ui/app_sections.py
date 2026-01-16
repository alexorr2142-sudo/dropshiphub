"""Input + pipeline sections used by app.py.

Split out of app.py to keep files <500 lines while preserving behavior.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import pandas as pd
import streamlit as st


# -----------------------------
# Small shared helpers
# -----------------------------

def call_with_accepted_kwargs(fn: Callable[..., Any], **kwargs):
    sig = inspect.signature(fn)
    accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return fn(**accepted)


def mailto_fallback(to: str, subject: str, body: str) -> str:
    from urllib.parse import quote

    return f"mailto:{quote(to or '')}?subject={quote(subject or '')}&body={quote(body or '')}"


def is_empty_df(x) -> bool:
    return (x is None) or (not isinstance(x, pd.DataFrame)) or x.empty


# -----------------------------
# Sections: Start + Upload
# -----------------------------

def render_start_here(
    *,
    data_dir: Path,
    demo_mode_active: bool,
    ensure_demo_state: Optional[Callable[..., Any]] = None,
    render_demo_editor: Optional[Callable[..., Any]] = None,
):
    st.subheader("Start here")
    if callable(ensure_demo_state):
        ensure_demo_state(data_dir)
    if callable(render_demo_editor):
        render_demo_editor()
        return

    if demo_mode_active:
        st.info("Demo mode is ON but demo editor UI module is not available.")
    else:
        st.info("Turn on **Demo Mode (Sticky)** in the sidebar to play with demo data (edits persist).")


def render_upload_and_templates(
    *,
    render_upload_section: Optional[Callable[..., Any]] = None,
    render_template_downloads: Optional[Callable[..., Any]] = None,
):
    st.divider()
    uploads = None

    if callable(render_upload_section):
        uploads = render_upload_section()
    else:
        st.subheader("Upload your data")
        c1, c2, c3 = st.columns(3)
        with c1:
            f_orders = st.file_uploader(
                "Orders CSV (Shopify export or generic)", type=["csv"], key="uploader_orders"
            )
        with c2:
            f_shipments = st.file_uploader("Shipments CSV (supplier export)", type=["csv"], key="uploader_shipments")
        with c3:
            f_tracking = st.file_uploader("Tracking CSV\n(optional)", type=["csv"], key="uploader_tracking")

        uploads = type(
            "U",
            (),
            {
                "f_orders": f_orders,
                "f_shipments": f_shipments,
                "f_tracking": f_tracking,
                "has_uploads": (f_orders is not None and f_shipments is not None),
            },
        )

    if callable(render_template_downloads):
        render_template_downloads()

    return uploads


def resolve_raw_inputs(
    *,
    demo_mode_active: bool,
    data_dir: Path,
    uploads: Any,
    get_active_raw_inputs: Optional[Callable[..., Any]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (raw_orders, raw_shipments, raw_tracking), stopping the app if needed."""

    if callable(get_active_raw_inputs):
        return get_active_raw_inputs(
            demo_mode_active,
            data_dir,
            uploads.f_orders,
            uploads.f_shipments,
            uploads.f_tracking,
        )

    if not (demo_mode_active or getattr(uploads, "has_uploads", False)):
        st.info("Upload Orders + Shipments, or turn on **Demo Mode (Sticky)** in the sidebar to begin.")
        st.stop()

    if demo_mode_active:
        raw_orders = st.session_state.get("demo_raw_orders", pd.DataFrame())
        raw_shipments = st.session_state.get("demo_raw_shipments", pd.DataFrame())
        raw_tracking = st.session_state.get("demo_raw_tracking", pd.DataFrame())
        return raw_orders, raw_shipments, raw_tracking

    raw_orders = pd.read_csv(uploads.f_orders)
    raw_shipments = pd.read_csv(uploads.f_shipments)
    raw_tracking = pd.read_csv(uploads.f_tracking) if uploads.f_tracking else pd.DataFrame()
    return raw_orders, raw_shipments, raw_tracking


# -----------------------------
# Pipeline: Normalize + Reconcile
# -----------------------------

def normalize_inputs(
    *,
    raw_orders: pd.DataFrame,
    raw_shipments: pd.DataFrame,
    raw_tracking: pd.DataFrame,
    normalize_orders: Callable[..., Any],
    normalize_shipments: Callable[..., Any],
    normalize_tracking: Callable[..., Any],
    account_id: str,
    store_id: str,
    platform_hint: str,
    default_currency: str,
    default_promised_ship_days: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    st.divider()
    st.subheader("Data checks")

    orders, meta_o = normalize_orders(
        raw_orders,
        account_id=account_id,
        store_id=store_id,
        platform_hint=platform_hint,
        default_currency=default_currency,
        default_promised_ship_days=int(default_promised_ship_days),
    )
    shipments, meta_s = normalize_shipments(raw_shipments, account_id=account_id, store_id=store_id)

    tracking = pd.DataFrame()
    meta_t: Dict[str, Any] = {"validation_errors": []}
    if raw_tracking is not None and isinstance(raw_tracking, pd.DataFrame) and not raw_tracking.empty:
        tracking, meta_t = normalize_tracking(raw_tracking, account_id=account_id, store_id=store_id)

    errs = (
        meta_o.get("validation_errors", [])
        + meta_s.get("validation_errors", [])
        + meta_t.get("validation_errors", [])
    )
    if errs:
        st.warning("We found some schema issues. You can still proceed, but fixing these improves accuracy:")
        for e in errs:
            st.write("- ", e)
    else:
        st.success("Looks good ✅")

    meta = {"meta_o": meta_o, "meta_s": meta_s, "meta_t": meta_t, "validation_errors": errs}
    return orders, shipments, tracking, meta


def reconcile_with_debug(
    *,
    orders: pd.DataFrame,
    shipments: pd.DataFrame,
    tracking: pd.DataFrame,
    reconcile_all: Callable[..., Any],
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    st.divider()
    st.subheader("Running reconciliation")

    try:
        line_status_df, exceptions, followups, order_rollup, kpis = reconcile_all(orders, shipments, tracking)
        return line_status_df, exceptions, followups, order_rollup, (kpis if isinstance(kpis, dict) else {})
    except Exception as e:
        st.error("Reconciliation failed. Showing debug details below.")
        st.markdown("### Debug: normalized inputs")
        st.write("orders columns:", list(orders.columns))
        st.write("shipments columns:", list(shipments.columns))
        st.write("tracking columns:", list(tracking.columns) if isinstance(tracking, pd.DataFrame) else tracking)
        st.markdown("### Error")
        st.code(str(e))
        with st.expander("Preview orders (head)", expanded=False):
            st.dataframe(orders.head(5), use_container_width=True)
        with st.expander("Preview shipments (head)", expanded=False):
            st.dataframe(shipments.head(5), use_container_width=True)
        with st.expander("Preview tracking (head)", expanded=False):
            st.dataframe(tracking.head(5), use_container_width=True)
        st.stop()


def stop_if_missing_required_inputs(
    *,
    raw_orders: pd.DataFrame,
    raw_shipments: pd.DataFrame,
    raw_tracking: pd.DataFrame,
):
    if not is_empty_df(raw_orders) and not is_empty_df(raw_shipments):
        return

    st.divider()
    st.subheader("Data checks")
    st.warning("We found some schema issues. You can still proceed, but fixing these improves accuracy:")

    if is_empty_df(raw_orders):
        st.write("- [orders] Input orders dataframe is empty.")
    if is_empty_df(raw_shipments):
        st.write("- [shipments] Input shipments dataframe is empty.")

    st.error(
        "Cannot run reconciliation without Orders + Shipments data (missing required columns like order_id and sku)."
    )

    with st.expander("Debug (raw input shapes / columns)", expanded=False):
        st.write("raw_orders shape:", raw_orders.shape)
        st.write("raw_orders columns:", list(raw_orders.columns))
        st.write("raw_shipments shape:", raw_shipments.shape)
        st.write("raw_shipments columns:", list(raw_shipments.columns))
        st.write("raw_tracking shape:", raw_tracking.shape)
        st.write("raw_tracking columns:", list(raw_tracking.columns))

    st.stop()
