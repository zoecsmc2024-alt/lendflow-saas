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


# ==============================
# 8. SYSTEM & UI CONFIGURATION
# ==============================

def apply_ui_theme():
    """
    Applies the Zoe Consults / SaaS UI theme.
    Logic and CSS are preserved exactly.
    """
    st.markdown("""
    <style>
        /* 1. PAGE LAYOUT: FULL WIDTH */
        .block-container {
            max-width: 100% !important;
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
            padding-left: 5rem !important;
            padding-right: 5rem !important;
        }

        /* 2. MAIN APP BACKGROUND */
        .stApp {
            background-color: #F0F8FF !important; /* Baby Blue Page BG */
        }

        /* 3. THE DEEP BLUE SIDEBAR */
        [data-testid="stSidebar"] {
            background-color: #0A192F !important; /* Deep Midnight Blue */
            min-width: 260px !important;
        }

        /* Sidebar Branding Text */
        [data-testid="stSidebar"] h2, [data-testid="stSidebar"] p, [data-testid="stSidebar"] b {
            color: #F0F8FF !important;
        }

        /* 4. REMOVE BUTTON BOXES - TEXT ONLY NAV */
        section[data-testid="stSidebar"] .stButton > button {
            background-color: transparent !important;
            color: #F0F8FF !important; 
            border: none !important;     
            box-shadow: none !important; 
            width: 100% !important;
            text-align: left !important;
            padding: 8px 15px !important;
            margin-bottom: 5px !important;
            font-size: 16px !important;
            font-weight: 400 !important;
            transition: all 0.3s ease !important;
        }

        /* Hover Effect: Text Glows & Slides Right Slightly */
        section[data-testid="stSidebar"] .stButton > button:hover {
            color: #FFFFFF !important; 
            background-color: rgba(240, 248, 255, 0.1) !important; 
            padding-left: 25px !important; 
            text-decoration: none !important;
        }

        /* Active Page Indicator */
        section[data-testid="stSidebar"] .stButton > button:focus {
            color: #FFFFFF !important;
            font-weight: 700 !important;
            background-color: transparent !important;
        }

        /* 5. METRIC CARDS */
        div[data-testid="stMetric"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E0E0E0 !important;
            border-left: 8px solid #0A192F !important; 
            border-radius: 12px !important;
            padding: 20px !important;
        }

        /* 6. HIDE THE DEFAULT OVERLAY ON HOVER */
        button:focus:not(:focus-visible) {
            outline: none !important;
            box-shadow: none !important;
        }
        
    </style>
    """, unsafe_allow_html=True)

# Execute the UI theme application
apply_ui_theme()

# ==============================
# 9. UTILITY FUNCTIONS (SaaS TRANSFORMED)
# ==============================

def send_whatsapp(phone, msg):
    """
    Sends a WhatsApp message via Twilio.
    Maintains your exact logic but ensures it pulls from SaaS-wide secrets.
    """
    try:
        # Pulling from st.secrets (Ensure these are in your Streamlit Cloud secrets)
        client_tw = TwilioClient(st.secrets["TWILIO_SID"], st.secrets["TWILIO_TOKEN"])
        
        target_phone = f'whatsapp:{phone}'
        
        client_tw.messages.create(
            from_=st.secrets.get("TWILIO_WHATSAPP_FROM", 'whatsapp:+14155238886'),
            body=msg,
            to=target_phone
        )
        return True
    except Exception as e:
        st.error(f"⚠️ WhatsApp failed to send: {e}")
        return False

def save_logo_to_db(image_file):
    """
    SAAS VERSION: Saves the logo to the Supabase 'settings' table 
    associated with the specific tenant_id.
    """
    try:
        # Convert image to Base64 string
        image_file.seek(0)
        encoded = base64.b64encode(image_file.read()).decode()
        
        # Upsert the logo specifically for this tenant
        # We target the row where key='logo' AND tenant_id is the user's ID
        data = {
            "tenant_id": st.session_state.tenant_id,
            "key": "logo",
            "value": encoded
        }
        
        # In Supabase, we upsert based on a unique constraint (tenant_id + key)
        supabase.table("settings").upsert(data, on_conflict="tenant_id, key").execute()
        
        # Clear cache so the UI reflects the new logo immediately
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"❌ Logo Save Error: {e}")
        return False


# ==============================
# 10. THE SIDEBAR NAVIGATION
# ==============================

