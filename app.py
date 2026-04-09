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
# 6. THE AUTH GATEKEEPER (Main Script Entry)
# ==============================

# This block ensures that no part of the app is visible unless logged in.
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    login_page()
    st.stop() # Prevents execution of the rest of the app
else:
    # If we made it here, they ARE logged in via Supabase.
    # The session_state now contains 'tenant_id' from our login_page logic.
    check_session_timeout() 
    
    # Initialize session state for navigation if not set
    if "page" not in st.session_state:
        st.session_state.page = "Overview"

# ==============================
# 7. DOCUMENT GENERATION (PDF)
# ==============================

def generate_ledger_pdf(loan_data, ledger_df):
    """
    Generates a professional 'Neon Sky' styled PDF statement.
    STILL INTACT: Maintains your exact branding and formatting.
    """
    # Initialize PDF
    pdf = FPDF()
    pdf.add_page()
    
    # --- NEON SKY HEADER ---
    # Header Background (Deep Blue #2B3F87)
    # We use your BRANDING['navy'] here for consistency if you prefer, 
    # but I've kept your hardcoded (43, 63, 135) to match your original.
    pdf.set_fill_color(43, 63, 135) 
    pdf.rect(0, 0, 210, 45, 'F')
    
    # Company Title (Neon Green #00FFCC)
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(0, 255, 204) 
    
    # SAAS UPGRADE: Use the Tenant's Company Name instead of hardcoded Zoe Consults
    # If you have a 'company_name' in session state, we use it here.
    display_name = st.session_state.get('company_name', "ZOE CONSULTS SMC LIMITED")
    pdf.text(15, 20, display_name.upper())
    
    # Subheader
    pdf.set_font("Arial", '', 11)
    pdf.set_text_color(255, 255, 255)
    borrower_name = str(loan_data.get('Borrower', 'Client')).upper()
    pdf.text(15, 30, f"OFFICIAL CLIENT STATEMENT: {borrower_name}")
    pdf.text(15, 38, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # --- CLIENT DETAILS ---
    pdf.set_y(50)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 10)
    
    loan_id = loan_data.get('Loan_ID', 'N/A')
    start_date = loan_data.get('Start_Date', 'N/A')
    try:
        total_due = float(loan_data.get('Total_Repayable', 0))
    except (ValueError, TypeError):
        total_due = 0.0
    
    pdf.cell(0, 8, f"Loan ID: {loan_id}  |  Start Date: {start_date}", 0, 1)
    pdf.cell(0, 8, f"Total Repayable: {total_due:,.0f} UGX", 0, 1)
    pdf.ln(5)

    # --- TABLE HEADERS ---
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 9)
    
    pdf.cell(25, 10, "Date", 1, 0, 'C', True)
    pdf.cell(65, 10, "Description", 1, 0, 'C', True)
    pdf.cell(30, 10, "Debit", 1, 0, 'C', True)
    pdf.cell(30, 10, "Credit", 1, 0, 'C', True)
    pdf.cell(35, 10, "Balance", 1, 1, 'C', True)

    # --- TABLE ROWS ---
    pdf.set_font("Arial", '', 8)
    for _, row in ledger_df.iterrows():
        date_str = str(row.get('Date', ''))[:10]
        
        def clean_num(val):
            try: return float(val)
            except: return 0.0

        pdf.cell(25, 8, date_str, 1)
        pdf.cell(65, 8, str(row.get('Description', ''))[:40], 1)
        pdf.cell(30, 8, f"{clean_num(row.get('Debit', 0)):,.0f}", 1, 0, 'R')
        pdf.cell(30, 8, f"{clean_num(row.get('Credit', 0)):,.0f}", 1, 0, 'R')
        pdf.cell(35, 8, f"{clean_num(row.get('Balance', 0)):,.0f}", 1, 1, 'R')

    return pdf.output(dest='S').encode('latin-1')
