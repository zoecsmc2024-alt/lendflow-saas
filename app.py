import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
# import gspread  <-- We will eventually remove this
from supabase import create_client, Client
import io
import base64
import json
import bcrypt
import os
import re 
from datetime import datetime, timedelta
from twilio.rest import Client as TwilioClient
from fpdf import FPDF
from streamlit_calendar import calendar

# ==============================
# 1. SUPABASE CONNECTION (SaaS REPLACEMENT)
# ==============================
try:
    SUPABASE_URL = st.secrets["supabase_url"]
    SUPABASE_KEY = st.secrets["supabase_key"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"❌ Connection to Supabase failed: {e}")
    st.info("Check your 'supabase_url' and 'supabase_key' in Streamlit Secrets.")
    st.stop()

# ==============================
# 2. MULTI-TENANT SESSION STATE
# ==============================
# This ensures that throughout the app, we know which company is logged in
if 'tenant_id' not in st.session_state:
    st.session_state.tenant_id = None # This will be set during login

# ==============================
# 3. BRANDING & PAGE CONFIG (UNTOUCHED)
# ==============================
st.set_page_config(page_title="Zoe Admin", layout="wide", initial_sidebar_state="expanded")

BRANDING = {
    "navy": "#2B3F87",      # Primary Header / Buttons
    "baby_blue": "#F0F8FF", # Row Highlights / Hover
    "white": "#FFFFFF",     # Backgrounds
    "text_gray": "#666666"  # Captions / Timestamps
}

# ==============================
# 4. DATA LOADER (TRANSFORMED FOR SUPABASE)
# ==============================
@st.cache_data(ttl=600)
def get_cached_data(table_name):
    """
    Fetches data from Supabase filtered by the current tenant.
    This replaces the get_all_records() from Google Sheets.
    """
    try:
        # We add a .eq() filter to ensure Tenant A never sees Tenant B's data
        response = supabase.table(table_name)\
            .select("*")\
            .eq("tenant_id", st.session_state.tenant_id)\
            .execute()
        
        df = pd.DataFrame(response.data)
        return df.dropna(how='all').reset_index(drop=True)
    except Exception as e:
        st.error(f"⚠️ Error loading {table_name}: {e}")
        return pd.DataFrame()

# ==============================
# 5. GLOBAL STYLER (UNTOUCHED)
# ==============================
# [Your existing CSS logic continues here...]
