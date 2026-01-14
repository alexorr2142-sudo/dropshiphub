import streamlit as st
import os

# -------------------------------
# Early Access Gate (Step 6D)
# -------------------------------
ACCESS_CODE = os.getenv("DSH_ACCESS_CODE", "early2026")

st.title("Dropship Hub — Early Access")

code = st.text_input("Enter early access code", type="password")

if code != ACCESS_CODE:
    st.info("This app is currently in early access. Enter your code to continue.")
    st.stop()

# -------------------------------
# App starts here
# -------------------------------
st.subheader("Manage your dropshipping operation from one hub")
st.write("App skeleton is live.")