def sidebar():
    """
    Main Navigation Sidebar for the SaaS platform.
    Handles tenant branding, user info, and role-based access.
    """
    # Safety Check: Ensure session state variables exist
    role = st.session_state.get("role", "Staff")
    user = st.session_state.get("user", "Guest")
    current_page = st.session_state.get("page", "Overview")
    # SaaS addition: Get the dynamic company name
    company_name = st.session_state.get("company_name", "ZOE CONSULTS")

    # 1. THE LOGO LOADER (Now pulling from Supabase via our get_logo helper)
    logo_base64 = get_logo() 
    
    if logo_base64:
        img_src = f"data:image/png;base64,{logo_base64}"
        st.sidebar.markdown(f"""
            <div style="display: flex; justify-content: center; margin-bottom: 20px;">
                <div style="width: 85px; height: 85px; border-radius: 50%; overflow: hidden; 
                            border: 3px solid #F0F8FF; box-shadow: 0px 0px 15px rgba(240, 248, 255, 0.3);">
                    <img src="{img_src}" style="width: 100%; height: 100%; object-fit: cover;">
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    # 2. BRANDING & USER INFO
    st.sidebar.markdown(f"""
        <div style="text-align: center;">
            <h2 style="color: #FFFFFF; margin-bottom: 0;">{company_name.upper()}</h2>
            <div style="color: #F0F8FF; font-size: 12px; margin-top: 5px;">
                <span style="height: 8px; width: 8px; background-color: #00ffcc; border-radius: 50%; display: inline-block; margin-right: 5px;"></span> System Online
            </div>
            <p style='color:#F0F8FF; font-size:14px; margin-top:10px; opacity: 0.9;'>
                👤 <b>{user}</b> <span style='font-size: 12px;'>({role})</span>
            </p>
        </div>
        <hr style='border-top: 1px solid rgba(255,255,255,0.2); margin: 20px 0;'>
    """, unsafe_allow_html=True)

    # 3. NAVIGATION MENU (Untouched)
    menu = {
        "Overview": "📊", "Loans": "💵", "Borrowers": "👥", "Collateral": "🛡️",
        "Calendar": "📅", "Ledger": "📄", "Overdue Tracker": "🚨",
        "Payments": "💰", "Expenses": "📁", "PettyCash": "📉",
        "Payroll": "🧾", "Reports": "📈", "Settings": "⚙️"
    }
    
    # Restricted Pages for Admin Only
    restricted = ["Settings", "Reports", "Payroll"]

    for item, icon in menu.items():
        if role != "Admin" and item in restricted:
            continue

        # Logic check: highlight active page effect
        is_active = current_page == item
        
        if st.sidebar.button(f"{icon} {item}", key=f"nav_{item}", use_container_width=True, type="secondary"):
            st.session_state.page = item
            st.rerun()

    # 4. LOGOUT (Now also wipes tenant_id for security)
    st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
    if st.sidebar.button("🚪 Logout", key="logout_btn", use_container_width=True):
        # Clear all session data to ensure the next tenant starts fresh
        st.session_state.clear()
        st.rerun()


# ==============================
# 11. DASHBOARD LOGIC (OVERVIEW)
# ==============================

def show_overview():
    """
    Main Dashboard view. 
    Maintains exact UI/Logic but powered by Supabase Tenant Data.
    """
    st.markdown("## 📊 Financial Dashboard")
    
    # 1. LOAD TENANT-SPECIFIC DATA
    # Our Supabase helper automatically filters these by st.session_state.tenant_id
    df = get_cached_data("loans")
    pay_df = get_cached_data("payments")
    exp_df = get_cached_data("expenses") 

    if df.empty:
        st.info("No loan records found for your organization.")
        return

    # 2. TRANSLATE HEADERS (Kept for compatibility with your existing math)
    df.columns = df.columns.str.strip().str.replace(" ", "_")
    if not pay_df.empty:
        pay_df.columns = pay_df.columns.str.strip().str.replace(" ", "_")
    if not exp_df.empty:
        exp_df.columns = exp_df.columns.str.strip().str.replace(" ", "_")

    # 3. CLEAN DATA TYPES (Preserved logic)
    df["Interest"] = pd.to_numeric(df.get("Interest", 0), errors="coerce").fillna(0)
    df["Amount_Paid"] = pd.to_numeric(df.get("Amount_Paid", 0), errors="coerce").fillna(0)
    df["Principal"] = pd.to_numeric(df.get("Principal", 0), errors="coerce").fillna(0)
    df["End_Date"] = pd.to_datetime(df.get("End_Date"), errors="coerce")
    
    today = pd.Timestamp.today().normalize()
    
    # RECOVERY FILTER
    active_statuses = ["Active", "Overdue", "Rolled/Overdue"]
    active_df = df[df["Status"].isin(active_statuses)].copy()

    # 4. METRICS CALCULATION
    total_issued = active_df["Principal"].sum() if "Principal" in active_df.columns else 0
    total_interest_expected = active_df["Interest"].sum()
    total_collected = df["Amount_Paid"].sum() 
    
    overdue_mask = (active_df["End_Date"] < today) & (active_df["Status"] != "Cleared")
    overdue_count = active_df[overdue_mask].shape[0]

    # 5. METRICS ROW (Zoe Soft Blue Style - INTACT)
    m1, m2, m3, m4 = st.columns(4)
    
    m1.markdown(f"""<div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #4A90E2;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">💰 ACTIVE PRINCIPAL</p><h3 style="margin:0;color:#4A90E2;font-size:18px;">{total_issued:,.0f} <span style="font-size:10px;">UGX</span></h3></div>""", unsafe_allow_html=True)
    m2.markdown(f"""<div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #4A90E2;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">📈 EXPECTED INTEREST</p><h3 style="margin:0;color:#4A90E2;font-size:18px;">{total_interest_expected:,.0f} <span style="font-size:10px;">UGX</span></h3></div>""", unsafe_allow_html=True)
    m3.markdown(f"""<div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #2E7D32;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">✅ TOTAL COLLECTED</p><h3 style="margin:0;color:#2E7D32;font-size:18px;">{total_collected:,.0f} <span style="font-size:10px;">UGX</span></h3></div>""", unsafe_allow_html=True)
    m4.markdown(f"""<div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #FF4B4B;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">🚨 OVERDUE FILES</p><h3 style="margin:0;color:#FF4B4B;font-size:18px;">{overdue_count}</h3></div>""", unsafe_allow_html=True)

    # 6. RECENT ACTIVITY TABLES (Branding preserved)
    st.write("---")
    t1, t2 = st.columns(2)

    with t1:
        st.markdown("<h4 style='color: #4A90E2;'>📝 Recent Portfolio Activity</h4>", unsafe_allow_html=True)
        rows_html = ""
        if not active_df.empty:
            recent_loans = active_df.sort_values(by="End_Date", ascending=False).head(5)
            for i, (idx, r) in enumerate(recent_loans.iterrows()):
                bg = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                b_name = r.get('Borrower', 'Unknown')
                p_amt = float(r.get('Principal', 0))
                b_stat = r.get('Status', 'Active')
                e_date_raw = r.get('End_Date')
                e_date = pd.to_datetime(e_date_raw).strftime('%d %b') if pd.notna(e_date_raw) else "-"
                rows_html += f"""<tr style="background-color: {bg}; border-bottom: 1px solid #ddd;"><td style="padding:10px;">{b_name}</td><td style="padding:10px; text-align:right; font-weight:bold; color:#4A90E2;">{p_amt:,.0f}</td><td style="padding:10px; text-align:center;"><span style="font-size:10px; background:#e1f5fe; padding:2px 5px; border-radius:5px;">{b_stat}</span></td><td style="padding:10px; text-align:center; color:#666;">{e_date}</td></tr>"""
        
        st.markdown(f"""<table style="width:100%; border-collapse:collapse; font-family:sans-serif; font-size:12px; border: 1px solid #4A90E2;"><thead><tr style="background:#4A90E2; color:white;"><th style="padding:10px;">Borrower</th><th style="padding:10px; text-align:right;">Principal</th><th style="padding:10px; text-align:center;">Status</th><th style="padding:10px; text-align:center;">Due</th></tr></thead><tbody>{rows_html if rows_html else "<tr><td colspan='4' style='text-align:center;padding:10px;'>No active loans</td></tr>"}</tbody></table>""", unsafe_allow_html=True)

    with t2:
        st.markdown("<h4 style='color: #2E7D32;'>💸 Recent Cash Inflows</h4>", unsafe_allow_html=True)
        pay_rows = ""
        if not pay_df.empty:
            recent_pay = pay_df.sort_values(by="Date", ascending=False).head(5)
            for i, (idx, r) in enumerate(recent_pay.iterrows()):
                bg = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                p_borr = r.get('Borrower', 'Unknown')
                p_val = float(r.get('Amount', 0))
                p_date_raw = r.get('Date')
                p_date = pd.to_datetime(p_date_raw).strftime('%d %b') if pd.notna(p_date_raw) else "-"
                pay_rows += f"""<tr style="background-color: {bg}; border-bottom: 1px solid #ddd;"><td style="padding:10px;">{p_borr}</td><td style="padding:10px; text-align:right; font-weight:bold; color:green;">{p_val:,.0f}</td><td style="padding:10px; text-align:center; color:#666;">{p_date}</td></tr>"""
        
        st.markdown(f"""<table style="width:100%; border-collapse:collapse; font-family:sans-serif; font-size:12px; border: 1px solid #2E7D32;"><thead><tr style="background:#2E7D32; color:white;"><th style="padding:10px;">Borrower</th><th style="padding:10px; text-align:right;">Amount</th><th style="padding:10px; text-align:center;">Date</th></tr></thead><tbody>{pay_rows if pay_rows else "<tr><td colspan='3' style='text-align:center;padding:10px;'>No recent payments</td></tr>"}</tbody></table>""", unsafe_allow_html=True)

    # 7. DASHBOARD VISUALS (Plotly)
    st.markdown("---")
    st.markdown("<h4 style='color: #4A90E2;'>📈 Portfolio Analytics</h4>", unsafe_allow_html=True)
    c_pie, c_bar = st.columns(2)

    with c_pie:
        status_counts = df["Status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Count"]
        fig_pie = px.pie(status_counts, names="Status", values="Count", hole=0.5, title="Loan Distribution", color_discrete_sequence=["#4A90E2", "#FF4B4B", "#FFA500"])
        fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="#2B3F87", margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_pie, use_container_width=True)

    with c_bar:
        if not pay_df.empty and not exp_df.empty:
            pay_df["Date"] = pd.to_datetime(pay_df["Date"], errors='coerce')
            exp_df["Date"] = pd.to_datetime(exp_df["Date"], errors='coerce')
            inc_m = pay_df.groupby(pay_df["Date"].dt.strftime('%b %Y'))["Amount"].sum().reset_index()
            exp_m = exp_df.groupby(exp_df["Date"].dt.strftime('%b %Y'))["Amount"].sum().reset_index()
            m_cash = pd.merge(inc_m, exp_m, on="Date", how="outer", suffixes=('_Inc', '_Exp')).fillna(0)
            m_cash.columns = ["Month", "Income", "Expenses"]
            fig_bar = px.bar(m_cash, x="Month", y=["Income", "Expenses"], barmode="group", title="Performance", color_discrete_map={"Income": "#2E7D32", "Expenses": "#FF4B4B"})
            fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#2B3F87")
            st.plotly_chart(fig_bar, use_container_width=True) 


# ==============================
# 12. BORROWERS MANAGEMENT PAGE
# ==============================

