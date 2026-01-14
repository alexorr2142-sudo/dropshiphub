# ui/templates.py
import pandas as pd
import streamlit as st

def render_template_downloads():
    st.subheader("Download templates")

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
        columns=["supplier_name", "supplier_email", "supplier_channel", "language", "timezone"]
    )

    t1, t2, t3 = st.columns(3)
    with t1:
        st.download_button(
            "Shipments template CSV",
            data=shipments_template.to_csv(index=False).encode("utf-8"),
            file_name="shipments_template.csv",
            mime="text/csv",
        )
    with t2:
        st.download_button(
            "Tracking template CSV",
            data=tracking_template.to_csv(index=False).encode("utf-8"),
            file_name="tracking_template.csv",
            mime="text/csv",
        )
    with t3:
        st.download_button(
            "Suppliers template CSV",
            data=suppliers_template.to_csv(index=False).encode("utf-8"),
            file_name="suppliers_template.csv",
            mime="text/csv",
        )
