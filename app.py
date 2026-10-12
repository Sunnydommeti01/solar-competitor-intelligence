"""Streamlit dashboard for PM Surya Ghar vendor intelligence.

No CSV dependency. Live requests require a verified encrypted request builder.
"""
import streamlit as st
import pandas as pd

from api_client import VendorAPIClient, VendorAPIError
from extractor import extract_district, to_excel_bytes
from config import STATES

st.set_page_config(page_title="Solar Competitor Intelligence", page_icon="☀️", layout="wide")
st.title("☀️ Solar Competitor Intelligence")
st.caption("PM Surya Ghar | District-wise vendor installations")
st.warning("Live extraction is not configured yet: the portal's encrypted request builder must be verified.")

state = st.selectbox("State", STATES)
district = st.text_input("District (exact portal label)", value="Eluru" if state == "Andhra Pradesh" else "Hyderabad")

if st.button("Fetch live vendor data", type="primary"):
    if not district.strip():
        st.error("Enter a district name.")
    else:
        try:
            client = VendorAPIClient()  # Needs credentials AND a verified request_builder.
            with st.spinner("Fetching live vendor data..."):
                df = extract_district(state, district.strip(), client)
            st.session_state["vendors"] = df
            st.session_state["selection"] = (state, district.strip())
        except (VendorAPIError, ValueError, RuntimeError) as exc:
            st.error(f"Live API extraction unavailable: {exc}")
        except Exception as exc:
            st.error(f"Unexpected error: {type(exc).__name__}: {exc}")

if "vendors" in st.session_state:
    df = st.session_state["vendors"]
    selected_state, selected_district = st.session_state["selection"]
    st.subheader(f"Results: {selected_state} / {selected_district}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Vendor records", len(df))
    c2.metric("District installations", f"{df['Installations'].sum():,.0f}")
    c3.metric("Missing installation counts", int(df['Installations'].isna().sum()))
    query = st.text_input("Search vendor")
    shown = df[df["Vendor Name"].fillna("").str.contains(query, case=False, regex=False)] if query else df
    st.dataframe(shown.sort_values("Installations", ascending=False, na_position="last"), use_container_width=True, hide_index=True)
    st.download_button(
        "Download Excel",
        data=to_excel_bytes(df),
        file_name="solar_competitor_intelligence.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("No live data loaded. The API request builder must be completed before fetching data.")
