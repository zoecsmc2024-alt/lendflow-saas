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
# 2. GLOBAL STYLER (UNTOUCHED LOGIC)
# ==============================
def apply_custom_styles():
    """
    Applies the Zoe Consults branding to the Streamlit UI.
    Maintains navy sidebar and specific button hover logic.
    """
    st.markdown(f"""
        <style>
            /* Sidebar Background */
            [data-testid="stSidebar"] {{
                background-color: {BRANDING['navy']};
            }}
            
            /* Sidebar Text/Icons */
            [data-testid="stSidebar"] * {{
                color: white !important;
            }}
            
            /* Active Tab Highlight */
            .st-bb {{ border-bottom-color: {BRANDING['navy']}; }}
            .st-at {{ background-color: {BRANDING['baby_blue']}; }}
            
            /* Main App Buttons */
            .stButton>button {{
                background-color: {BRANDING['navy']};
                color: white;
                border-radius: 8px;
                border: none;
                padding: 0.5rem 1rem;
                transition: all 0.3s ease;
            }}
            
            /* Button Hover Effects */
            .stButton>button:hover {{
                background-color: #1a285e;
                color: {BRANDING['baby_blue']};
                border: none;
            }}

            /* Card-like containers (Metric Boxes) */
            div[data-testid="stMetric"] {{
                background-color: white;
                border: 1px solid #ddd;
                padding: 15px;
                border-radius: 10px;
                box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
            }}
        </style>
    """, unsafe_allow_html=True)

# ==============================
# 3. DATA HELPERS (THE NEW SUPABASE ENGINE)
# ==============================

def create_pdf(html_content):
    """Generates a PDF from HTML content using pisa."""
    from xhtml2pdf import pisa 
    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html_content), dest=pdf_buffer)
    return pdf_buffer.getvalue()

@st.cache_data(ttl=3600)
def get_logo():
    """
    Fetches the tenant's specific logo from the 'settings' table.
    """
    try:
        # We query the 'settings' table specifically for this tenant
        response = supabase.table("settings")\
            .select("value")\
            .eq("tenant_id", st.session_state.tenant_id)\
            .eq("key", "logo")\
            .execute()
        
        if response.data:
            return response.data[0]['value']
    except Exception:
        pass
    return None

def save_data(table_name, dataframe):
    """
    Saves data to Supabase. 
    In SaaS mode, we 'upsert' (update or insert) based on tenant_id.
    """
    try:
        # 1. Ensure the dataframe has the tenant_id before saving
        dataframe['tenant_id'] = st.session_state.tenant_id
        
        # 2. Convert dataframe to list of dictionaries for Supabase
        records = dataframe.to_dict(orient='records')
        
        # 3. Perform the Upsert
        # Note: 'id' or a unique constraint is needed for upsert to work properly
        supabase.table(table_name).upsert(records).execute()
        
        # Clear cache so the next pull is fresh
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"❌ Error saving to {table_name}: {e}")
        return False


# ==============================
# 4. SECURITY & SESSION MANAGEMENT (SaaS Version)
# ==============================

SESSION_TIMEOUT = 15  # Minutes

def verify_password(input_password, stored_hash):
    """
    STILL INTACT: Though Supabase Auth usually handles this, 
    we keep this if you have legacy hashed data to check.
    """
    try:
        return bcrypt.checkpw(input_password.encode(), stored_hash.encode())
    except Exception:
        return False

def check_session_timeout():
    """
    Quietly monitors inactivity. 
    Maintains your exact logic but adds 'tenant_id' to the wipe list.
    """
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        return

    if "last_activity" not in st.session_state:
        st.session_state.last_activity = datetime.now()
        return

    now = datetime.now()
    elapsed = now - st.session_state.last_activity

    if elapsed > timedelta(minutes=SESSION_TIMEOUT):
        # Added 'tenant_id' and 'session_data' to ensure total isolation on logout
        keys_to_clear = ["logged_in", "user", "role", "last_activity", "page", "tenant_id"]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        st.warning("⏳ Session expired for security. Please login again.")
        st.rerun()
    
    st.session_state.last_activity = now

# ==============================
# 5. THE LOGIN INTERFACE (SUPABASE POWERED)
# ==============================

def login_page():
    """
    A clean, centered login page.
    Transformed to use Supabase Auth for multi-tenancy.
    """
    apply_custom_styles()
    
    st.markdown("<h2 style='text-align: center; color: #2B3F87;'>🔐 ZOE CONSULTS LOGIN</h2>", unsafe_allow_html=True)
    
    with st.container():
        # We use email for Supabase Auth instead of just 'Username'
        email_input = st.text_input("Email Address", placeholder="e.g., admin@client.com")
        p_input = st.text_input("Password", type="password", placeholder="Enter password")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🚀 Access System", use_container_width=True):
                try:
                    # SUPABASE AUTH SIGN IN
                    auth_response = supabase.auth.sign_in_with_password({
                        "email": email_input,
                        "password": p_input
                    })
                    
                    if auth_response.user:
                        # 1. Set basic login state
                        st.session_state.logged_in = True
                        st.session_state.user = email_input
                        st.session_state.last_activity = datetime.now()
                        
                        # 2. Link User to Tenant ID
                        # We assume your 'users' table links auth.uid to a tenant
                        user_data = supabase.table("users")\
                            .select("tenant_id, role")\
                            .eq("id", auth_response.user.id)\
                            .single().execute()
                        
                        if user_data.data:
                            st.session_state.tenant_id = user_data.data['tenant_id']
                            st.session_state.role = user_data.data['role']
                            st.success(f"Welcome back! {st.session_state.role} access granted. ✨")
                            st.rerun()
                        else:
                            st.error("Account active but no Tenant linked. Contact Zoe Admin.")
                
                except Exception as e:
                    # If auth fails, we drop to the error message
                    st.error("❌ Access Denied. Check credentials.")

# ==============================
# 6. THE AUTH GATEKEEPER
# ==============================
# This is usually the bottom of your script
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    login_page()
else:
    # check_session_timeout()  # Optional: call this here to trigger timeout logic
    # [Your sidebar and main app logic goes here]
    pass
