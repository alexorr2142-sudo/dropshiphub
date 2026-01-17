"""Streamlit UI sections for demo + uploads + choosing raw inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional, Tuple

import pandas as pd
import streamlit as st


def render_start_here(
    *,
    data_dir: Path,
    demo_mode_active: bool,
    ensure_demo_state: Optional[Callable[..., Any]] = None,
    render_demo_editor: Optional[Callable[..., Any]] = None,
) -> None:
    st.subheader("Start here")

    # Demo state should be initialized early so the rest of the app can run safely
    if callable(ensure_demo_state):
        ensure_demo_state(data_dir)

    # If the demo editor exists, let it own this section
    if callable(render_demo_editor):
        render_demo_editor()
        return

    if demo_mode_active:
        st.info("ClearOps Demo is ON, but the demo editor UI module is not available.")
    else:
        st.info("Turn on **ClearOps Demo (Sticky)** in the sidebar to explore demo data (edits persist).")


def render_upload_section_fallback():
    st.subheader("Upload your data")
    st.caption("Upload Orders + Shipments to run ClearOps. Tracking is optional.")
    c1, c2, c3 = st.columns(3)
    with c1:
        f_orders = st.file_uploader(
            "Orders CSV (platform export or generic)",
            type=["csv"],
            key="uploader_orders",
        )
    with c2:
        f_shipments = st.file_uploader(
            "Shipments CSV (supplier / 3PL export)",
            type=["csv"],
            key="uploader_shipments",
        )
    with c3:
        f_tracking = st.file_uploader(
            "Tracking CSV (optional)",
            type=["csv"],
            key="uploader_tracking",
        )

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
    return uploads


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
        uploads = render_upload_section_fallback()

    if callable(render_template_downloads):
        render_template_downloads()

    return uploads


def resolve_raw_inputs(
    *,
    demo_mode_active: bool,
    data_dir: Path,
    uploads,
    get_active_raw_inputs: Optional[Callable[..., Any]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (raw_orders, raw_shipments, raw_tracking).

    Matches the behavior in the original app.py, including stop conditions.
    """

    if callable(get_active_raw_inputs):
        return get_active_raw_inputs(
            demo_mode_active,
            data_dir,
            uploads.f_orders,
            uploads.f_shipments,
            uploads.f_tracking,
        )

    if not (demo_mode_active or uploads.has_uploads):
        st.info("Upload Orders + Shipments, or turn on **ClearOps Demo (Sticky)** in the sidebar to begin.")
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