def show_borrowers():
    """
    Manages borrower profiles. 
    Transformed for Supabase Multi-tenancy.
    """
    st.markdown("<h2 style='color: #2B3F87;'>👥 Borrowers Management</h2>", unsafe_allow_html=True)
    
    # 1. FETCH TENANT DATA
    # Automatically filtered by tenant_id via our get_cached_data helper
    df = get_cached_data("borrowers")
    
    if df.empty:
        df = pd.DataFrame(columns=["id", "name", "phone", "address", "national_id", "status"])

    # --- TABS (Logic & Styling Preserved) ---
    tab_view, tab_add, tab_audit = st.tabs(["📑 View All", "➕ Add New", "⚙️ Audit & Manage"])

    # --- TAB 1: VIEW ALL ---
    with tab_view:
        col1, col2 = st.columns([3, 1]) 
        with col1:
            search = st.text_input("🔍 Search Name or Phone", placeholder="Type to filter...", key="bor_search").lower()
        with col2:
            status_filter = st.selectbox("Filter Status", ["All", "Active", "Inactive"], key="bor_status_filt")

        filtered_df = df.copy()
        if not filtered_df.empty:
            # Ensure columns exist and match Supabase naming (lowercase)
            filtered_df["name"] = filtered_df["name"].astype(str)
            filtered_df["phone"] = filtered_df["phone"].astype(str)
            
            mask = (filtered_df["name"].str.lower().str.contains(search, na=False) | 
                    filtered_df["phone"].str.contains(search, na=False))
            filtered_df = filtered_df[mask]
            
            if status_filter != "All":
                filtered_df = filtered_df[filtered_df["status"] == status_filter]

            if not filtered_df.empty:
                rows_html = ""
                for i, r in filtered_df.reset_index().iterrows():
                    bg_color = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                    rows_html += f"""
                    <tr style="background-color: {bg_color}; border-bottom: 1px solid #ddd;">
                        <td style="padding:12px;"><b>{r['name']}</b></td>
                        <td style="padding:12px;">{r['phone']}</td>
                        <td style="padding:12px; font-size: 11px; color:#666;">{r.get('national_id', 'N/A')}</td>
                        <td style="padding:12px; text-align:center;">
                            <span style="background:#4A90E2; color:white; padding:3px 8px; border-radius:12px; font-size:10px;">{r['status']}</span>
                        </td>
                    </tr>"""
                st.markdown(f"<div style='border:2px solid #4A90E2; border-radius:10px; overflow:hidden; margin-top:20px;'><table style='width:100%; border-collapse:collapse; font-family:sans-serif; font-size:13px;'><thead><tr style='background:#4A90E2; color:white; text-align:left;'><th style='padding:12px;'>Borrower Name</th><th style='padding:12px;'>Phone</th><th style='padding:12px;'>National ID</th><th style='padding:12px; text-align:center;'>Status</th></tr></thead><tbody>{rows_html}</tbody></table></div>", unsafe_allow_html=True)

    # --- TAB 2: ADD BORROWER ---
    with tab_add:
        with st.form("add_borrower_form", clear_on_submit=True):
            st.markdown("<h4 style='color: #4A90E2;'>📝 Register New Borrower</h4>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            name = c1.text_input("Full Name*")
            phone = c2.text_input("Phone Number*")
            nid = c1.text_input("National ID / NIN")
            addr = c2.text_input("Physical Address")
            
            if st.form_submit_button("🚀 Save Borrower Profile", use_container_width=True):
                if name and phone:
                    # In Supabase, we don't need to manually calculate new_id (it's auto-increment)
                    new_entry = pd.DataFrame([{
                        "name": name, 
                        "phone": phone, 
                        "national_id": nid, 
                        "address": addr, 
                        "status": "Active",
                        "tenant_id": st.session_state.tenant_id
                    }])
                    if save_data("borrowers", new_entry):
                        st.success(f"✅ {name} registered!"); st.rerun()

    # --- TAB 3: AUDIT & MANAGE ---
    with tab_audit:
        if not df.empty:
            target_name = st.selectbox("Select Borrower to Audit/Manage", df["name"].tolist(), key="audit_manage_select")
            b_data = df[df["name"] == target_name].iloc[0]
            
            # SHOW LOAN HISTORY
            u_loans = get_cached_data("loans")
            
            if not u_loans.empty:
                # Filter for this specific borrower within the tenant's loans
                user_loans = u_loans[u_loans["borrower"] == target_name].copy()
                if not user_loans.empty:
                    st.metric("Total Loans Found", len(user_loans))
                    st.table(user_loans[["id", "status", "principal", "end_date"]])
                else:
                    st.info("ℹ️ No loans recorded for this borrower yet.")

            st.markdown("---")
            st.markdown("### ⚙️ Modify Borrower Details")
            
            with st.expander(f"📝 Edit Profile: {target_name}"):
                with st.form(f"edit_bor_{target_name}"):
                    c1, c2 = st.columns(2)
                    e_name = c1.text_input("Full Name", value=str(b_data['name']))
                    e_phone = c1.text_input("Phone Number", value=str(b_data['phone']))
                    e_nid = c1.text_input("National ID / NIN", value=str(b_data.get('national_id', '')))
                    e_email = c2.text_input("Email Address", value=str(b_data.get('email', '')))
                    e_status = c2.selectbox("Account Status", ["Active", "Inactive"], index=0 if b_data['status'] == "Active" else 1)
                    e_addr = st.text_input("Physical Address", value=str(b_data.get('address', '')))
                    
                    if st.form_submit_button("💾 Save Updated Profile", use_container_width=True):
                        # Create a single-row dataframe for the update
                        update_df = pd.DataFrame([{
                            "id": b_data['id'], # Primary key for upsert
                            "name": e_name,
                            "phone": e_phone,
                            "national_id": e_nid,
                            "email": e_email,
                            "status": e_status,
                            "address": e_addr,
                            "tenant_id": st.session_state.tenant_id
                        }])
                        
                        if save_data("borrowers", update_df):
                            st.success("✅ Profile updated!"); st.rerun()

            # --- DELETE ACTION ---
            st.markdown("### ⚠️ Danger Zone")
            if st.button(f"🗑️ Delete {target_name} Permanently", key=f"del_btn_{target_name}"):
                # Check for active loans before deleting
                has_loans = not u_loans[u_loans["borrower"] == target_name].empty if not u_loans.empty else False

                if has_loans:
                    st.error("❌ Cannot delete! Borrower has active loan records.")
                else:
                    try:
                        supabase.table("borrowers").delete().eq("id", b_data['id']).execute()
                        st.warning(f"⚠️ {target_name} removed."); st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

# ==============================
# 13. LOANS MANAGEMENT PAGE (SaaS Luxe Edition)
# ==============================

def show_loans():
    """
    Core engine for issuing and managing loan agreements.
    Preserves Midnight Blue branding and Peachy Luxe themes.
    """
    st.markdown("<h2 style='color: #0A192F;'>💵 Loans Management</h2>", unsafe_allow_html=True)
    
    # 1. LOAD DATA FROM SUPABASE
    # Filters automatically by tenant_id via our helper
    loans_df = get_cached_data("loans")
    borrowers_df = get_cached_data("borrowers")
    
    # Standardize Borrowers
    if not borrowers_df.empty:
        active_borrowers = borrowers_df[borrowers_df["status"] == "Active"]
    else:
        active_borrowers = pd.DataFrame()
    
    if loans_df.empty:
        loans_df = pd.DataFrame(columns=["id", "borrower", "principal", "interest", "total_repayable", "amount_paid", "balance", "status", "start_date", "end_date"])
    
    # 2. AUTO-CALC & DATA CLEANING (Preserved Logic)
    num_cols = ["principal", "interest", "total_repayable", "amount_paid", "balance"]
    for col in num_cols:
        if col in loans_df.columns:
            loans_df[col] = pd.to_numeric(loans_df[col], errors='coerce').fillna(0)

    # Balance and Auto-Close Engine
    loans_df["balance"] = (loans_df["total_repayable"] - loans_df["amount_paid"]).clip(lower=0)
    closed_mask = loans_df["balance"] <= 0
    loans_df.loc[closed_mask, "status"] = "Closed"
    loans_df.loc[closed_mask, "balance"] = 0

    tab_view, tab_add, tab_manage, tab_actions = st.tabs(["📑 Portfolio View", "➕ New Loan", "🛠️ Manage/Edit", "⚙️ Actions"])

    # ==============================
    # TAB: PORTFOLIO VIEW (Luxe Theme)
    # ==============================
    with tab_view:
        if not loans_df.empty:
            sel_id = st.selectbox("🔍 Select Loan to Inspect", loans_df["id"].unique(), key="inspect_sel_v5")
            
            # BRANDED METRIC CARDS (Restored Peach/Navy Blend)
            loan_history = loans_df[loans_df["id"] == sel_id]
            if not loan_history.empty:
                latest_info = loan_history.sort_values("start_date").iloc[-1]
                rec_val, out_val, stat_val = latest_info['amount_paid'], latest_info['balance'], str(latest_info['status']).upper()
                if stat_val == "CLOSED": out_val = 0
            else:
                rec_val, out_val, stat_val = 0, 0, "N/A"

            c1, c2, c3 = st.columns(3)
            card_style = "background-color:#FFF9F5; padding:20px; border-radius:15px; border-left:10px solid #0A192F; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"
            text_style = "margin:0; color:#0A192F;"

            c1.markdown(f"""<div style="{card_style}"><p style="{text_style} font-size:11px; font-weight:bold;">✅ RECEIVED</p><h3 style="{text_style} font-size:18px;">{rec_val:,.0f} <span style="font-size:10px;">UGX</span></h3></div>""", unsafe_allow_html=True)
            c2.markdown(f"""<div style="{card_style}"><p style="{text_style} font-size:11px; font-weight:bold;">🚨 OUTSTANDING</p><h3 style="{text_style} font-size:18px;">{out_val:,.0f} <span style="font-size:10px;">UGX</span></h3></div>""", unsafe_allow_html=True)
            c3.markdown(f"""<div style="{card_style}"><p style="{text_style} font-size:11px; font-weight:bold;">📑 STATUS</p><h3 style="{text_style} font-size:18px;">{stat_val}</h3></div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # RENDER THE PEACHY TABLE (Preserved Custom Styler)
            def style_loan_table(row):
                bg_color = "#FFF9F5" 
                status = str(row["status"])
                colors = {"Active": "#4A90E2", "Closed": "#2E7D32", "Overdue": "#D32F2F", "BCF": "#FFA500"}
                s_color = colors.get(status, "#666666")
                styles = [f'background-color: {bg_color}; color: #0A192F;'] * len(row)
                styles[-1] = f'background-color: {s_color}; color: white; font-weight: bold; border-radius: 5px;'
                return styles

            show_cols = ["id", "borrower", "principal", "balance", "start_date", "end_date", "status"]
            st.dataframe(
                loans_df[show_cols].style.format({"principal": "{:,.0f}", "balance": "{:,.0f}"}).apply(style_loan_table, axis=1), 
                use_container_width=True, hide_index=True
            )

    # ==============================
    # TAB: NEW LOAN (Supabase Integration)
    # ==============================
    with tab_add:
        if active_borrowers.empty:
            st.info("💡 Tip: Activate a borrower first.")
        else:
            with st.form("loan_issue_form"):
                st.markdown("<h4 style='color: #0A192F;'>📝 Create New Loan Agreement</h4>", unsafe_allow_html=True)
                col1, col2 = st.columns(2)
                selected_borrower = col1.selectbox("Select Borrower", active_borrowers["name"].unique())
                amount = col1.number_input("Principal Amount (UGX)", min_value=0, step=50000)
                date_issued = col1.date_input("Start Date", value=datetime.now())
                l_type = col2.selectbox("Loan Type", ["Business", "Personal", "Emergency", "Other"])
                interest_rate = col2.number_input("Monthly Interest Rate (%)", min_value=0.0, step=0.5)
                date_due = col2.date_input("Due Date", value=date_issued + timedelta(days=30))

                total_due = amount + ((interest_rate / 100) * amount)
                st.info(f"Preview: Total Repayable will be {total_due:,.0f} UGX")

                if st.form_submit_button("🚀 Confirm & Issue Loan", use_container_width=True):
                    new_loan = pd.DataFrame([{
                        "borrower": selected_borrower, "type": l_type,
                        "principal": float(amount), "interest": (interest_rate/100)*amount,
                        "total_repayable": float(total_due), "amount_paid": 0.0,
                        "status": "Active", "start_date": str(date_issued), "end_date": str(date_due),
                        "tenant_id": st.session_state.tenant_id
                    }])
                    if save_data("loans", new_loan):
                        st.success("✅ Loan issued!"); st.rerun()

    # ==============================
    # TAB: ACTIONS (The Rollover Engine)
    # ==============================
    with tab_actions:
        st.markdown("<h4 style='color: #0A192F;'>🔄 Loan Rollover & Settlement</h4>", unsafe_allow_html=True)
        
        if loans_df.empty:
            st.info("No active loans to roll over.")
        else:
            # Only allow rolling over loans that aren't already closed
            eligible_loans = loans_df[loans_df["status"] != "Closed"]
            
            if eligible_loans.empty:
                st.success("All loans are currently settled! ✨")
            else:
                roll_sel = st.selectbox("Select Loan to Roll Over", eligible_loans["id"].unique())
                loan_to_roll = eligible_loans[eligible_loans["id"] == roll_sel].iloc[0]
                
                st.warning(f"You are rolling over Loan #{roll_sel} for {loan_to_roll['borrower']}")
                
                # Calculation for the new "Rolled" Principal
                current_unpaid = loan_to_roll['balance']
                new_interest_rate = st.number_input("New Monthly Interest (%)", value=10.0)
                
                if st.button("🔥 Execute Rollover", use_container_width=True):
                    # 1. Update old loan to 'Rolled'
                    supabase.table("loans").update({"status": "Rolled"}).eq("id", loan_to_roll['id']).execute()
                    
                    # 2. Create New Loan Entry (The Next Cycle)
                    new_cycle = pd.DataFrame([{
                        "borrower": loan_to_roll['borrower'],
                        "type": loan_to_roll['type'],
                        "principal": float(current_unpaid), # The old balance becomes the new principal
                        "interest": float(current_unpaid * (new_interest_rate / 100)),
                        "total_repayable": float(current_unpaid * (1 + (new_interest_rate / 100))),
                        "amount_paid": 0.0,
                        "status": "Active",
                        "start_date": datetime.now().strftime("%Y-%m-%d"),
                        "end_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                        "tenant_id": st.session_state.tenant_id
                    }])
                    
                    if save_data("loans", new_cycle):
                        st.success(f"Loan successfully rolled over! New Principal: {current_unpaid:,.0f} UGX")
                        st.rerun()

    # ==============================
    # TAB: MANAGE/EDIT (Direct ID Targeting)
    # ==============================
    with tab_manage:
        if not loans_df.empty:
            target_id = st.selectbox("Select Loan ID to Edit", loans_df["id"].unique())
            loan_to_edit = loans_df[loans_df["id"] == target_id].iloc[0]

            with st.form("edit_loan_form"):
                c1, c2 = st.columns(2)
                e_borr = c1.text_input("Borrower", value=loan_to_edit['borrower'])
                e_princ = c1.number_input("Principal", value=float(loan_to_edit['principal']))
                e_stat = c2.selectbox("Status", ["Active", "Pending", "Closed", "Overdue", "BCF"], index=0)
                
                if st.form_submit_button("💾 Save Changes"):
                    update_data = pd.DataFrame([{
                        "id": target_id, "borrower": e_borr, "principal": e_princ, 
                        "status": e_stat, "tenant_id": st.session_state.tenant_id
                    }])
                    if save_data("loans", update_data):
                        st.success("✅ Loan updated!"); st.rerun()

            if st.button("🗑️ Delete Loan Permanently", use_container_width=True):
                supabase.table("loans").delete().eq("id", target_id).execute()
                st.warning("Loan Deleted."); st.rerun()



# ==============================
# 14. PAYMENTS & COLLECTIONS PAGE (SaaS Upgraded)
# ==============================

def show_payments():
    """
    Manages cash inflows. Includes payment posting, 
    automatic loan status updating, and history logs.
    """
    st.markdown("<h2 style='color: #2B3F87;'>💵 Payments Management</h2>", unsafe_allow_html=True)
    
    # 1. FETCH TENANT DATA
    loans_df = get_cached_data("loans")
    payments_df = get_cached_data("payments")

    if loans_df.empty:
        st.info("ℹ️ No loans found in the system.")
        return

    tab_new, tab_history, tab_manage = st.tabs(["➕ Record Payment", "📜 History & Trends", "⚙️ Edit/Delete"])

    # ==============================
    # TAB 1: RECORD NEW PAYMENT
    # ==============================
    with tab_new:
        # Standardize for logic (Supabase columns are lowercase)
        active_loans = loans_df[loans_df["status"].str.lower() != "closed"].copy()
        
        if active_loans.empty:
            st.success("🎉 All loans are currently cleared!")
        else:
            # Selection logic
            loan_options = active_loans.apply(
                lambda x: f"ID: {x['id']} - {x['borrower']}", 
                axis=1
            ).tolist()
            
            selected_option = st.selectbox("Select Loan to Credit", loan_options, key="pay_sel")
            
            # --- TARGETING THE CURRENT CYCLE ---
            try:
                raw_id = int(selected_option.split(" - ")[0].replace("ID: ", "").strip())
                # Get the specific loan record
                loan = active_loans[active_loans["id"] == raw_id].iloc[0]
            except Exception as e:
                st.error(f"❌ Error identifying Loan: {e}")
                st.stop()

            # Financial Calculations
            total_rep = float(loan.get("total_repayable", 0))
            paid_so_far = float(loan.get("amount_paid", 0))
            outstanding = total_rep - paid_so_far

            # --- STYLED CARDS (Zoe Branding Preserved) ---
            c1, c2, c3 = st.columns(3)
            status_val = str(loan.get('status', 'Active')).strip()
            status_color = "#2E7D32" if status_val == "Active" else "#D32F2F"
            
            c1.markdown(f"""<div style="background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 5px solid #2B3F87; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0; font-size:12px; color:#666; font-weight:bold;">CLIENT</p><h3 style="margin:0; color:#2B3F87; font-size:18px;">{loan['borrower']}</h3></div>""", unsafe_allow_html=True)
            c2.markdown(f"""<div style="background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 5px solid #FF4B4B; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0; font-size:12px; color:#666; font-weight:bold;">BALANCE DUE</p><h3 style="margin:0; color:#FF4B4B; font-size:18px;">{max(0, outstanding):,.0f} <span style="font-size:12px;">UGX</span></h3></div>""", unsafe_allow_html=True)
            c3.markdown(f"""<div style="background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 5px solid {status_color}; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0; font-size:12px; color:#666; font-weight:bold;">STATUS</p><h3 style="margin:0; color:{status_color}; text-transform:uppercase; font-size:18px;">{status_val}</h3></div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # --- PAYMENT FORM ---
            with st.form("payment_form", clear_on_submit=True):
                col_a, col_b, col_c = st.columns(3)
                pay_amount = col_a.number_input("Amount Received (UGX)", min_value=0, step=10000)
                pay_method = col_b.selectbox("Method", ["Mobile Money", "Cash", "Bank Transfer", "Cheque"])
                pay_date = col_c.date_input("Payment Date", value=datetime.now())
                
                if st.form_submit_button("✅ Post Payment", use_container_width=True):
                    if pay_amount > 0:
                        try:
                            # 1. Prepare Payment Entry
                            new_payment = pd.DataFrame([{
                                "loan_id": raw_id,
                                "borrower": loan["borrower"],
                                "amount": float(pay_amount),
                                "date": pay_date.strftime("%Y-%m-%d"),
                                "method": pay_method,
                                "recorded_by": st.session_state.get("user", "Staff"),
                                "tenant_id": st.session_state.tenant_id
                            }])

                            # 2. Prepare Loan Update (Update the specific ID)
                            new_total_paid = paid_so_far + float(pay_amount)
                            new_status = "Closed" if new_total_paid >= (total_rep - 10) else status_val
                            
                            loan_update = pd.DataFrame([{
                                "id": raw_id,
                                "amount_paid": new_total_paid,
                                "status": new_status,
                                "tenant_id": st.session_state.tenant_id
                            }])

                            # 3. Double Sync Save
                            if save_data("payments", new_payment) and save_data("loans", loan_update):
                                st.success("✅ Payment recorded!"); st.cache_data.clear(); st.rerun()
                                
                        except Exception as e:
                            st.error(f"🚨 Error: {str(e)}")

    # ==============================
    # TAB 2: HISTORY (Emoji Logic Preserved)
    # ==============================
    with tab_history:
        if not payments_df.empty:
            df_display = payments_df.copy()
            def get_color_emoji(amt):
                if amt >= 5000000: return "🟢 Large"
                if amt >= 1000000: return "🔵 Medium"
                return "⚪ Small"
            
            df_display["level"] = df_display["amount"].apply(get_color_emoji)
            st.dataframe(df_display.sort_values("date", ascending=False), use_container_width=True, hide_index=True)

    # ==============================
    # TAB 3: EDIT / DELETE
    # ==============================
    with tab_manage:
        if not payments_df.empty:
            p_sel = st.selectbox("Select Receipt to Edit", payments_df["id"].unique())
            p_row = payments_df[payments_df["id"] == p_sel].iloc[0]

            with st.form("edit_payment_saas"):
                new_amt = st.number_input("Adjust Amount", value=float(p_row['amount']))
                if st.form_submit_button("💾 Update Receipt"):
                    update_p = pd.DataFrame([{"id": p_sel, "amount": new_amt, "tenant_id": st.session_state.tenant_id}])
                    if save_data("payments", update_p):
                        st.success("Receipt Updated!"); st.rerun()
            
            if st.button("🗑️ Delete Receipt Permanently"):
                supabase.table("payments").delete().eq("id", p_sel).execute()
                st.warning("Receipt Deleted."); st.rerun()


# ==============================
# 15. COLLATERAL MANAGEMENT PAGE
# ==============================

def show_collateral():
    """
    Handles asset security for loans in a multi-tenant environment.
    Maintains exact UI styling and inventory logic.
    """
    st.markdown("<h2 style='color: #2B3F87;'>🛡️ Collateral Management</h2>", unsafe_allow_html=True)
    
    # 1. FETCH TENANT DATA (Filtered by Supabase)
    collateral_df = get_cached_data("collateral")
    loans_df = get_cached_data("loans") 
    
    if collateral_df.empty:
        collateral_df = pd.DataFrame(columns=[
            "id", "borrower", "loan_id", "type", 
            "description", "value", "status", "date_added", "photo_link"
        ])

    # ==============================
    # TABBED INTERFACE (Logic Intact)
    # ==============================
    tab_reg, tab_view = st.tabs(["➕ Register Asset", "📋 Inventory & Status"])

    # --- TAB 1: REGISTER COLLATERAL ---
    with tab_reg:
        if loans_df.empty:
            st.warning("⚠️ No loans found. Issue a loan before adding collateral.")
        else:
            # Filter for active loans requiring security
            active_statuses = ["Active", "Overdue", "Rolled/Overdue"]
            available_loans = loans_df[loans_df["status"].isin(active_statuses)].copy()

            if available_loans.empty:
                st.info("✅ All current loans are cleared. No assets need to be held.")
            else:
                with st.form("collateral_form", clear_on_submit=True):
                    st.markdown("<h4 style='color: #2B3F87;'>🔒 Secure New Asset</h4>", unsafe_allow_html=True)
                    c1, c2 = st.columns(2)
                    
                    # Create labels for selection
                    loan_options = available_loans.apply(lambda x: f"ID: {x['id']} - {x['borrower']}", axis=1).tolist()
                    selected_loan = c1.selectbox("Link to Active Loan", loan_options)
                    
                    # Parse Selection
                    sel_id = int(selected_loan.split(" - ")[0].replace("ID: ", ""))
                    sel_borrower = selected_loan.split(" - ")[1]

                    asset_type = c2.selectbox("Asset Type", ["Logbook (Car)", "Land Title", "Electronics", "House Deed", "Other"])
                    desc = st.text_input("Asset Description", placeholder="e.g. Toyota Prado UBA 123X Black")
                    est_value = st.number_input("Estimated Value (UGX)", min_value=0, step=100000)

                    if st.form_submit_button("💾 Save & Secure Asset", use_container_width=True):
                        if desc and est_value > 0:
                            new_asset = pd.DataFrame([{
                                "borrower": sel_borrower,
                                "loan_id": sel_id,
                                "type": asset_type,
                                "description": desc,
                                "value": float(est_value),
                                "status": "Held",
                                "date_added": datetime.now().strftime("%Y-%m-%d"),
                                "tenant_id": st.session_state.tenant_id
                            }])
                            
                            if save_data("collateral", new_asset):
                                st.success(f"✅ Asset registered for {sel_borrower}!")
                                st.rerun()
                        else:
                            st.error("⚠️ Provide both a description and value.")

    # --- TAB 2: VIEW & UPDATE ---
    with tab_view:
        if not collateral_df.empty:
            collateral_df["value"] = pd.to_numeric(collateral_df["value"], errors='coerce').fillna(0)
            
            # --- BRANDED METRICS (Zoe Style) ---
            total_val = collateral_df[collateral_df["status"] != "Released"]["value"].sum()
            in_custody = collateral_df[collateral_df["status"].isin(["In Custody", "Held"])].shape[0]
            
            m1, m2 = st.columns(2)
            m1.markdown(f"""<div style="background-color: #F0F8FF; padding: 20px; border-radius: 15px; border-left: 5px solid #2B3F87; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0; font-size:12px; color:#666; font-weight:bold;">TOTAL ASSET SECURITY</p><h2 style="margin:0; color:#2B3F87;">{total_val:,.0f} <span style="font-size:14px;">UGX</span></h2></div>""", unsafe_allow_html=True)
            m2.markdown(f"""<div style="background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 5px solid #2B3F87; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0; font-size:12px; color:#666; font-weight:bold;">ACTIVE ASSETS</p><h2 style="margin:0; color:#2B3F87;">{in_custody}</h2></div>""", unsafe_allow_html=True)

            # --- INVENTORY TABLE (Custom HTML) ---
            rows_html = ""
            for i, r in collateral_df.reset_index().iterrows():
                bg = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                rows_html += f"""
                <tr style="background-color: {bg}; border-bottom: 1px solid #ddd;">
                    <td style="padding:10px; color:#666; font-size:11px;">#{r['id']}</td>
                    <td style="padding:10px;"><b>{r['borrower']}</b></td>
                    <td style="padding:10px;">{r['type']}</td>
                    <td style="padding:10px; font-size:11px;">{r['description']}</td>
                    <td style="padding:10px; text-align:right; font-weight:bold; color:#2B3F87;">{float(r['value']):,.0f}</td>
                    <td style="padding:10px; text-align:center;"><span style="background:#2B3F87; color:white; padding:2px 8px; border-radius:10px; font-size:10px;">{r['status']}</span></td>
                    <td style="padding:10px; text-align:right; font-size:11px; color:#666;">{r['date_added']}</td>
                </tr>"""

            st.markdown(f"""<div style="border:2px solid #2B3F87; border-radius:10px; overflow:hidden;"><table style="width:100%; border-collapse:collapse; font-family:sans-serif; font-size:12px;"><thead><tr style="background:#2B3F87; color:white; text-align:left;"><th style="padding:12px;">ID</th><th style="padding:12px;">Borrower</th><th style="padding:12px;">Type</th><th style="padding:12px;">Description</th><th style="padding:12px; text-align:right;">Value</th><th style="padding:12px; text-align:center;">Status</th><th style="padding:12px; text-align:right;">Date</th></tr></thead><tbody>{rows_html}</tbody></table></div>""", unsafe_allow_html=True)

            # --- DELETE & EDIT SECTION ---
            with st.expander("⚙️ Manage Collateral Records"):
                manage_list = collateral_df.apply(lambda x: f"ID: {x['id']} | {x['borrower']} - {x['description']}", axis=1).tolist()
                selected_col = st.selectbox("Select Asset to Modify", manage_list)
                
                c_id = int(selected_col.split(" | ")[0].replace("ID: ", ""))
                c_row = collateral_df[collateral_df["id"] == c_id].iloc[0]

                ce1, ce2 = st.columns(2)
                upd_desc = ce1.text_input("Edit Description", value=str(c_row["description"]))
                upd_val = ce1.number_input("Edit Value (UGX)", value=float(c_row["value"]))
                
                status_opts = ["In Custody", "Released", "Disposed", "Held"]
                upd_stat = ce2.selectbox("Update Status", status_opts, index=status_opts.index(c_row["status"]) if c_row["status"] in status_opts else 0)
                
                if st.button("💾 Save Asset Changes", use_container_width=True):
                    update_df = pd.DataFrame([{
                        "id": c_id, "description": upd_desc, "value": upd_val, 
                        "status": upd_stat, "tenant_id": st.session_state.tenant_id
                    }])
                    if save_data("collateral", update_df):
                        st.success("✅ Asset record updated!"); st.rerun()

                if st.button("🗑️ Delete Asset Record", use_container_width=True):
                    supabase.table("collateral").delete().eq("id", c_id).execute()
                    st.warning("⚠️ Asset record deleted."); st.rerun()
        else:
            st.info("💡 No collateral registered yet.")


# ==============================
# 16. COLLECTIONS & OVERDUE TRACKER (The Master Engine)
# ==============================
def show_overdue_tracker():
    st.markdown("### 🚨 Loan Overdue & Rollover Tracker")

    # 1. --- THE SaaS REFRESH (Now targeting Supabase) ---
    if st.button("🔄 Sync with Database", use_container_width=True):
        with st.spinner("🧹 Re-syncing tenant data..."):
            st.cache_data.clear() 
            st.session_state.loans = get_cached_data("loans")
            st.rerun()

    # --- LOAD NECESSARY DATA ---
    loans = get_cached_data("loans")
    today = datetime.now()

    if loans.empty:
        st.info("💡 No active loan records found. The system is currently clear!")
        return

    # 2. --- PREP OVERDUE DATA (Logic Intact) ---
    loans_work = loans.copy()
    # Normalize headers for math
    loans_work.columns = loans_work.columns.str.strip().str.replace(" ", "_")
    loans_work['end_date'] = pd.to_datetime(loans_work['end_date'], errors='coerce')
    
    overdue_df = loans_work[
        (loans_work['status'].isin(["Active", "Overdue", "Rolled/Overdue"])) & 
        (loans_work['end_date'] < today)
    ].copy()

    # 3. --- ROLLOVER BUTTON (The History-Building Engine) ---
    st.markdown("---") 
    if st.button("🔄 Execute Monthly Rollover (Compound All)", use_container_width=True):
        new_rows_list = []
        count = 0
        
        try: 
            # TARGETS: Logic preserved exactly
            targets = loans_work[loans_work['status'] == "Pending"].copy()
            if targets.empty:
                targets = overdue_df.copy()

            if targets.empty:
                st.info("No loans currently require a rollover cycle.")
            else:
                for i, r in targets.iterrows():
                    # 1. Archive the old row via Supabase Update
                    supabase.table("loans").update({"status": "BCF"}).eq("id", r['id']).execute()

                    # 2. THE ULTIMATE MATH FIX (Preserved Exactly)
                    old_p = float(r.get('principal', 0))
                    old_i = float(r.get('interest', 0))
                    
                    # New Basis = 514,000 (Old P + Old I)
                    new_basis = old_p + old_i
                    # New Interest = 3% of new basis
                    new_month_interest = new_basis * 0.03
                    compounded_balance = new_basis + new_month_interest
                    
                    # Date Math
                    orig_end = pd.to_datetime(r['end_date'], errors='coerce')
                    new_start = orig_end if pd.notna(orig_end) else datetime.now()
                    new_end = new_start + pd.DateOffset(months=1)

                    # 3. Create New Cycle Row (Adding tenant_id)
                    new_row = {
                        "borrower": r['borrower'],
                        "loan_id": r.get('loan_id', r['id']), # Preserve original Loan ID link
                        "start_date": new_start.strftime('%Y-%m-%d'),
                        "end_date": new_end.strftime('%Y-%m-%d'),
                        "principal": new_basis,
                        "interest": new_month_interest,
                        "total_repayable": compounded_balance,
                        "amount_paid": 0,
                        "status": "Pending",
                        "tenant_id": st.session_state.tenant_id
                    }
                    new_rows_list.append(new_row)
                    count += 1

                if new_rows_list:
                    # Save all new cycles to Supabase
                    supabase.table("loans").insert(new_rows_list).execute()
                    st.success(f"✅ Compounding Successful! Added {count} cycles.")
                    st.cache_data.clear() 
                    st.rerun()

        except Exception as e:
            st.error(f"🚨 Rollover Error: {str(e)}")

    # 4. --- TABLE DISPLAY (Branded & Formatted Styles Preserved) ---
    def style_status_colors(s):
        if s == "BCF": return "background-color: #FFA500; color: white;" 
        if s == "Pending": return "background-color: #D32F2F; color: white;" 
        if s == "Closed": return "background-color: #2E7D32; color: white;" 
        return ""

    st.markdown("### 🏦 All Loan Records")
    
    # Sort for historical view
    display_df = loans_work.sort_values(by=['borrower', 'start_date'], ascending=[True, True])
    
    # Push Status to end for Luxe view
    cols = [c for c in display_df.columns if c != 'status'] + ['status']
    display_df = display_df[cols]

    # Currency Formatting Logic
    fmt_cols = ["principal", "interest", "total_repayable", "amount_paid", "balance"]
    actual_fmt = {k: "{:,.0f}" for k in fmt_cols if k in display_df.columns}

    styled_df = display_df.style.map(style_status_colors, subset=['status']).format(actual_fmt)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)


# ==============================
# 17. ACTIVITY CALENDAR PAGE
# ==============================
def show_calendar():
    
    st.markdown("<h2 style='color: #2B3F87;'>📅 Activity Calendar</h2>", unsafe_allow_html=True)

    # 1. FETCH TENANT DATA (Filtered by Supabase)
    loans_df = get_cached_data("loans")

    if loans_df.empty:
        st.info("📅 Calendar is clear! No active loans to track.")
        return

    # Standardize types for SaaS logic
    loans_df["end_date"] = pd.to_datetime(loans_df["end_date"], errors="coerce")
    loans_df["total_repayable"] = pd.to_numeric(loans_df["total_repayable"], errors="coerce").fillna(0)
    
    today = pd.Timestamp.today().normalize()
    
    # Filter for active loans
    active_loans = loans_df[loans_df["status"].astype(str).str.lower() != "closed"].copy()

    # --- VISUAL CALENDAR WIDGET ---
    calendar_events = []
    for _, r in active_loans.iterrows():
        if pd.notna(r['end_date']):
            # Color logic: Red for overdue, Blue for upcoming (Preserved)
            is_overdue = r['end_date'].date() < today.date()
            ev_color = "#FF4B4B" if is_overdue else "#4A90E2"
            
            calendar_events.append({
                "title": f"UGX {float(r['total_repayable']):,.0f} - {r['borrower']}",
                "start": r['end_date'].strftime("%Y-%m-%d"),
                "end": r['end_date'].strftime("%Y-%m-%d"),
                "color": ev_color,
                "allDay": True,
            })

    calendar_options = {
        "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"},
        "initialView": "dayGridMonth",
        "selectable": True,
    }

    # Render the interactive calendar widget
    calendar(events=calendar_events, options=calendar_options, key="collection_cal")
    
    st.markdown("---")

    # 2. DAILY WORKLOAD METRICS (Zoe Branded Cards - Indentation Fixed)
    due_today_df = active_loans[active_loans["end_date"].dt.date == today.date()]
    upcoming_df = active_loans[
        (active_loans["end_date"] > today) & 
        (active_loans["end_date"] <= today + pd.Timedelta(days=7))
    ]
    overdue_count = active_loans[active_loans["end_date"] < today].shape[0]

    m1, m2, m3 = st.columns(3)
    
    m1.markdown(f"""<div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #2B3F87;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:12px;color:#666;font-weight:bold;">DUE TODAY |</p><p style="margin:0;font-size:18px;color:#2B3F87;font-weight:bold;">{len(due_today_df)} Accounts</p></div>""", unsafe_allow_html=True)
    m2.markdown(f"""<div style="background-color:#F0F8FF;padding:20px;border-radius:15px;border-left:5px solid #2B3F87;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:12px;color:#666;font-weight:bold;">UPCOMING (7 DAYS) |</p><p style="margin:0;font-size:18px;color:#2B3F87;font-weight:bold;">{len(upcoming_df)} Accounts</p></div>""", unsafe_allow_html=True)
    m3.markdown(f"""<div style="background-color:#FFF5F5;padding:20px;border-radius:15px;border-left:5px solid #D32F2F;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:12px;color:#D32F2F;font-weight:bold;">TOTAL OVERDUE |</p><p style="margin:0;font-size:18px;color:#D32F2F;font-weight:bold;">{overdue_count} Accounts</p></div>""", unsafe_allow_html=True)

    # 3. REVENUE FORECAST (This Month)
    st.markdown("---")
    st.markdown("<h4 style='color: #2B3F87;'>📊 Revenue Forecast (This Month)</h4>", unsafe_allow_html=True)
    
    this_month_df = active_loans[active_loans["end_date"].dt.month == today.month]
    total_expected = this_month_df["total_repayable"].sum()
    
    f1, f2 = st.columns(2)
    f1.metric("Expected Collections", f"{total_expected:,.0f} UGX")
    f2.metric("Remaining Appointments", len(this_month_df))

    # 4. ACTION ITEMS (Custom HTML Tables Intact)
    st.markdown("<h4 style='color: #2B3F87;'>📌 Action Items for Today</h4>", unsafe_allow_html=True)
    if due_today_df.empty:
        st.success("✨ No deadlines for today.")
    else:
        today_rows = "".join([f"""<tr style="background:#F0F8FF;"><td style="padding:10px;"><b>#{r['id']}</b></td><td style="padding:10px;">{r['borrower']}</td><td style="padding:10px;text-align:right;">{r['total_repayable']:,.0f}</td><td style="padding:10px;text-align:center;"><span style="background:#2B3F87;color:white;padding:2px 8px;border-radius:10px;font-size:10px;">💰 COLLECT NOW</span></td></tr>""" for _, r in due_today_df.iterrows()])
        st.markdown(f"""<div style="border:2px solid #2B3F87;border-radius:10px;overflow:hidden;"><table style="width:100%;border-collapse:collapse;font-size:12px;"><tr style="background:#2B3F87;color:white;"><th style="padding:10px;">ID</th><th style="padding:10px;">Borrower</th><th style="padding:10px;text-align:right;">Amount</th><th style="padding:10px;text-align:center;">Action</th></tr>{today_rows}</table></div>""", unsafe_allow_html=True)

    # 5. OVERDUE FOLLOW-UP (Red/Orange Warning System Intact)
    st.markdown("<br><h4 style='color: #FF4B4B;'>🔴 Past Due (Immediate Attention)</h4>", unsafe_allow_html=True)
    overdue_df = active_loans[active_loans["end_date"] < today].copy()
    if not overdue_df.empty:
        overdue_df["days_late"] = (today - overdue_df["end_date"]).dt.days
        od_rows = ""
        for _, r in overdue_df.iterrows():
            late_color = "#FF4B4B" if r['days_late'] > 7 else "#FFA500"
            od_rows += f"""<tr style="background:#FFF5F5;"><td style="padding:10px;"><b>#{r['id']}</b></td><td style="padding:10px;">{r['borrower']}</td><td style="padding:10px;color:{late_color};font-weight:bold;">{r['days_late']} Days</td><td style="padding:10px;text-align:center;"><span style="background:{late_color};color:white;padding:2px 8px;border-radius:10px;font-size:10px;">{r['status']}</span></td></tr>"""
        st.markdown(f"""<div style="border:2px solid #FF4B4B;border-radius:10px;overflow:hidden;"><table style="width:100%;border-collapse:collapse;font-size:12px;"><tr style="background:#FF4B4B;color:white;"><th style="padding:10px;">ID</th><th style="padding:10px;">Borrower</th><th style="padding:10px;text-align:center;">Late By</th><th style="padding:10px;text-align:center;">Status</th></tr>{od_rows}</table></div>""", unsafe_allow_html=True)

