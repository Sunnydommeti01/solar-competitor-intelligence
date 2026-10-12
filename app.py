"""Solar Competitor Intelligence — live API integration readiness dashboard."""
import streamlit as st
import pandas as pd
from api_client import APIIntegrationPending
from extractor import extract_district, to_excel_bytes
from config import STATES

st.set_page_config(page_title='Solar Competitor Intelligence', page_icon='☀️', layout='wide')
st.title('☀️ Solar Competitor Intelligence')
st.caption('PM Surya Ghar | District-wise vendor comparison | Live API integration pending')
st.warning('Live API fetching is NOT yet operational: the portal uses an encrypted POST body and x-ts header. This app does not use a static CSV or display invented results.')
state = st.selectbox('State', STATES)
district = st.text_input('District (exact portal label)', value='Eluru' if state == 'Andhra Pradesh' else 'Hyderabad')
if st.button('Fetch live vendor data', type='primary'):
    try:
        with st.spinner('Contacting portal…'):
            df = extract_district(state, district.strip())
        if df.empty:
            st.info('API returned no vendors for this district.')
        else:
            st.session_state['vendors'] = df
            st.session_state['selection'] = (state, district.strip())
    except APIIntegrationPending as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f'Live request failed: {exc}')

if 'vendors' in st.session_state:
    df = st.session_state['vendors']
    saved_state, saved_district = st.session_state['selection']
    st.subheader(f'Results: {saved_state} / {saved_district}')
    a,b,c = st.columns(3)
    a.metric('Vendors', len(df))
    b.metric('District installations', f"{df['Installations'].sum():,.0f}")
    c.metric('Missing counts', int(df['Installations'].isna().sum()))
    search = st.text_input('Search vendor')
    filtered = df[df['Vendor Name'].fillna('').str.contains(search, case=False, regex=False)] if search else df
    st.dataframe(filtered.sort_values('Installations', ascending=False, na_position='last'), use_container_width=True, hide_index=True)
    st.download_button('Download consolidated Excel', to_excel_bytes(df), file_name='solar_competitor_intelligence.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
else:
    st.info('No live data loaded. Complete and validate the API request generator before using the dashboard for competitor decisions.')
