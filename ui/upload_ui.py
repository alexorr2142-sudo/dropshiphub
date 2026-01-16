# ui/upload_ui.py
from __future__ import annotations

from dataclasses import dataclass
import streamlit as st


@dataclass
class UploadInputs:
    f_orders: object | None
    f_shipments: object | None
    f_tracking: object | None
    has_uploads: bool


def render_upload_section(*, key_prefix: str = "uploader") -> UploadInputs:
    """
    Renders the 3 CSV uploaders and returns the uploaded file objects.

    Mirrors app.py behavior:
      - Orders CSV required (unless demo mode)
      - Shipments CSV required (unless demo mode)
      - Tracking optional
    """
    st.subheader("Upload your data")

    col1, col2, col3 = st.columns(3)
    with col1:
        f_orders = st.file_uploader(
            "Orders CSV (Shopify export or generic)",
            type=["csv"],
            key=f"{key_prefix}_orders",
        )
    with col2:
        f_shipments = st.file_uploader(
            "Shipments CSV (supplier export)",
            type=["csv"],
            key=f"{key_prefix}_shipments",
        )
    with col3:
        f_tracking = st.file_uploader(
            "Tracking CSV (shipping co export)",
            type=["csv"],
            key=f"{key_prefix}_tracking",
        )

    has_uploads = (f_orders is not None) and (f_shipments is not None)

    return UploadInputs(
        f_orders=f_orders,
        f_shipments=f_shipments,
        f_tracking=f_tracking,
        has_uploads=has_uploads,
    )


def enforce_demo_or_uploads_ready(*, demo_mode_active: bool, has_uploads: bool) -> None:
    """
    Enforces the same early stop behavior from app.py:
      If NOT demo mode AND NOT (orders+shipments uploaded) -> show message + stop.

    Keep this separate so app.py stays tiny and testable.
    """
    if not (demo_mode_active or has_uploads):
        st.info("Upload Orders + Shipments, or turn on **Demo Mode (Sticky)** in the sidebar to begin.")
        st.stop()