# ==============================
# 18. EXPENSE MANAGEMENT PAGE
# ==============================

def show_expenses():
    """
    Tracks business operational costs for specific tenants.
    Includes category logging, distribution analytics, and row management.
    """
    st.markdown("<h2 style='color: #2B3F87;'>📁 Expense Management</h2>", unsafe_allow_html=True)

    # 1. FETCH TENANT DATA
    df = get_cached_data("expenses")

    # The Master Category List (Intact)
    EXPENSE_CATS = ["Rent", "Insurance Account", "Utilities", "Salaries", "Marketing", "Office Expenses"]

    if df.empty:
        df = pd.DataFrame(columns=["id", "category", "amount", "date", "description", "payment_date", "receipt_no"])

    # ==============================
    # TABBED INTERFACE
    # ==============================
    tab_add, tab_view, tab_manage = st.tabs(["➕ Record Expense", "📊 Spending Analysis", "⚙️ Manage/Delete"])

    # --- TAB 1: ADD NEW EXPENSE ---
    with tab_add:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("add_expense_form", clear_on_submit=True):
            st.markdown("<h4 style='color: #2B3F87;'>📝 Log Business Outflow</h4>", unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            
            category = col1.selectbox("Category", EXPENSE_CATS)
            amount = col2.number_input("Amount (UGX)", min_value=0, step=1000)
            desc = st.text_input("Description (e.g., Office Power Bill March)")
            
            c_date, c_receipt = st.columns(2)
            p_date = c_date.date_input("Actual Payment Date", value=datetime.now())
            receipt_no = c_receipt.text_input("Receipt / Invoice #", placeholder="e.g. RCP-101")
            
            if st.form_submit_button("🚀 Save Expense Record", use_container_width=True):
                if amount > 0 and desc:
                    new_entry = pd.DataFrame([{
                        "category": category,
                        "amount": float(amount),
                        "date": datetime.now().strftime("%Y-%m-%d"), 
                        "description": desc,
                        "payment_date": p_date.strftime("%Y-%m-%d"), 
                        "receipt_no": receipt_no,
                        "tenant_id": st.session_state.tenant_id
                    }])
                    
                    if save_data("expenses", new_entry):
                        st.success(f"✅ Expense of {amount:,.0f} recorded!"); st.rerun()
                else:
                    st.error("⚠️ Please provide both an amount and a description.")

    # --- TAB 2: ANALYSIS & LOG ---
    with tab_view:
        if not df.empty:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
            total_spent = df["amount"].sum()
            
            st.markdown(f"""<div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #FF4B4B;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:12px;color:#666;font-weight:bold;">TOTAL MONTHLY OUTFLOW</p><h2 style="margin:0;color:#FF4B4B;">{total_spent:,.0f} <span style="font-size:14px;">UGX</span></h2></div>""", unsafe_allow_html=True)
            
            # Pie Chart Analysis (Branding Preserved)
            cat_summary = df.groupby("category")["amount"].sum().reset_index()
            fig_exp = px.pie(cat_summary, names="category", values="amount", title="Spending Distribution", hole=0.4, color_discrete_sequence=["#2B3F87", "#F0F8FF", "#FF4B4B", "#ADB5BD"])
            fig_exp.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="#2B3F87")
            st.plotly_chart(fig_exp, use_container_width=True)
            
            # Detailed Expense Log (Custom HTML Table)
            rows_html = ""
            for i, r in df.sort_values("date", ascending=False).reset_index().iterrows():
                bg = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                rows_html += f"""<tr style="background-color:{bg};border-bottom:1px solid #ddd;"><td style="padding:10px;color:#666;font-size:11px;">{r['date']}</td><td style="padding:10px;"><b>{r['category']}</b></td><td style="padding:10px;font-size:11px;">{r['description']}</td><td style="padding:10px;text-align:right;font-weight:bold;color:#FF4B4B;">{float(r['amount']):,.0f}</td><td style="padding:10px;text-align:center;color:#666;font-size:10px;">{r['receipt_no']}</td></tr>"""

            st.markdown(f"""<div style="border:2px solid #2B3F87;border-radius:10px;overflow:hidden;"><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="background:#2B3F87;color:white;text-align:left;"><th style="padding:12px;">Date</th><th style="padding:12px;">Category</th><th style="padding:12px;">Description</th><th style="padding:12px;text-align:right;">Amount (UGX)</th><th style="padding:12px;text-align:center;">Receipt #</th></tr></thead><tbody>{rows_html}</tbody></table></div>""", unsafe_allow_html=True)

    # --- TAB 3: MANAGE / EDIT EXPENSES (NEW LOGIC) ---
    with tab_manage:
        st.markdown("### 🛠️ Manage Outflow Records")
        if df.empty:
            st.info("ℹ️ No expenses found to manage.")
        else:
            # Selection for Expenses
            exp_options = [f"ID: {r['id']} | {r['category']} - {float(r['amount']):,.0f} UGX" for _, r in df.iterrows()]
            selected_exp = st.selectbox("🔍 Select Expense to Edit/Delete", exp_options)

            exp_id = int(selected_exp.split("|")[0].replace("ID:", "").strip())
            exp_to_edit = df[df["id"] == exp_id].iloc[0]

            with st.form("edit_expense_form"):
                st.markdown(f"**Editing Record ID #{exp_id}**")
                c1, c2 = st.columns(2)
                up_cat = c1.selectbox("Update Category", EXPENSE_CATS, index=EXPENSE_CATS.index(exp_to_edit['category']) if exp_to_edit['category'] in EXPENSE_CATS else 0)
                up_amt = c1.number_input("Update Amount", value=float(exp_to_edit['amount']))
                up_desc = c2.text_input("Update Description", value=str(exp_to_edit['description']))
                up_date = c2.date_input("Update Date", value=pd.to_datetime(exp_to_edit['payment_date']))

                if st.form_submit_button("💾 Save Changes to Database", use_container_width=True):
                    update_entry = pd.DataFrame([{
                        "id": exp_id,
                        "category": up_cat,
                        "amount": float(up_amt),
                        "description": up_desc,
                        "payment_date": up_date.strftime("%Y-%m-%d"),
                        "tenant_id": st.session_state.tenant_id
                    }])
                    if save_data("expenses", update_entry):
                        st.success("✅ Expense updated!"); st.rerun()

            if st.button("🗑️ Delete Expense Permanently", use_container_width=True):
                supabase.table("expenses").delete().eq("id", exp_id).execute()
                st.warning(f"⚠️ Record #{exp_id} deleted."); st.rerun()
        
