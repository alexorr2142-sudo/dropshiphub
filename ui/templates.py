# ui/templates.py
from __future__ import annotations

import io
import zipfile

import pandas as pd
import streamlit as st


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, b in files.items():
            z.writestr(name, b)
    buf.seek(0)
    return buf.read()


def render_template_downloads(
    *,
    key_prefix: str = "tmpl",
    title: str = "Download ClearOps templates",
    expanded: bool = False,
    show_preview: bool = False,
) -> None:
    """
    Renders CSV template downloads for:
      - shipments_template.csv
      - tracking_template.csv
      - suppliers_template.csv

    Adds optional:
      - Download all as ZIP
      - Template preview (disabled by default)
    """
    with st.expander(title, expanded=expanded):
        st.caption(
            "Use these templates if your exports don’t match the expected column names. "
            "You can upload your own CSVs too — these are just starting points for ClearOps."
        )

        # ----------------------------
        # Templates
        # ----------------------------
        shipments_template = pd.DataFrame(
            columns=[
                "Supplier",
                "Supplier Order ID",
                "Order ID",
                "SKU",
                "Quantity",
                "Ship Date",
                "Carrier",
                "Tracking",
                "From Country",
                "To Country",
            ]
        )

        tracking_template = pd.DataFrame(
            columns=[
                "Carrier",
                "Tracking Number",
                "Order ID",
                "Supplier Order ID",
                "Status",
                "Last Update",
                "Delivered At",
                "Exception",
            ]
        )

        suppliers_template = pd.DataFrame(
            columns=[
                "supplier_name",
                "supplier_email",
                "supplier_channel",
                "language",
                "timezone",
            ]
        )

        # ----------------------------
        # Downloads (3)
        # ----------------------------
        t1, t2, t3 = st.columns(3)

        with t1:
            st.download_button(
                "Shipments template CSV",
                data=_df_to_csv_bytes(shipments_template),
                file_name="shipments_template.csv",
                mime="text/csv",
                key=f"{key_prefix}_shipments",
                use_container_width=True,
            )
            st.caption("Supplier shipment confirmations (recommended).")

        with t2:
            st.download_button(
                "Tracking template CSV",
                data=_df_to_csv_bytes(tracking_template),
                file_name="tracking_template.csv",
                mime="text/csv",
                key=f"{key_prefix}_tracking",
                use_container_width=True,
            )
            st.caption("Optional carrier tracking rollup.")

        with t3:
            st.download_button(
                "Suppliers template CSV",
                data=_df_to_csv_bytes(suppliers_template),
                file_name="suppliers_template.csv",
                mime="text/csv",
                key=f"{key_prefix}_suppliers",
                use_container_width=True,
            )
            st.caption("Supplier Directory (CRM) for auto-filled follow-ups.")

        # ----------------------------
        # Download all as ZIP
        # ----------------------------
        zip_data = _zip_bytes(
            {
                "shipments_template.csv": _df_to_csv_bytes(shipments_template),
                "tracking_template.csv": _df_to_csv_bytes(tracking_template),
                "suppliers_template.csv": _df_to_csv_bytes(suppliers_template),
                "README.txt": (
                    "ClearOps — Template Pack\n\n"
                    "Purpose:\n"
                    "These CSV templates help you get started quickly in ClearOps if your\n"
                    "exports don’t already match the expected column names.\n\n"
                    "Files:\n"
                    " - shipments_template.csv: supplier shipment confirmations (recommended)\n"
                    " - tracking_template.csv: carrier tracking rollup (optional)\n"
                    " - suppliers_template.csv: supplier contact directory (CRM)\n\n"
                    "You can upload your own CSVs at any time — templates are optional.\n"
                ).encode("utf-8"),
            }
        )

        st.download_button(
            "⬇️ Download all templates (ZIP)",
            data=zip_data,
            file_name="clearops_templates.zip",
            mime="application/zip",
            key=f"{key_prefix}_zip_all",
            use_container_width=True,
        )

        # ----------------------------
        # Optional previews
        # ----------------------------
        if show_preview:
            with st.expander("Preview templates", expanded=False):
                p1, p2, p3 = st.columns(3)
                with p1:
                    st.caption("Shipments template")
                    st.dataframe(shipments_template, use_container_width=True, height=160)
                with p2:
                    st.caption("Tracking template")
                    st.dataframe(tracking_template, use_container_width=True, height=160)
                with p3:
                    st.caption("Suppliers template")
                    st.dataframe(suppliers_template, use_container_width=True, height=160)
