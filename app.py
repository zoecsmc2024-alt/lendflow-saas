import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client, Client
import io
import base64
import json
import os
import re 
from datetime import datetime, timedelta
from fpdf import FPDF
from streamlit_calendar import calendar
import bcrypt
from twilio.rest import Client as TwilioClient # Renamed to avoid conflict
import streamlit as st
import pandas as pd
import base64
from datetime import datetime
from supabase import create_client
import streamlit as st
import pandas as pd
import time
st.set_page_config(layout="wide")
# --- CONFIGURATION (Add this!) ---
SESSION_TIMEOUT = 30

# MUST BE THE FIRST ST COMMAND


def apply_master_theme():
    brand_color = st.session_state.get("theme_color", "#1E3A8A")
    
    st.markdown(f"""
        <style>
            /* 1. Sets Sidebar Background Color */
            [data-testid="stSidebar"] {{
                background-color: {brand_color} !important;
            }}

            /* 2. Styles the Radio Button Text */
            [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {{
                color: white !important;
                font-weight: 500 !important;
                font-size: 1rem !important;
                padding: 5px 0px !important;
            }}

            /* 3. Forces the 'White Circle' for unselected buttons (Pic 1 Style) */
            [data-testid="stSidebar"] .stRadio div[data-testid="stMarkdownContainer"] p {{
                color: white !important;
            }}
            
            /* 4. This targets the outer circle of the radio button */
            div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] div[data-bv-tabindex] {{
                background-color: transparent !important;
                border: 2px solid white !important;
            }}

            /* 5. This targets the selected (Active) dot color */
            div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] div[data-bv-tabindex="0"] > div {{
                background-color: #FF4B4B !important; /* The red dot in Pic 1 */
            }}

            /* 6. Fix for Logout Button contrast */
            [data-testid="stSidebar"] button {{
                background-color: white !important;
                color: {brand_color} !important;
                border-radius: 8px !important;
            }}
        </style>
    """, unsafe_allow_html=True)


def upload_image(file):
    """Uploads collateral image to Supabase Storage and returns the public URL."""
    try:
        bucket_name = 'collateral-photos'
        file_name = f"collateral_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.name}"
        
        # Upload the file
        supabase.storage.from_(bucket_name).upload(file_name, file.getvalue())
        
        # Get public URL
        res = supabase.storage.from_(bucket_name).get_public_url(file_name)
        return res
    except Exception as e:
        st.error(f"Image upload failed: {str(e)}")
        return None
# ==========================================
# 1. SUPABASE CONNECTION
# ==========================================
try:
    SUPABASE_URL = st.secrets["supabase_url"]
    SUPABASE_KEY = st.secrets["supabase_key"]
    # Ensure 'Client' and 'create_client' are imported in your actual script
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"❌ Connection to Supabase failed: {e}")
    st.stop()

# ==========================================
# 2. MULTI-TENANT SESSION STATE
# ==========================================
if 'tenant_id' not in st.session_state:
    st.session_state.tenant_id = None 
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'theme_color' not in st.session_state:
    st.session_state.theme_color = "#2B3F87"





# ==========================================
# 5. DATA LOADERS (VERIFIED)
# ==========================================
@st.cache_data(ttl=600)
def get_cached_data_refined(table_name):
    """Fetches data with tenant isolation."""
    try:
        t_id = st.session_state.get('tenant_id')
        if not t_id: 
            return pd.DataFrame()
        response = supabase.table(table_name).select("*").eq("tenant_id", t_id).execute()
        return pd.DataFrame(response.data) if response.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame()

# --- DATA LOADING SECTION ---
df = get_cached_data_refined("borrowers")
if df.empty:
    df = pd.DataFrame(columns=["id", "name", "phone", "email", "address", "national_id", "next_of_kin", "status", "tenant_id"])

loans_df = get_cached_data_refined("loans")
if loans_df.empty:
    loans_df = pd.DataFrame(columns=["id", "loan_id_label", "borrower_id", "principal", "total_repayable", "amount_paid", "status", "start_date", "tenant_id"])

# --- UPDATED CRITICAL BRIDGE ---
if not loans_df.empty:
    if not df.empty:
        # Ensure we are mapping ID strings to Name strings
        bor_map = dict(zip(df['id'].astype(str), df['name'].astype(str)))
        
        # Convert borrower_id to string to match the map keys
        # Then map and explicitly handle the series to prevent 'int' errors
        loans_df['borrower'] = loans_df['borrower_id'].astype(str).map(bor_map)
        loans_df['borrower'] = loans_df['borrower'].fillna("Unknown")
    else:
        loans_df['borrower'] = "No Borrower Data"
@st.cache_data(ttl=600)
def get_cached_data(table_name):
    """Legacy helper maintained for backward compatibility."""
    try:
        if not st.session_state.tenant_id:
            return pd.DataFrame()

        response = supabase.table(table_name)\
            .select("*")\
            .eq("tenant_id", st.session_state.tenant_id)\
            .execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            return df.dropna(how='all').reset_index(drop=True)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()
# ==========================================
# 6. STORAGE & DATA HELPERS
# ==========================================
import base64 
from datetime import datetime
import pandas as pd
from fpdf import FPDF

def get_logo():
    """Fetches the tenant logo from Supabase with a cache-busting parameter."""
    tenant_id = st.session_state.get('tenant_id')
    if not tenant_id:
        return None
    
    try:
        # Get the public URL from your 'logos' bucket
        res = supabase.storage.from_('logos').get_public_url(f"{tenant_id}/logo.png")
        
        # Add a timestamp to the URL to force an image refresh
        import time
        return f"{res}?t={int(time.time())}"
    except:
        return None

def create_pdf_report(title, content_list):
    """
    SaaS-friendly PDF generator using FPDF.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(40, 10, title)
    pdf.ln(10)
    pdf.set_font("Helvetica", '', 12)
    for line in content_list:
        pdf.cell(0, 10, str(line), ln=True)
    return pdf.output(dest='S').encode('latin-1')

@st.cache_data(ttl=600)
def get_cached_data_refined(table_name):
    """Refined data fetcher with tenant safety."""
    try:
        t_id = st.session_state.get('tenant_id')
        if not t_id:
            return pd.DataFrame() 

        response = supabase.table(table_name).select("*").eq("tenant_id", t_id).execute()
        
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Database Error on {table_name}: {e}")
        return pd.DataFrame()

def upload_image(file):
    """Uploads collateral image to Supabase Storage and returns the public URL."""
    try:
        # NOTE: Check if your settings page uses this for the LOGO. 
        # If it's a logo, it should probably go to 'company-logos'
        bucket_name = 'collateral-photos' 
        file_name = f"collateral_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.name}"
        supabase.storage.from_(bucket_name).upload(file_name, file.getvalue())
        res = supabase.storage.from_(bucket_name).get_public_url(file_name)
        return res
    except Exception as e:
        st.error(f"Image upload failed: {str(e)}")
        return None

@st.cache_data(ttl=3600)
def save_data(table_name, dataframe):
    """Saves data to Supabase with tenant isolation."""
    if dataframe.empty:
        return False
    try:
        dataframe['tenant_id'] = st.session_state.tenant_id
        records = dataframe.to_dict(orient='records')
        supabase.table(table_name).upsert(records).execute()
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"❌ Error saving to {table_name}: {e}")
        return False


# ==========================================
# PASSWORD VERIFICATION (LEGACY SUPPORT)
# ==========================================
def verify_password(input_password, stored_hash):
    """
    Kept for legacy hashed data.
    """
    try:
        # Checking if bcrypt was successfully imported earlier
        import bcrypt
        return bcrypt.checkpw(input_password.encode(), stored_hash.encode())
    except Exception:
        # If bcrypt is missing or hash is invalid, return False instead of crashing
        return False


# ==========================================
# 8. SESSION & SECURITY UTILITIES (VERIFIED)
# ==========================================

def check_session_timeout():
    """
    Monitors inactivity and wipes session data on expiration.
    """
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        return

    if "last_activity" not in st.session_state:
        st.session_state.last_activity = datetime.now()
        return

    now = datetime.now()
    elapsed = now - st.session_state.last_activity

    if elapsed > timedelta(minutes=SESSION_TIMEOUT):
        # We clear EVERYTHING to ensure total isolation
        keys_to_clear = ["logged_in", "user", "role", "last_activity", "page", "tenant_id", "view"]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        st.warning("⏳ Session expired for security. Please login again.")
        st.rerun()
    
    st.session_state.last_activity = now

# --- RATE LIMITING ---
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 10

def check_rate_limit(email):
    attempts = st.session_state.get("login_attempts", {})
    if email in attempts:
        count, last_attempt = attempts[email]
        if count >= MAX_ATTEMPTS:
            if datetime.now() - last_attempt < timedelta(minutes=LOCKOUT_MINUTES):
                return False
            # Reset after lockout period expires
            attempts[email] = (0, datetime.now())
    return True

def record_failed_attempt(email):
    attempts = st.session_state.setdefault("login_attempts", {})
    count, _ = attempts.get(email, (0, datetime.now()))
    attempts[email] = (count + 1, datetime.now())

def reset_attempts(email):
    attempts = st.session_state.get("login_attempts", {})
    if email in attempts:
        del attempts[email]

# --- AUDIT LOGGING ---
def log_event(supabase, user_id, event, status, meta=None):
    """
    Logs events to Supabase with error handling.
    """
    try:
        supabase.table("audit_logs").insert({
            "user_id": user_id,
            "event": event,
            "status": status,
            "meta": meta or {},
            "timestamp": datetime.now(timedelta(0)).isoformat() # UTC format
        }).execute()
    except Exception:
        pass # Logging should never break the main user experience

# ==========================================
# 9. CORE AUTHENTICATION LOGIC (VERIFIED)
# ==========================================

def authenticate(supabase, company_code, email, password):
    try:
        # 1. Sign in with Supabase Auth
        res = supabase.auth.sign_in_with_password({
            "email": email.strip(), # Clean email
            "password": password
        })
        
        if res.user:
            # 2. Fetch the user's tenant link
            response = supabase.table("users") \
                .select("tenant_id, tenants(company_code)") \
                .eq("id", res.user.id) \
                .execute()
            
            if not response.data:
                return {"success": False, "error": "User profile not found."}

            user_record = response.data[0]
            tenant_info = user_record.get('tenants')
            
            if not tenant_info:
                return {"success": False, "error": "User is not linked to any company."}

            # 3. CLEAN COMPARISON
            # .strip() removes accidental spaces; .upper() ignores capitalization
            db_code = str(tenant_info.get('company_code', '')).strip().upper()
            input_code = str(company_code).strip().upper()
            
            if db_code == input_code:
                return {
                    "success": True, 
                    "user": res.user, 
                    "tenant_id": user_record['tenant_id']
                }
            else:
                # Debugging tip: This tells you exactly what the DB expected vs what you gave
                return {"success": False, "error": f"Invalid Company Code. (Received: {input_code})"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

    return {"success": False, "error": "Authentication failed."}

# ==========================================
# 10. SESSION & RBAC MANAGEMENT
# ==========================================

def create_session(user_data, remember=False):
    """Updates session and forces a rerun to enter the dashboard."""
    st.session_state.update({
        "logged_in": True,
        "user_id": user_data["user_id"],
        "tenant_id": user_data["tenant_id"],
        "role": user_data["role"],
        "company": user_data["company"],
        "last_activity": datetime.now()
    })
    if remember:
        st.session_state["remember"] = True
    
    # Trigger theme application immediately on login
    if "theme_color" in st.session_state:
        apply_custom_theme(st.session_state.theme_color)
        
    # CRITICAL: Force rerun so the UI switches views
    st.rerun()

def logout():
    """Wipes session and returns to login."""
    keys_to_clear = ["logged_in", "user_id", "tenant_id", "role", "company", "remember", "view"]
    for key in keys_to_clear:
        st.session_state.pop(key, None)
    st.rerun()

def require_role(allowed_roles):
    """Access control check for pages."""
    if not st.session_state.get("logged_in"):
        st.error("Not authenticated")
        st.stop()

    user_role = st.session_state.get("role")
    if user_role not in allowed_roles and user_role != "SuperAdmin":
        st.error(f"Unauthorized. Required: {allowed_roles}")
        st.stop()

# ==========================================
# 11. UI COMPONENTS & AUTH LOGIC (REFINED)
# ==========================================

def reset_password_ui(supabase):
    st.subheader("Reset Password")
    email = st.text_input("Enter your email")

    if st.button("Send Reset Link"):
        try:
            supabase.auth.reset_password_email(email)
            st.success("Check your email for reset link")
        except Exception:
            st.error("Failed to send reset email")

def authenticate_refined(supabase, company_code, email, password):
    """Specific Zoe Consults Auth logic with Company Code verification."""
    try:
        # 1. Sign in with Supabase Auth
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if res.user:
            # 2. Verify relationship with the tenants table
            response = supabase.table("users") \
                .select("tenant_id, role, tenants(company_code, name)") \
                .eq("id", res.user.id) \
                .execute()
            
            if not response.data or len(response.data) == 0:
                return {"success": False, "error": "Profile not found in users table."}

            user_record = response.data[0]
            tenant_info = user_record.get('tenants')
            
            if tenant_info is None:
                return {"success": False, "error": "System Error: User exists but is not linked to a valid Company."}

            db_company_code = tenant_info.get('company_code', '').upper()
            
            if db_company_code == company_code.upper():
                # Returning data in the format create_session expects
                return {
                    "success": True, 
                    "user_id": res.user.id, 
                    "tenant_id": user_record['tenant_id'],
                    "role": user_record.get("role", "Admin"),
                    "company": tenant_info.get("name", "Unknown")
                }
            else:
                return {"success": False, "error": f"Invalid Company Code."}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

    return {"success": False, "error": "Authentication failed."}
# ==========================================
# 12. LOGIN & SIGNUP PAGES
# ==========================================

def login_page(supabase):
    _, col, _ = st.columns([1, 2, 1])

    with col:
        st.markdown("<h2 style='text-align:center;'>🔐 LOGIN</h2>", unsafe_allow_html=True)

        company = st.text_input("🏢 Company Code", key="login_comp_unique").strip().upper()
        email = st.text_input("📧 Email", key="login_email").strip().lower()
        password = st.text_input("🔑 Password", type="password", key="login_pass")

        if st.button("🚀 Login", use_container_width=True, key="login_btn"):
            if not all([company, email, password]):
                st.warning("Please fill all fields.")
            else:
                auth_result = authenticate(supabase, company, email, password)
                
                if auth_result.get("success"):
                    st.session_state.logged_in = True
                    st.session_state.user = auth_result.get("user")
                    st.session_state.session = auth_result.get("session")
                    st.session_state.tenant_id = auth_result.get("tenant_id")
                    st.session_state.view = "dashboard"
                    st.success("Login Successful! Redirecting...")
                    st.rerun()
                else:
                    st.error(auth_result.get("error", "Unknown login error"))
        
        st.markdown("---") 

        # Navigation Buttons
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("❓ Forgot", key="nav_reset", use_container_width=True):
                st.session_state.view = "reset"
                st.rerun()

        with btn_col2:
            if st.button("🆕 Sign Up", key="nav_signup", use_container_width=True):
                st.session_state.view = "signup"
                st.rerun()

def signup_page(supabase):
    import time
    st.markdown("<h2 style='text-align:center;'>🆕 Create Account</h2>", unsafe_allow_html=True)
    
    tenant_code = st.text_input("🏢 Company Code", key="signup_tenant").strip().upper()
    email = st.text_input("📧 Email", key="signup_email").strip().lower()
    password = st.text_input("🔑 Password", type="password", key="signup_pass")

    if st.button("🚀 Create Account", use_container_width=True):
        if not all([tenant_code, email, password]):
            st.warning("⚠️ Please fill all fields.")
        else:
            try:
                # 1. TENANT CHECK
                check = supabase.table("tenants").select("id").eq("company_code", tenant_code).execute()
                if check.data:
                    tenant_id = check.data[0]['id']
                else:
                    new_t = supabase.table("tenants").insert({
                        "company_code": tenant_code,
                        "name": tenant_code.capitalize()
                    }).execute()
                    tenant_id = new_t.data[0]['id']

                # 2. AUTH SIGNUP
                res = supabase.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {"data": {"tenant_id": str(tenant_id), "role": "Admin"}}
                })

                if res.user:
                    user_data = {
                        "id": res.user.id,
                        "tenant_id": str(tenant_id),
                        "role": "Admin",
                        "full_name": email.split('@')[0].capitalize()
                    }

                    try:
                        supabase.table("users").insert(user_data).execute()
                        st.success("✅ SUCCESS! Account created.")
                        time.sleep(1)
                        st.session_state.view = "login"
                        st.rerun()
                    except Exception as db_err:
                        if "23505" in str(db_err):
                            st.info("👋 Account exists. Redirecting...")
                            time.sleep(1)
                            st.session_state.view = "login"
                            st.rerun()
                        else:
                            st.error(f"🚨 Profile Error: {str(db_err)}")

            except Exception as e:
                st.error(f"🚨 Signup Error: {str(e)}")

    if st.button("⬅️ Back to Login", key="signup_back_final"):
        st.session_state.view = "login"
        st.rerun()

# ==========================================
# 13. DOCUMENT GENERATION (NEON SKY STYLE)
# ==========================================

def generate_ledger_pdf(loan_data, ledger_df):
    """
    Generates a professional 'Neon Sky' styled PDF statement.
    Verified: Maintains exact branding and formatting.
    """
    # Initialize PDF
    pdf = FPDF()
    pdf.add_page()
    
    # --- NEON SKY HEADER ---
    # Header Background (Deep Blue #2B3F87)
    pdf.set_fill_color(43, 63, 135) 
    pdf.rect(0, 0, 210, 45, 'F')
    
    # Company Title (Neon Green #00FFCC)
    pdf.set_font("Helvetica", 'B', 20)
    pdf.set_text_color(0, 255, 204) 
    
    # Use the tenant's company name from session state
    display_name = st.session_state.get('company', "ZOE CONSULTS SMC LIMITED")
    pdf.text(15, 20, str(display_name).upper())
    
    # Subheader
    pdf.set_font("Helvetica", '', 11)
    pdf.set_text_color(255, 255, 255)
    borrower_name = str(loan_data.get('Borrower', 'Client')).upper()
    pdf.text(15, 30, f"OFFICIAL CLIENT STATEMENT: {borrower_name}")
    pdf.text(15, 38, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # --- CLIENT DETAILS ---
    pdf.set_y(50)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", 'B', 10)
    
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
    pdf.set_font("Helvetica", 'B', 9)
    
    pdf.cell(25, 10, "Date", 1, 0, 'C', True)
    pdf.cell(65, 10, "Description", 1, 0, 'C', True)
    pdf.cell(30, 10, "Debit", 1, 0, 'C', True)
    pdf.cell(30, 10, "Credit", 1, 0, 'C', True)
    pdf.cell(35, 10, "Balance", 1, 1, 'C', True)

    # --- TABLE ROWS ---
    pdf.set_font("Helvetica", '', 8)
    for _, row in ledger_df.iterrows():
        date_str = str(row.get('Date', ''))[:10]
        
        def clean_num(val):
            if pd.isna(val): return 0.0
            try: return float(val)
            except: return 0.0

        pdf.cell(25, 8, date_str, 1)
        pdf.cell(65, 8, str(row.get('Description', ''))[:40], 1)
        pdf.cell(30, 8, f"{clean_num(row.get('Debit', 0)):,.0f}", 1, 0, 'R')
        pdf.cell(30, 8, f"{clean_num(row.get('Credit', 0)):,.0f}", 1, 0, 'R')
        pdf.cell(35, 8, f"{clean_num(row.get('Balance', 0)):,.0f}", 1, 1, 'R')

    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 14. THE ROUTER TRIGGER
# ==========================================

def run_auth_ui(supabase):
    """Controls which authentication page to show."""
    if "view" not in st.session_state:
        st.session_state.view = "login"

    if st.session_state.view == "login":
        login_page(supabase)
    elif st.session_state.view == "signup":
        signup_page(supabase)
    elif st.session_state.view == "reset":
        reset_password_ui(supabase)



# ==========================================
# 16. UTILITY FUNCTIONS (SYNCED)
# ==========================================

def save_logo_to_storage(image_file):
    """
    Saves logo to Supabase Storage and updates the 'tenants' table.
    This fixes the disconnect between saving and loading.
    """
    try:
        t_id = st.session_state.get("tenant_id")
        if not t_id:
            st.error("No tenant session found.")
            return False

        # 1. Generate filename
        file_ext = image_file.name.split('.')[-1]
        file_name = f"{t_id}_logo.{file_ext}"
        
        # 2. Upload to the correct bucket (company-logos)
        image_file.seek(0)
        supabase.storage.from_('company-logos').upload(
            path=file_name, 
            file=image_file.read(),
            file_options={"upsert": "true"} # Overwrite if exists
        )
        
        # 3. Update the 'tenants' table so get_logo() can find it
        supabase.table("tenants").update({"logo_url": file_name}).eq("id", t_id).execute()
        
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"❌ Logo Upload Error: {e}")
        return False

# --- THEME & LOGO HELPERS ---

def get_current_theme():
    tenant_id = st.session_state.get("tenant_id")
    try:
        res = supabase.table("tenants").select("brand_color, name").eq("id", tenant_id).execute()
        if res.data:
            # Sync the color to session state for the CSS to pick up
            st.session_state.theme_color = res.data[0].get('brand_color', '#2B3F87')
            return res.data[0]
    except Exception:
        pass
    return {'brand_color': '#2B3F87', 'name': 'Zoe Consults'}

def upload_image(file):
    """Uploads collateral image to Supabase Storage and returns the public URL."""
    try:
        bucket_name = 'collateral-photos'
        file_name = f"collateral_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.name}"
        
        # Upload the file
        supabase.storage.from_(bucket_name).upload(file_name, file.getvalue())
        
        # Get public URL
        res = supabase.storage.from_(bucket_name).get_public_url(file_name)
        return res
    except Exception as e:
        st.error(f"Image upload failed: {str(e)}")
        return None



def render_sidebar():
    # 1. Fetch Fresh Tenant Data
    try:
        # Fetching necessary columns from Supabase
        tenants_res = supabase.table("tenants").select("id, name, brand_color, logo_url").execute()
        tenant_map = {row['name']: row for row in tenants_res.data} if tenants_res.data else {}
    except Exception as e:
        st.error(f"Error fetching tenants: {e}")
        tenant_map = {}

    current_tenant_id = st.session_state.get('tenant_id')

    with st.sidebar:
        if tenant_map:
            options = list(tenant_map.keys())
            default_index = 0
            if current_tenant_id:
                for i, name in enumerate(options):
                    if tenant_map[name]['id'] == current_tenant_id:
                        default_index = i
                        break
            
            # selectbox for switching between business portals
            active_company_name = st.selectbox("Business Portal:", options, index=default_index, key="sidebar_portal_select")
            active_company = tenant_map[active_company_name]
            
            # CRITICAL SYNC: Update the Master Switch and Session State
            if st.session_state.get('tenant_id') != active_company['id']:
                st.session_state['tenant_id'] = active_company['id']
                st.session_state['theme_color'] = active_company['brand_color']
                st.rerun()
        else:
            st.stop()

        # --- LOGO RENDER ---
        _, col_mid, _ = st.columns([1, 2, 1])
        with col_mid:
            logo_val = active_company.get('logo_url')
            if logo_val and logo_val not in ["0", "None"]:
                import time
                # Build URL and append timestamp to avoid MediaFileStorageError
                if str(logo_val).startswith("http"):
                    final_logo_url = logo_val
                else:
                    # Replace with your actual project ID
                    proj_id = "YOUR_PROJECT_ID" 
                    final_logo_url = f"https://{proj_id}.supabase.co/storage/v1/object/public/company-logos/{logo_val}"
                
                try:
                    # Cache-busting with time.time()
                    st.image(f"{final_logo_url}?t={int(time.time())}", width=80)
                except:
                    st.markdown("<h1 style='text-align: center;'>🏢</h1>", unsafe_allow_html=True)
            else:
                st.markdown("<h1 style='text-align: center;'>🌍</h1>", unsafe_allow_html=True)

        st.divider()

        # --- NAVIGATION (FIXED FOR PIC 1 LOOK) ---
        menu = {
            "Overview": "📈", "Loans": "💵", "Borrowers": "👥", "Collateral": "🛡️", 
            "Calendar": "📅", "Ledger": "📄", "Payroll": "💳", "Expenses": "📉", 
            "Petty Cash": "🪙", "Overdue Tracker": "🚨", "Payments": "💰", "Settings": "⚙️"
        }
        
        # We use a clean radio button list to get the selection dot style
        menu_options = [f"{emoji} {name}" for name, emoji in menu.items()]
        
        current_p = st.session_state.get('current_page', "Overview")
        try:
            # Finding current index for persistence
            default_ix = list(menu.keys()).index(current_p)
        except:
            default_ix = 0

        # The radio widget provides the white/red dot indicators seen in Pic 1
        selection = st.radio(
            "Navigation", 
            menu_options, 
            index=default_ix, 
            label_visibility="collapsed",
            key="navigation_radio"
        )
        
        st.divider()

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # Clean the selection string to return only the page name (e.g., "Settings")
    final_page = selection.split(" ", 1)[1] if " " in selection else selection
    st.session_state['current_page'] = final_page
    return final_page
        
# ==============================
# 12. BORROWERS MANAGEMENT PAGE
# ==============================
import uuid # CRITICAL: Fixes the UUID NameError
import streamlit as st
import pandas as pd

def show_borrowers():
    """
    Manages borrower profiles. 
    Fixed for Supabase UUID and RLS compliance.
    Includes "Fuzzy Column Matching" to prevent 'borrower' key errors.
    """
    # Maintain visual brand color sync from session state
    brand_color = st.session_state.get("theme_color", "#2B3F87")
    st.markdown(f"<h2 style='color: {brand_color};'>👥 Borrowers Management</h2>", unsafe_allow_html=True)
    
    # 1. FETCH DATA
    df = get_cached_data("borrowers")
    
    # Ensure columns exist even if the DB is empty
    if df.empty:
        df = pd.DataFrame(columns=["id", "name", "phone", "email", "address", "national_id", "next_of_kin", "status", "tenant_id"])
    else:
        # Normalize columns to lowercase to prevent case-sensitive crashes
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # 2. DYNAMIC COLUMN DETECTION (The Fix for the 'borrower' Error)
    # This looks for the most likely name/phone/status columns
    name_col = next((c for c in df.columns if 'name' in c or 'borrower' in c), "name")
    phone_col = next((c for c in df.columns if 'phone' in c), "phone")
    status_col = next((c for c in df.columns if 'status' in c), "status")

    # --- TABS DEFINITION ---
    tab_view, tab_add, tab_audit = st.tabs(["📑 View All", "➕ Add New", "⚙️ Audit & Manage"])

    with tab_view:
        col1, col2 = st.columns([3, 1]) 
        with col1:
            search = st.text_input("🔍 Search Name or Phone", placeholder="Type to filter...", key="bor_search").lower()
        with col2:
            status_filter = st.selectbox("Filter Status", ["All", "Active", "Inactive"], key="bor_status_filt")

        filtered_df = df.copy()
        
        if not filtered_df.empty:
            # Safely convert to string for searching
            filtered_df[name_col] = filtered_df[name_col].astype(str)
            if phone_col in filtered_df.columns:
                filtered_df[phone_col] = filtered_df[phone_col].astype(str)
            
            # Perform search using the detected column names
            mask = filtered_df[name_col].str.lower().str.contains(search, na=False)
            if phone_col in filtered_df.columns:
                mask |= filtered_df[phone_col].str.contains(search, na=False)
                
            filtered_df = filtered_df[mask]
            
            if status_filter != "All" and status_col in filtered_df.columns:
                filtered_df = filtered_df[filtered_df[status_col].astype(str).str.title() == status_filter]

            if not filtered_df.empty:
                rows_html = ""
                for i, r in filtered_df.reset_index().iterrows():
                    bg_color = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                    
                    # Safely grab values using .get() to prevent 'KeyError' crashes
                    name_val = r.get(name_col, 'Unknown')
                    phone_val = r.get(phone_col, 'N/A')
                    email_val = r.get('email', 'N/A')
                    nok_val = r.get('next_of_kin', 'N/A')
                    stat_val = r.get(status_col, 'Active')
                    
                    rows_html += f"""
                    <tr style="background-color: {bg_color}; border-bottom: 1px solid #ddd;">
                        <td style="padding:12px;"><b>{name_val}</b></td>
                        <td style="padding:12px;">{phone_val}</td>
                        <td style="padding:12px;">{email_val}</td>
                        <td style="padding:12px;">{nok_val}</td>
                        <td style="padding:12px; text-align:center;">
                            <span style="background:{brand_color}; color:white; padding:3px 8px; border-radius:12px; font-size:10px;">{stat_val}</span>
                        </td>
                    </tr>"""
                
                # Render the table
                st.markdown(f"""
                <div style='border:2px solid {brand_color}33; border-radius:10px; overflow:hidden; margin-top:20px;'>
                    <table style='width:100%; border-collapse:collapse; font-family:sans-serif; font-size:13px;'>
                        <thead>
                            <tr style='background:{brand_color}; color:white; text-align:left;'>
                                <th style='padding:12px;'>Borrower Name</th>
                                <th style='padding:12px;'>Phone</th>
                                <th style='padding:12px;'>Email</th>
                                <th style='padding:12px;'>Next of Kin</th>
                                <th style='padding:12px; text-align:center;'>Status</th>
                            </tr>
                        </thead>
                        <tbody>{rows_html}</tbody>
                    </table>
                </div>""", unsafe_allow_html=True)
            else:
                st.info("No borrowers found matching your search.")
        else:
            st.info("No borrowers registered yet.")

# --- TAB 2: ADD BORROWER ---
    with tab_add:
        with st.form("add_borrower_form", clear_on_submit=True):
            st.markdown(f"<h4 style='color: {brand_color};'>📝 Register New Borrower</h4>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            
            # Row 1
            name = c1.text_input("Full Name*")
            phone = c2.text_input("Phone Number*")
            
            # Row 2
            email = c1.text_input("Email Address")
            nid = c2.text_input("National ID / NIN")
            
            # Row 3
            addr = c1.text_input("Physical Address")
            nok = c2.text_input("Next of Kin (Name & Contact)")
            
            if st.form_submit_button("🚀 Save Borrower Profile", use_container_width=True):
                if name and phone:
                    new_id = str(uuid.uuid4())
                    t_id = st.session_state.get('tenant_id', 'test-tenant-123')
                    
                    new_entry = pd.DataFrame([{
                        "id": new_id, 
                        "name": name, 
                        "phone": phone, 
                        "email": email,
                        "national_id": nid, 
                        "address": addr, 
                        "next_of_kin": nok,
                        "status": "Active",
                        "tenant_id": t_id 
                    }])
                    
                    if save_data("borrowers", new_entry):
                        st.success(f"✅ {name} registered!")
                        st.rerun()
                else:
                    st.error("⚠️ Please fill in Name and Phone Number.")

    # --- TAB 3: AUDIT & MANAGE ---
    with tab_audit:
        if not df.empty:
            # Dynamically find the name column in the borrowers dataframe
            b_name_col = next((c for c in df.columns if 'name' in c.lower()), df.columns[0])
            b_status_col = next((c for c in df.columns if 'status' in c.lower()), 'status')
            
            target_name = st.selectbox("Select Borrower to Audit/Manage", df[b_name_col].tolist(), key="audit_manage_select")
            b_data = df[df[b_name_col] == target_name].iloc[0]
            
            # SHOW LOAN HISTORY
            u_loans = get_cached_data("loans")
            
            if not u_loans.empty:
                # FIX: Standardize loans columns and find the borrower reference
                u_loans.columns = u_loans.columns.str.strip().str.lower().str.replace(" ", "_")
                
                # Look for 'borrower', 'borrower_id', or 'borrower_name' in the LOANS table
                loan_bor_ref = next((c for c in u_loans.columns if 'borrower' in c), None)
                
                if loan_bor_ref:
                    # Filter loans by matching the borrower reference to the target name
                    user_loans = u_loans[u_loans[loan_bor_ref].astype(str) == str(target_name)].copy()
                    
                    if not user_loans.empty:
                        st.metric("Total Loans Found", len(user_loans))
                        # Select only available columns to avoid display errors
                        cols_to_show = [c for c in ["id", "status", "principal", "end_date"] if c in user_loans.columns]
                        st.table(user_loans[cols_to_show])
                    else:
                        st.info("ℹ️ No loans recorded for this borrower yet.")
                else:
                    st.warning("Could not find a borrower reference column in the loans table.")

            st.markdown("---")
            st.markdown("### ⚙️ Modify Borrower Details")
            
            with st.expander(f"📝 Edit Profile: {target_name}"):
                with st.form(f"edit_bor_{target_name}"):
                    c1, c2 = st.columns(2)
                    e_name = c1.text_input("Full Name", value=str(b_data.get(b_name_col, '')))
                    e_phone = c1.text_input("Phone Number", value=str(b_data.get('phone', '')))
                    e_nid = c1.text_input("National ID / NIN", value=str(b_data.get('national_id', '')))
                    e_email = c2.text_input("Email Address", value=str(b_data.get('email', '')))
                    
                    # Safe status index check
                    current_status = str(b_data.get(b_status_col, 'Active')).title()
                    e_status = c2.selectbox("Account Status", ["Active", "Inactive"], index=0 if current_status == "Active" else 1)
                    e_addr = st.text_input("Physical Address", value=str(b_data.get('address', '')))
                    
                    if st.form_submit_button("💾 Save Updated Profile", use_container_width=True):
                        update_df = pd.DataFrame([{
                            "id": b_data.get('id'), 
                            "name": e_name,
                            "phone": e_phone,
                            "national_id": e_nid,
                            "email": e_email,
                            "status": e_status,
                            "address": e_addr,
                            "tenant_id": st.session_state.get('tenant_id')
                        }])
                        
                        if save_data("borrowers", update_df):
                            st.success("✅ Profile updated!")
                            st.rerun()
                # --- DELETE ACTION (Now properly indented) ---
                st.markdown("### ⚠️ Danger Zone")
                confirm_delete = st.checkbox(f"I am sure I want to delete {target_name}")

                if st.button(f"🗑️ Delete Permanently", disabled=not confirm_delete, type="primary"):
                    # Check for loans
                    user_loans = u_loans[u_loans["borrower"] == target_name] if not u_loans.empty else pd.DataFrame()
                    
                    if not user_loans.empty:
                        st.error(f"❌ Cannot delete! This borrower has {len(user_loans)} loan records.")
                    else:
                        try:
                            # The actual database call
                            response = supabase.table("borrowers").delete().eq("id", b_data['id']).execute()
                            
                            # Check if it actually deleted something
                            if response.data:
                                st.success(f"Successfully removed {target_name}.")
                                st.rerun()
                            else:
                                st.error("Delete failed. You might not have permission (Check RLS).")
                        except Exception as e:
                            st.error(f"Database Error: {e}")
                        else:
                            st.info("No borrowers found to manage.")
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
            # 1. THE BRIDGE: Map names if they aren't already mapped
            if not df.empty:
                bor_map = dict(zip(df['id'], df['name']))
                loans_df['borrower'] = loans_df['borrower_id'].map(bor_map).fillna("Unknown")
            else:
                loans_df['borrower'] = "No Borrower Data"

            # 2. SELECTOR: Combine Label and Name for the dropdown
            loans_df['display_label'] = loans_df['loan_id_label'].astype(str) + " - " + loans_df['borrower'].astype(str)
            
            sel_label = st.selectbox("🔍 Select Loan to Inspect", 
                                     options=loans_df['display_label'].unique(), 
                                     key="inspect_sel_v5")
            
            # 3. DATA SLICE: Get details for the selected loan
            latest_info = loans_df[loans_df["display_label"] == sel_label].iloc[-1]
            
            # 4. METRICS CALCULATION
            rec_val = float(latest_info.get('amount_paid', 0))
            total_rep = float(latest_info.get('total_repayable', 0))
            out_val = total_rep - rec_val
            stat_val = str(latest_info.get('status', 'N/A')).upper()
            
            if stat_val == "CLOSED": 
                out_val = 0

            # --- BRANDED METRIC CARDS ---
            c1, c2, c3 = st.columns(3)
            card_style = "background-color:#FFF9F5; padding:20px; border-radius:15px; border-left:10px solid #0A192F; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"
            text_style = "margin:0; color:#0A192F;"

            c1.markdown(f"""<div style="{card_style}"><p style="{text_style} font-size:11px; font-weight:bold;">✅ RECEIVED</p><h3 style="{text_style} font-size:18px;">{rec_val:,.0f} <span style="font-size:10px;">UGX</span></h3></div>""", unsafe_allow_html=True)
            c2.markdown(f"""<div style="{card_style}"><p style="{text_style} font-size:11px; font-weight:bold;">🚨 OUTSTANDING</p><h3 style="{text_style} font-size:18px;">{out_val:,.0f} <span style="font-size:10px;">UGX</span></h3></div>""", unsafe_allow_html=True)
            c3.markdown(f"""<div style="{card_style}"><p style="{text_style} font-size:11px; font-weight:bold;">📑 STATUS</p><h3 style="{text_style} font-size:18px;">{stat_val}</h3></div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # --- RENDER THE PEACHY TABLE ---
            def style_loan_table(row):
                # Status-based colors
                status = str(row["status"])
                colors = {"Active": "#4A90E2", "Closed": "#2E7D32", "Overdue": "#D32F2F", "BCF": "#FFA500"}
                s_color = colors.get(status, "#666666")
                
                # Default style for all cells
                styles = ['background-color: #FFF9F5; color: #0A192F;'] * len(row)
                # Find the 'status' column index to apply the badge style
                status_idx = row.index.get_loc("status")
                styles[status_idx] = f'background-color: {s_color}; color: white; font-weight: bold; border-radius: 5px; text-align: center;'
                return styles

            # Select specific columns to keep the table clean
            show_cols = ["loan_id_label", "borrower", "principal", "total_repayable", "start_date", "status"]
            
            # Final Table Display
            st.dataframe(
                loans_df[show_cols].style.format({
                    "principal": "{:,.0f}", 
                    "total_repayable": "{:,.0f}"
                }).apply(style_loan_table, axis=1), 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.info("No loans found. Head over to 'New Loan' to get started!")

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
                
                borrower_map = dict(zip(active_borrowers["name"], active_borrowers["id"]))
                selected_name = col1.selectbox("Select Borrower", options=list(borrower_map.keys()))
                selected_id = borrower_map[selected_name]
                
                amount = col1.number_input("Principal Amount (UGX)", min_value=0, step=50000)
                date_issued = col1.date_input("Start Date", value=datetime.now())
                l_type = col2.selectbox("Loan Type", ["Business", "Personal", "Emergency", "Other"])
                interest_rate = col2.number_input("Monthly Interest Rate (%)", min_value=0.0, step=0.5)
                date_due = col2.date_input("Due Date", value=date_issued + timedelta(days=30))

                total_due = amount + ((interest_rate / 100) * amount)
                st.info(f"Preview: Total Repayable will be {total_due:,.0f} UGX")

                if st.form_submit_button("🚀 Confirm & Issue Loan", use_container_width=True):
                    # --- ALL LOGIC BELOW IS NOW PROPERLY INDENTED ---
                    t_id = "test-tenant-123"
                    
                    import random
                    readable_label = f"LN-{random.randint(1000, 9999)}"

                    loan_data = {
                        "loan_id_label": readable_label, 
                        "borrower_id": selected_id, 
                        "principal": float(amount), 
                        "interest": float((interest_rate/100)*amount),
                        "total_repayable": float(total_due), 
                        "amount_paid": 0.0,
                        "status": "Active", 
                        "start_date": str(date_issued), 
                        "end_date": str(date_due),
                        "tenant_id": t_id
                    }
                    
                    new_loan_df = pd.DataFrame([loan_data])
                    
                    if save_data("loans", new_loan_df):
                        st.success(f"✅ Loan {readable_label} issued!")
                        st.rerun()
    # ==============================
    # TAB: ACTIONS (The Rollover Engine)
    # ==============================
    with tab_actions:
        st.markdown("<h4 style='color: #0A192F;'>🔄 Loan Rollover & Settlement</h4>", unsafe_allow_html=True)
        
        if loans_df.empty:
            st.info("No active loans to roll over.")
        else:
            eligible_loans = loans_df[loans_df["status"] != "Closed"]
            
            if eligible_loans.empty:
                st.success("All loans are currently settled! ✨")
            else:
                roll_sel = st.selectbox("Select Loan to Roll Over", eligible_loans["id"].unique())
                loan_to_roll = eligible_loans[eligible_loans["id"] == roll_sel].iloc[0]
                
                st.warning(f"You are rolling over Loan #{roll_sel}")
                
                current_unpaid = loan_to_roll['balance']
                new_interest_rate = st.number_input("New Monthly Interest (%)", value=10.0)
                
                if st.button("🔥 Execute Rollover", use_container_width=True):
                    # --- ALL LOGIC BELOW MUST BE INDENTED ---
                    # 1. Update old loan
                    supabase.table("loans").update({"status": "Rolled"}).eq("id", loan_to_roll['id']).execute()
                    
                    # 2. Create New Entry
                    t_id = st.session_state.get('tenant_id', 'default-admin')
                    
                    import random
                    new_label = f"ROLL-{random.randint(1000, 9999)}"

                    new_cycle = pd.DataFrame([{
                        "loan_id_label": new_label,
                        "borrower_id": loan_to_roll['borrower_id'], 
                        "principal": float(current_unpaid), 
                        "interest": float(current_unpaid * (new_interest_rate / 100)),
                        "total_repayable": float(current_unpaid * (1 + (new_interest_rate / 100))),
                        "amount_paid": 0.0,
                        "status": "Active",
                        "start_date": datetime.now().strftime("%Y-%m-%d"),
                        "end_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                        "tenant_id": t_id 
                    }])

                    if save_data("loans", new_cycle):
                        st.success(f"✅ Loan rolled over as {new_label}!")
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
from datetime import datetime
import pandas as pd
import streamlit as st

def show_collateral():
    """
    Handles asset security for loans in a multi-tenant environment.
    Fixed for column naming mismatches and form submission errors.
    """
    brand_color = st.session_state.get("theme_color", "#2B3F87")
    st.markdown(f"<h2 style='color: {brand_color};'>🛡️ Collateral Management</h2>", unsafe_allow_html=True)
    
    # 1. FETCH DATA
    collateral_df = get_cached_data("collateral")
    loans_df = get_cached_data("loans") 
    
    # 2. STANDARDIZE COLUMNS (Prevents 'borrower' key errors)
    for d in [collateral_df, loans_df]:
        if not d.empty:
            d.columns = d.columns.str.strip().str.lower().str.replace(" ", "_")

    if collateral_df.empty:
        collateral_df = pd.DataFrame(columns=[
            "id", "borrower", "loan_id", "type", 
            "description", "value", "status", "date_added"
        ])

    # Dynamic Column Detection for Loans Table
    loan_id_col = next((c for c in loans_df.columns if 'id' in c), "id")
    loan_bor_col = next((c for c in loans_df.columns if 'borrower' in c), "borrower")
    loan_stat_col = next((c for c in loans_df.columns if 'status' in c), "status")

    tab_reg, tab_view = st.tabs(["➕ Register Asset", "📋 Inventory & Status"])

    # --- TAB 1: REGISTER ASSET (Short ID Logic) ---
# FIX: Pre-define columns outside the tab block to prevent NameErrors
l_id_col, l_bor_col, l_stat_col = "id", "borrower", "status"

with tab_reg:
    if loans_df.empty:
        st.warning("⚠️ No loans found. Issue a loan before adding collateral.")
    else:
        # Standardize column detection immediately
        loans_df.columns = loans_df.columns.str.strip().str.lower()
        l_id_col = next((c for c in loans_df.columns if 'id' in c), "id")
        l_bor_col = next((c for c in loans_df.columns if 'borrower' in c or 'name' in c), "borrower")
        l_stat_col = next((c for c in loans_df.columns if 'status' in c), "status")

        # Filter for active loans
        active_statuses = ["Active", "Overdue", "Rolled/Overdue"]
        available_loans = loans_df[loans_df[l_stat_col].astype(str).str.title().isin(active_statuses)].copy()

        if available_loans.empty:
            st.info("✅ All current loans are cleared. No assets need to be held.")
        else:
            with st.form("collateral_form", clear_on_submit=True):
                st.markdown(f"<h4 style='color: {brand_color};'>🔒 Secure New Asset</h4>", unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                
                # --- FINAL ID TRUNCATION FIX ---
                # This explicitly slices the ID to 8 characters to clean the UI
                loan_map = {
                    f"{str(row[l_id_col])[:8]} | {str(row[l_bor_col]).upper()}": row[l_id_col] 
                    for _, row in available_loans.iterrows()
                }
                
                selected_label = c1.selectbox("Link to Active Loan", options=list(loan_map.keys()))
                asset_type = c2.selectbox("Asset Type", ["Logbook (Car)", "Land Title", "Electronics", "House Deed", "Other"])
                desc = st.text_input("Asset Description", placeholder="e.g. Toyota Prado UBA 123X Black")
                est_value = st.number_input("Estimated Value (UGX)", min_value=0, step=100000)

                # Nest the submit button inside the form block
                submit = st.form_submit_button("💾 Save & Secure Asset", use_container_width=True)

            if submit:
                if desc and est_value > 0:
                    # Use the map to get the FULL UUID for the database
                    full_loan_id = loan_map[selected_label]
                    
                    # Look up the actual borrower name to avoid 'borrower' KeyErrors
                    sel_borrower = available_loans[available_loans[l_id_col] == full_loan_id][l_bor_col].iloc[0]
                    
                    new_asset = pd.DataFrame([{
                        "borrower": sel_borrower,
                        "loan_id": full_loan_id,
                        "type": asset_type,
                        "description": desc,
                        "value": float(est_value),
                        "status": "Held",
                        "date_added": datetime.now().strftime("%Y-%m-%d"),
                        "tenant_id": st.session_state.get('tenant_id')
                    }])
                    
                    if save_data("collateral", new_asset):
                        st.success(f"✅ Asset registered for {sel_borrower}!")
                        st.rerun()
                else:
                    st.error("⚠️ Provide both a description and value.")
    # --- TAB 2: VIEW & UPDATE ---
    with tab_view:
        if not collateral_df.empty:
            # 1. Numeric Conversion
            collateral_df["value"] = pd.to_numeric(collateral_df["value"], errors='coerce').fillna(0)
            
            # 2. Dynamic Column Detection
            c_bor_col = next((c for c in collateral_df.columns if 'borrower' in c), "borrower")
            c_stat_col = next((c for c in collateral_df.columns if 'status' in c), "status")
            c_id_col = next((c for c in collateral_df.columns if 'id' in c), "id")

            # 3. Metrics Calculation
            total_val = collateral_df[collateral_df[c_stat_col] != "Released"]["value"].sum()
            in_custody = collateral_df[collateral_df[c_stat_col].isin(["In Custody", "Held", "held"])].shape[0]
            
            m1, m2 = st.columns(2)
            m1.markdown(f"""<div style="background-color: #F0F8FF; padding: 20px; border-radius: 15px; border-left: 5px solid {brand_color}; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0; font-size:12px; color:#666; font-weight:bold;">TOTAL ASSET SECURITY</p><h2 style="margin:0; color:{brand_color};">{total_val:,.0f} <span style="font-size:14px;">UGX</span></h2></div>""", unsafe_allow_html=True)
            m2.markdown(f"""<div style="background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 5px solid {brand_color}; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0; font-size:12px; color:#666; font-weight:bold;">ACTIVE ASSETS</p><h2 style="margin:0; color:{brand_color};">{in_custody}</h2></div>""", unsafe_allow_html=True)

            # 4. Table Generation
            rows_html = ""
            for i, r in collateral_df.reset_index().iterrows():
                bg = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                rows_html += f"""
                <tr style="background-color: {bg}; border-bottom: 1px solid #ddd;">
                    <td style="padding:10px; color:#666; font-size:11px;">#{r.get(c_id_col)}</td>
                    <td style="padding:10px;"><b>{r.get(c_bor_col)}</b></td>
                    <td style="padding:10px;">{r.get('type', 'Asset')}</td>
                    <td style="padding:10px; font-size:11px;">{r.get('description', '')}</td>
                    <td style="padding:10px; text-align:right; font-weight:bold; color:{brand_color};">{float(r.get('value', 0)):,.0f}</td>
                    <td style="padding:10px; text-align:center;"><span style="background:{brand_color}; color:white; padding:2px 8px; border-radius:10px; font-size:10px;">{r.get(c_stat_col)}</span></td>
                    <td style="padding:10px; text-align:right; font-size:11px; color:#666;">{r.get('date_added')}</td>
                </tr>"""

            st.markdown(f"""<div style="border:2px solid {brand_color}; border-radius:10px; overflow:hidden;"><table style="width:100%; border-collapse:collapse; font-family:sans-serif; font-size:12px;"><thead><tr style="background:{brand_color}; color:white; text-align:left;"><th style="padding:12px;">ID</th><th style="padding:12px;">Borrower</th><th style="padding:12px;">Type</th><th style="padding:12px;">Description</th><th style="padding:12px; text-align:right;">Value</th><th style="padding:12px; text-align:center;">Status</th><th style="padding:12px; text-align:right;">Date</th></tr></thead><tbody>{rows_html}</tbody></table></div>""", unsafe_allow_html=True)

            # 5. Manage Records
            st.markdown("---")
            with st.expander("⚙️ Manage Collateral Records"):
                manage_list = collateral_df.apply(lambda x: f"ID: {x[c_id_col]} | {x[c_bor_col]} - {x.get('description', '')}", axis=1).tolist()
                selected_col = st.selectbox("Select Asset to Modify", manage_list)
                
                c_id = selected_col.split(" | ")[0].replace("ID: ", "")
                c_row = collateral_df[collateral_df[c_id_col].astype(str) == str(c_id)].iloc[0]

                ce1, ce2 = st.columns(2)
                upd_desc = ce1.text_input("Edit Description", value=str(c_row.get("description", "")))
                upd_val = ce1.number_input("Edit Value (UGX)", value=float(c_row.get("value", 0)))
                
                status_opts = ["In Custody", "Released", "Disposed", "Held"]
                current_stat = str(c_row.get(c_stat_col, "Held")).title()
                upd_stat = ce2.selectbox("Update Status", status_opts, index=status_opts.index(current_stat) if current_stat in status_opts else 0)
                
                if st.button("💾 Save Asset Changes", use_container_width=True):
                    update_df = pd.DataFrame([{
                        "id": c_id, 
                        "description": upd_desc, 
                        "value": upd_val, 
                        "status": upd_stat, 
                        "tenant_id": st.session_state.get('tenant_id')
                    }])
                    if save_data("collateral", update_df):
                        st.success("✅ Asset record updated!")
                        st.rerun()

                if st.button("🗑️ Delete Asset Record", use_container_width=True):
                    supabase.table("collateral").delete().eq("id", c_id).execute()
                    st.warning("⚠️ Asset record deleted.")
                    st.rerun()
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


# ==============================
# 19. PETTY CASH MANAGEMENT PAGE
# ==============================

def show_petty_cash():
    """
    Manages daily office cash transactions. Tracks inflows/outflows
    for specific tenants with real-time balance alerts.
    """
    st.markdown("<h2 style='color: #2B3F87;'>💵 Petty Cash Management</h2>", unsafe_allow_html=True)

    # 1. FETCH TENANT DATA
    df = get_cached_data("petty_cash")

    if df.empty:
        df = pd.DataFrame(columns=["id", "type", "amount", "date", "description"])
    else:
        # Standardize for logic
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

    # 2. SMART BALANCE METRICS (Logic Intact)
    inflow = df[df["type"] == "In"]["amount"].sum()
    outflow = df[df["type"] == "Out"]["amount"].sum()
    balance = inflow - outflow

    # --- STYLED NEON CARDS (Branding Preserved) ---
    c1, c2, c3 = st.columns(3)
    
    # Inflow Card
    c1.markdown(f"""
        <div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #10B981;box-shadow:2px 2px 10px rgba(0,0,0,0.05);">
            <p style="margin:0;font-size:12px;color:#666;font-weight:bold;">TOTAL CASH IN</p>
            <h3 style="margin:0;color:#10B981;">{inflow:,.0f} <span style="font-size:14px;">UGX</span></h3>
        </div>
    """, unsafe_allow_html=True)

    # Outflow Card
    c2.markdown(f"""
        <div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #FF4B4B;box-shadow:2px 2px 10px rgba(0,0,0,0.05);">
            <p style="margin:0;font-size:12px;color:#666;font-weight:bold;">TOTAL CASH OUT</p>
            <h3 style="margin:0;color:#FF4B4B;">{outflow:,.0f} <span style="font-size:14px;">UGX</span></h3>
        </div>
    """, unsafe_allow_html=True)

    # Balance Card (Dynamic Color Logic Preserved)
    bal_color = "#2B3F87" if balance >= 50000 else "#FF4B4B"
    c3.markdown(f"""
        <div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid {bal_color};box-shadow:2px 2px 10px rgba(0,0,0,0.05);">
            <p style="margin:0;font-size:12px;color:#666;font-weight:bold;">CURRENT BALANCE</p>
            <h3 style="margin:0;color:{bal_color};">{balance:,.0f} <span style="font-size:14px;">UGX</span></h3>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ==============================
    # TABBED INTERFACE
    # ==============================
    tab_record, tab_history = st.tabs(["➕ Record Entry", "📜 Transaction History"])

    # --- TAB 1: RECORD ENTRY ---
    with tab_record:
        with st.form("petty_cash_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            ttype = col_a.selectbox("Transaction Type", ["Out", "In"])
            t_amount = col_b.number_input("Amount (UGX)", min_value=0, step=1000)
            desc = st.text_input("Purpose / Description", placeholder="e.g., Office Water Refill")

            if st.form_submit_button("💾 Save to Cashbook"):
                if t_amount > 0 and desc:
                    new_row = pd.DataFrame([{
                        "type": ttype,
                        "amount": float(t_amount),
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "description": desc,
                        "tenant_id": st.session_state.tenant_id
                    }])
                    
                    if save_data("petty_cash", new_row):
                        st.success(f"Successfully recorded {t_amount:,.0f} UGX!")
                        st.rerun()
                else:
                    st.error("Please provide amount and description.")

    # --- TAB 2: HISTORY (Styles & Logic Intact) ---
    with tab_history:
        if not df.empty:
            def color_type(val):
                return 'color: #10B981;' if val == 'In' else 'color: #FF4B4B;'
            
            st.dataframe(
                df.sort_values("date", ascending=False)
                .style.map(color_type, subset=['type'])
                .format({"amount": "{:,.0f}"}),
                use_container_width=True, hide_index=True
            )

            # ADMIN ACTIONS: EDIT/DELETE
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("⚙️ Advanced: Edit or Delete Transaction"):
                options = [f"ID: {int(row['id'])} | {row['type']} - {row['description']}" for _, row in df.iterrows()]
                selected_task = st.selectbox("Select Entry to Modify", options)
                
                sel_id = int(selected_task.split(" | ")[0].replace("ID: ", ""))
                item = df[df["id"] == sel_id].iloc[0]

                up_type = st.selectbox("Update Type", ["In", "Out"], index=0 if item["type"] == "In" else 1)
                up_amt = st.number_input("Update Amount", value=float(item["amount"]), step=1000.0)
                up_desc = st.text_input("Update Description", value=str(item["description"]))

                c_up, c_del = st.columns(2)
                if c_up.button("💾 Save Changes", use_container_width=True):
                    update_entry = pd.DataFrame([{
                        "id": sel_id,
                        "type": up_type,
                        "amount": up_amt,
                        "description": up_desc,
                        "tenant_id": st.session_state.tenant_id
                    }])
                    if save_data("petty_cash", update_entry):
                        st.success("Updated Successfully!")
                        st.rerun()

                if c_del.button("🗑️ Delete Permanently", use_container_width=True):
                    supabase.table("petty_cash").delete().eq("id", sel_id).execute()
                    st.warning("Entry Deleted."); st.rerun()


# ==============================
# 20. PAYROLL MANAGEMENT PAGE
# ==============================

def show_payroll():
    """
    Handles employee compensation, tax compliance, and multi-tenant payroll logs.
    Preserves exact Excel-matching PAYE and NSSF logic.
    """
    if st.session_state.get("role") != "Admin":
        st.error("🔒 Restricted Access: Only Administrators can process payroll.")
        return

    st.markdown("<h2 style='color: #4A90E2;'>🧾 Payroll Management</h2>", unsafe_allow_html=True)

    # 1. FETCH TENANT DATA
    df = get_cached_data("payroll")
    
    # Required keys mapping (Supabase lowercase)
    required_keys = [
        "id", "employee", "tin", "designation", "mob_no", "account_no", "nssf_no",
        "arrears", "basic_salary", "absent_deduction", "lst", "gross_salary", 
        "paye", "nssf_5", "advance_drs", "other_deductions", "net_pay", 
        "nssf_10", "nssf_15", "date"
    ]
    
    if df.empty:
        df = pd.DataFrame(columns=required_keys)

    def run_manual_sync_calculations(basic, arrears, absent_deduct, advance, other):
        # 1. Gross Calculation
        gross = (float(basic) + float(arrears)) - float(absent_deduct)
        
        # 2. Local Service Tax (LST) Logic
        lst = 100000 / 12 if gross > 1000000 else 0
        
        # 3. NSSF Logic (5/10/15%)
        n5, n10 = gross * 0.05, gross * 0.10
        n15 = n5 + n10
        
        # 4. --- THE EXCEL MATCHING PAYE LOGIC (PRESERVED) ---
        paye = 0
        if gross > 410000:
            paye = 25000 + (0.30 * (gross - 410000))
        elif gross > 235000:
            paye = (gross - 235000) * 0.10
            
        # 5. Final Deductions & Net Pay
        total_deductions = paye + lst + n5 + float(advance) + float(other)
        net = gross - total_deductions
        
        return {
            "gross": round(gross), "lst": round(lst), "n5": round(n5), 
            "n10": round(n10), "n15": round(n15), "paye": round(paye), "net": round(net)
        }

    tab_process, tab_logs = st.tabs(["➕ Process Salary", "📜 Payroll History"])

    with tab_process:
        with st.form("new_payroll_form", clear_on_submit=True):
            st.markdown("<h4 style='color: #2B3F87;'>👤 Employee Details</h4>", unsafe_allow_html=True)
            name = st.text_input("Employee Name")
            c1, c2, c3 = st.columns(3)
            f_tin = c1.text_input("TIN")
            f_desig = c2.text_input("Designation")
            f_mob = c3.text_input("Mob No.")
            c4, c5 = st.columns(2)
            f_acc = c4.text_input("Account No.")
            f_nssf_no = c5.text_input("NSSF No.")
            
            st.write("---")
            st.markdown("<h4 style='color: #2B3F87;'>💰 Earnings & Deductions</h4>", unsafe_allow_html=True)
            c6, c7, c8 = st.columns(3)
            f_arrears = c6.number_input("ARREARS", min_value=0.0)
            f_basic = c7.number_input("SALARY (Basic)", min_value=0.0)
            f_absent = c8.number_input("Absenteeism Deduction", min_value=0.0)
            c9, c10 = st.columns(2)
            f_adv = c9.number_input("S.DRS / ADVANCE", min_value=0.0)
            f_other = c10.number_input("Other Deductions", min_value=0.0)

            if st.form_submit_button("💳 Confirm & Release Payment", use_container_width=True):
                if name and f_basic > 0:
                    calc = run_manual_sync_calculations(f_basic, f_arrears, f_absent, f_adv, f_other)
                    new_row = pd.DataFrame([{
                        "employee": name, "tin": f_tin, "designation": f_desig, "mob_no": f_mob,
                        "account_no": f_acc, "nssf_no": f_nssf_no, "arrears": f_arrears,
                        "basic_salary": f_basic, "absent_deduction": f_absent,
                        "gross_salary": calc['gross'], "lst": calc['lst'], "paye": calc['paye'],
                        "nssf_5": calc['n5'], "nssf_10": calc['n10'], "nssf_15": calc['n15'],
                        "advance_drs": f_adv, "other_deductions": f_other, "net_pay": calc['net'],
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "tenant_id": st.session_state.tenant_id
                    }])
                    
                    if save_data("payroll", new_row):
                        st.success(f"✅ Payroll for {name} saved!"); st.rerun()

    with tab_logs:
        if not df.empty:
            p_col1, p_col2 = st.columns([4, 1])
            p_col1.markdown(f"<h3 style='color: #4A90E2;'>{datetime.now().strftime('%B %Y')} Summary</h3>", unsafe_allow_html=True)
            
            def fm(x): 
                try: return f"{int(float(x)):,}" 
                except: return "0"

            # Generate HTML Table rows (Logic In-Tact)
            rows_html = ""
            for i, r in df.iterrows():
                rows_html += f"""<tr><td style='text-align:center; border:1px solid #ddd; padding:10px;'>{i+1}</td><td style='border:1px solid #ddd; padding:10px;'><b>{r['employee']}</b><br><small>{r.get('designation', '-')}</small></td><td style='text-align:right; border:1px solid #ddd; padding:10px;'>{fm(r['arrears'])}</td><td style='text-align:right; border:1px solid #ddd; padding:10px;'>{fm(r['basic_salary'])}</td><td style='text-align:right; border:1px solid #ddd; padding:10px; font-weight:bold;'>{fm(r['gross_salary'])}</td><td style='text-align:right; border:1px solid #ddd; padding:10px;'>{fm(r['paye'])}</td><td style='text-align:right; border:1px solid #ddd; padding:10px;'>{fm(r['nssf_5'])}</td><td style='text-align:right; border:1px solid #ddd; padding:10px; background:#E3F2FD; font-weight:bold;'>{fm(r['net_pay'])}</td><td style='text-align:right; border:1px solid #ddd; padding:10px; background:#FFF9C4;'>{fm(r['nssf_10'])}</td><td style='text-align:right; border:1px solid #ddd; padding:10px; background:#FFF9C4; font-weight:bold;'>{fm(r['nssf_15'])}</td></tr>"""

            # Grand Totals Logic (Preserved)
            total_net = df['net_pay'].sum()
            rows_html += f"""<tr style="background:#2B3F87; color:white; font-weight:bold;"><td colspan="7" style="text-align:center; padding:12px;">GRAND TOTALS</td><td style='text-align:right; padding:12px;'>{fm(total_net)}</td><td colspan="2"></td></tr>"""

            printable_html = f"""<html><head><style>body {{ font-family: sans-serif; padding: 20px; }} table {{ width: 100%; border-collapse: collapse; font-size: 11px; }} th {{ background: #2B3F87; color: white; padding: 10px; border: 1px solid #ddd; }}</style></head><body><div style="text-align:center; border-bottom:3px solid #2B3F87; margin-bottom:20px;"><h1 style="color:#2B3F87;">{st.session_state.get('company_name', 'ZOE CONSULTS SMC LTD').upper()}</h1><p><b>PAYROLL REPORT - {datetime.now().strftime('%B %Y')}</b></p></div><table><thead><tr><th>S/N</th><th>Employee</th><th>Arrears</th><th>Basic</th><th>Gross</th><th>P.A.Y.E</th><th>NSSF(5%)</th><th>Net Pay</th><th>NSSF(10%)</th><th>NSSF(15%)</th></tr></thead><tbody>{rows_html}</tbody></table></body></html>"""
            
            if p_col2.button("📥 Print PDF", key="print_pay_btn"):
                st.components.v1.html(printable_html + "<script>window.print();</script>", height=0)
            
            st.components.v1.html(printable_html, height=600, scrolling=True)

            # Manage/Delete (Transformed for Supabase ID)
            st.write("---")
            with st.expander("⚙️ Manage Record"):
                sel_opt = st.selectbox("Select Record", [f"{r['employee']} (ID: {r['id']})" for _, r in df.iterrows()])
                if st.button("🗑️ Delete Record"):
                    sid = int(sel_opt.split("(ID: ")[1].replace(")", ""))
                    supabase.table("payroll").delete().eq("id", sid).execute()
                    st.warning("Deleted."); st.rerun()



# ==============================
# 21. ADVANCED ANALYTICS & REPORTS
# ==============================

def show_reports():
    """
    Consolidates multi-tenant data to provide financial health metrics.
    Preserves Net Profit logic and Portfolio at Risk (PAR) assessment.
    """
    st.markdown("<h2 style='color: #4A90E2;'>📊 Advanced Analytics & Reports</h2>", unsafe_allow_html=True)
    
    # 1. FETCH ALL TENANT DATA
    loans = get_cached_data("loans")
    payments = get_cached_data("payments")
    expenses = get_cached_data("expenses")
    payroll = get_cached_data("payroll")
    petty = get_cached_data("petty_cash")

    if loans.empty:
        st.info("📈 Record more data to see your financial analytics.")
        return

    # 2. PAYROLL SAFETY & TAX TOTALS (Logic Intact)
    nssf_total, paye_total = 0, 0
    if not payroll.empty:
        n5 = pd.to_numeric(payroll.get("nssf_5", 0), errors="coerce").fillna(0).sum()
        n10 = pd.to_numeric(payroll.get("nssf_10", 0), errors="coerce").fillna(0).sum()
        nssf_total = n5 + n10
        paye_total = pd.to_numeric(payroll.get("paye", 0), errors="coerce").fillna(0).sum()

    # 3. OTHER DATA SUMS (Standardized for SaaS)
    l_amt = pd.to_numeric(loans.get("principal", 0), errors="coerce").fillna(0).sum()
    l_int = pd.to_numeric(loans.get("interest", 0), errors="coerce").fillna(0).sum()
    p_amt = pd.to_numeric(payments.get("amount", 0), errors="coerce").fillna(0).sum() if not payments.empty else 0
    exp_amt = pd.to_numeric(expenses.get("amount", 0), errors="coerce").fillna(0).sum() if not expenses.empty else 0
    
    petty_out = 0
    if not petty.empty:
        petty_out = pd.to_numeric(petty[petty["type"]=="Out"].get("amount", 0), errors="coerce").fillna(0).sum()
    
    # 💰 FINANCIAL LOGIC (PRESERVED)
    total_outflow = exp_amt + petty_out + nssf_total + paye_total
    net_profit = p_amt - total_outflow

    # 4. KPI DASHBOARD (Zoe Branding Preserved)
    st.subheader("🚀 Financial Performance")
    k1, k2, k3, k4 = st.columns(4)
    
    k1.markdown(f"""<div style="background-color:#fff;padding:15px;border-radius:10px;border-left:5px solid #4A90E2;box-shadow:2px 2px 8px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">CAPITAL ISSUED</p><h4 style="margin:0;color:#4A90E2;">{l_amt:,.0f}</h4></div>""", unsafe_allow_html=True)
    k2.markdown(f"""<div style="background-color:#fff;padding:15px;border-radius:10px;border-left:5px solid #4A90E2;box-shadow:2px 2px 8px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">INTEREST ACCRUED</p><h4 style="margin:0;color:#4A90E2;">{l_int:,.0f}</h4></div>""", unsafe_allow_html=True)
    k3.markdown(f"""<div style="background-color:#fff;padding:15px;border-radius:10px;border-left:5px solid #2E7D32;box-shadow:2px 2px 8px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">COLLECTIONS</p><h4 style="margin:0;color:#2E7D32;">{p_amt:,.0f}</h4></div>""", unsafe_allow_html=True)
    
    p_color = "#2E7D32" if net_profit >= 0 else "#FF4B4B"
    k4.markdown(f"""<div style="background-color:#fff;padding:15px;border-radius:10px;border-left:5px solid {p_color};box-shadow:2px 2px 8px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">NET PROFIT</p><h4 style="margin:0;color:{p_color};">{net_profit:,.0f}</h4></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 5. VISUAL ANALYTICS (Plotly Styles Preserved)
    st.markdown("---")
    col_left, col_right = st.columns(2)

    with col_left:
        st.write("**💰 Income vs. Expenses (Monthly)**")
        if not payments.empty:
            payments["date"] = pd.to_datetime(payments["date"], errors='coerce')
            inc_trend = payments.groupby(payments["date"].dt.strftime('%Y-%m'))["amount"].sum().reset_index()
            
            exp_trend = pd.DataFrame(columns=["date", "amount"])
            if not expenses.empty:
                expenses["date"] = pd.to_datetime(expenses["date"], errors='coerce')
                exp_trend = expenses.groupby(expenses["date"].dt.strftime('%Y-%m'))["amount"].sum().reset_index()

            merged = pd.merge(inc_trend, exp_trend, left_on="date", right_on="date", how="outer").fillna(0)
            merged.columns = ["Month", "Income", "Expenses"]
            
            fig_bar = px.bar(merged, x="Month", y=["Income", "Expenses"], barmode="group",
                             color_discrete_map={"Income": "#00ffcc", "Expenses": "#FF4B4B"})
            fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_bar, use_container_width=True)

    with col_right:
        st.write("**🛡️ Portfolio Weight (Top 5)**")
        top_borrowers = loans.groupby("borrower")["principal"].sum().sort_values(ascending=False).head(5).reset_index()
        fig_pie = px.pie(top_borrowers, names="borrower", values="principal", hole=0.5,
                         color_discrete_sequence=px.colors.sequential.GnBu_r)
        fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_pie, use_container_width=True)

    # 6. RISK INDICATOR (PAR % Logic Intact)
    st.markdown("---")
    st.subheader("🚨 Risk Assessment")
    
    overdue_mask = loans["status"].isin(["Overdue", "Rolled/Overdue"])
    overdue_val = pd.to_numeric(loans.loc[overdue_mask, "principal"], errors="coerce").fillna(0).sum()
    risk_percent = (overdue_val / l_amt * 100) if l_amt > 0 else 0
    
    r1, r2 = st.columns([2, 1])
    with r1:
        st.write(f"Your Portfolio at Risk (PAR) is **{risk_percent:.1f}%**.")
        st.progress(min(float(risk_percent) / 100, 1.0))
        st.write(f"Total Overdue: **{overdue_val:,.0f} UGX**")
    with r2:
        if risk_percent < 10: st.success("✅ Healthy Portfolio")
        elif risk_percent < 25: st.warning("⚠️ Moderate Risk")
        else: st.error("🆘 Critical Risk Level")


# ==============================
# 22. MASTER LEDGER & STATEMENTS
# ==============================

def show_ledger():
    """
    Detailed transaction audit for individual loans.
    Generates a consolidated HTML statement with automated running balances.
    """
    st.markdown("<h2 style='color: #2B3F87;'>📘 Master Ledger</h2>", unsafe_allow_html=True)
    
    # 1. LOAD DATA (Automatically filtered by Tenant)
    loans_df = get_cached_data("loans")
    payments_df = get_cached_data("payments")

    if loans_df.empty:
        st.info("💡 Your system is clear! No active loans found.")
        return

    # 2. SELECTION LOGIC
    loan_options = [f"ID: {r['id']} - {r['borrower']}" for _, r in loans_df.iterrows()]
    selected_loan = st.selectbox("Select Loan to View Full Statement", loan_options, key="ledger_main_select")
    
    # Extract ID safely
    raw_id = int(selected_loan.split(" - ")[0].replace("ID: ", ""))
    loan_info = loans_df[loans_df["id"] == raw_id].iloc[0]
    
    # 3. TREND MATH (Preserved Exactly)
    current_p = float(loan_info.get("principal", 0))
    interest_amt = float(loan_info.get("interest", 0))
    
    # Top Card Display
    display_bal = float(loan_info.get("balance", (current_p + interest_amt) - float(loan_info.get("amount_paid", 0))))

    st.markdown(f"""
        <div style="background-color: #ffffff; padding: 25px; border-radius: 15px; border-left: 5px solid #2B3F87; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); margin-bottom: 20px;">
            <p style="margin:0; font-size:14px; color:#666; font-weight:bold;">CURRENT OUTSTANDING BALANCE (INC. INTEREST)</p>
            <h1 style="margin:0; color:#2B3F87;">{display_bal:,.0f} <span style="font-size:18px;">UGX</span></h1>
        </div>
    """, unsafe_allow_html=True)

    # 4. BUILD THE LEDGER TABLE DATA (Preserved Logic)
    ledger_data = []
    status_str = str(loan_info.get('status', ''))
    
    # Opening Entries
    ledger_data.append({"Date": loan_info.get("start_date", "-"), "Description": "Initial Loan Disbursement", "Debit": current_p, "Credit": 0, "Balance": current_p})
    if interest_amt > 0:
        ledger_data.append({"Date": loan_info.get("start_date", "-"), "Description": "➕ Interest Charged", "Debit": interest_amt, "Credit": 0, "Balance": current_p + interest_amt})

    # Integrate Payments
    if not payments_df.empty:
        rel_pay = payments_df[payments_df["loan_id"] == raw_id].sort_values("date")
        curr_run_bal = current_p + interest_amt
        for _, pay in rel_pay.iterrows():
            p_amt = float(pay.get("amount", 0))
            curr_run_bal -= p_amt
            ledger_data.append({
                "Date": pay.get("date", "-"),
                "Description": f"✅ Repayment ({pay.get('method', 'Cash')})",
                "Debit": 0, "Credit": p_amt, "Balance": curr_run_bal
            })

    st.dataframe(pd.DataFrame(ledger_data).style.format({"Debit": "{:,.0f}", "Credit": "{:,.0f}", "Balance": "{:,.0f}"}), use_container_width=True, hide_index=True)

    # 5. PRINTABLE STATEMENT (SaaS Branded)
    st.markdown("---")
    if st.button("✨ Preview Consolidated Statement", use_container_width=True):
        borrowers_df = get_cached_data("borrowers")
        current_b_name = loan_info['borrower'] 
        client_loans = loans_df[loans_df["borrower"] == current_b_name]
        b_data = borrowers_df[borrowers_df["name"] == current_b_name]
        b_details = b_data.iloc[0] if not b_data.empty else {}

        navy_blue, baby_blue = "#000080", "#E1F5FE"
        
        html_statement = f"""
        <div id="printable-area" style="font-family: Arial; padding: 25px; border: 1px solid #eee; background: white; color: #333;">
            <div style="background: {navy_blue}; color: white; padding: 30px; border-radius: 8px; display: flex; justify-content: space-between;">
                <div><h1>{st.session_state.get('company_name', 'ZOE CONSULTS').upper()}</h1><p>Client Statement</p></div>
                <div style="text-align: right;"><p><b>{current_b_name}</b></p><p>{datetime.now().strftime('%d %b %Y')}</p></div>
            </div>
            <div style="padding: 15px; border: 1px solid #ddd; border-top: none;">
                <p><b>Phone:</b> {b_details.get('phone', 'N/A')} | <b>Address:</b> {b_details.get('address', 'N/A')}</p>
            </div>
        """

        grand_total = 0.0
        for _, l_row in client_loans.iterrows():
            l_id = l_row['id']
            p, i = float(l_row['principal']), float(l_row['interest'])
            l_pay = payments_df[payments_df["loan_id"] == l_id]["amount"].sum() if not payments_df.empty else 0
            l_bal = (p + i) - l_pay
            grand_total += l_bal

            html_statement += f"""
            <div style="margin-top: 20px; padding: 10px; background: {baby_blue}; font-weight: bold; color: {navy_blue};">
                LOAN ID: {l_id} | Balance: {l_bal:,.0f} UGX
            </div>
            """
        
        html_statement += f"""
            <div style="margin-top: 30px; padding: 20px; border: 2px solid {navy_blue}; text-align: right; background: #f0f4ff;">
                <h2 style="color: {navy_blue}; margin: 0;">GRAND TOTAL OUTSTANDING</h2>
                <h1 style="color: #FF4B4B; margin: 0;">{grand_total:,.0f} UGX</h1>
            </div>
        </div>"""
        
        st.components.v1.html(html_statement, height=600, scrolling=True)



import streamlit as st
import time

# ==========================================
# 23. SETTINGS & BRANDING PAGE
# ==========================================

def show_settings():
    """
    Manages tenant identity and UI branding.
    Only displays when the 'Settings' page is selected.
    """
    # 1. FETCH FRESH TENANT DATA
    try:
        tenant_id = st.session_state.get("tenant_id")
        
        if not tenant_id:
            st.warning("⚠️ No active tenant detected. Please log in.")
            return

        # Always pull fresh data so we have the latest logo_url and brand_color
        tenant_resp = supabase.table("tenants").select("*").eq("id", tenant_id).execute()
        
        if not tenant_resp.data:
            st.error("❌ Business profile not found.")
            return
            
        active_company = tenant_resp.data[0]

    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return

    # Dynamic Header Color based on Session State
    brand_color = st.session_state.get("theme_color", "#2B3F87")
    st.markdown(f"<h2 style='color: {brand_color};'>⚙️ Portal Settings & Branding</h2>", unsafe_allow_html=True)
    
    # --- BUSINESS IDENTITY SECTION ---
    st.subheader("🏢 Business Identity")
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown(f"**Current Business Name:** {active_company['name']}")
        
        # Color Picker - Standardized variable name 'new_color'
        new_color = st.color_picker(
            "🎨 Change Brand Color", 
            active_company.get('brand_color', '#2B3F87'),
            key="settings_color_picker"
        )
        
        st.markdown("**Preview:**")
        st.markdown(
            f"<div style='padding:15px; background-color:{new_color}; color:white; border-radius:10px; text-align:center; font-weight:bold;'>"
            f"Brand Color Preview"
            f"</div>", 
            unsafe_allow_html=True
        )
    
    with col2:
        st.markdown("**Company Logo:**")
        # Show current logo with cache-busting timestamp
        if active_company.get('logo_url'):
            import time
            logo_display_url = f"{active_company['logo_url']}?t={int(time.time())}"
            st.image(logo_display_url, use_container_width=True, caption="Current Logo")
        else:
            st.caption("No logo uploaded yet.")
            
        logo_file = st.file_uploader("Upload New Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])

    st.divider()

    # --- SAVE ACTION ---
    if st.button("💾 Save Branding Changes", use_container_width=True):
        import time 
        
        # 1. Prepare data for update
        updated_data = {"brand_color": new_color} 
        
        # 2. Handle logo upload if a new file exists
        if logo_file:
            try:
                bucket_name = 'company-logos'
                file_path = f"logos/{active_company['id']}_logo.png"
                
                # Upload to Supabase Storage
                supabase.storage.from_(bucket_name).upload(
                    path=file_path, 
                    file=logo_file.getvalue(),
                    file_options={
                        "x-upsert": "true", 
                        "content-type": "image/png"
                    }
                )
                
                # Retrieve Public URL
                public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
                updated_data["logo_url"] = public_url
                
            except Exception as e:
                st.error(f"❌ Storage Error: {str(e)}")
                st.stop()

        # 3. Update the 'tenants' table in Supabase
        try:
            supabase.table("tenants").update(updated_data).eq("id", active_company['id']).execute()
            
            # 4. SYNC MASTER SWITCH: Update session state for instant UI change
            st.session_state['theme_color'] = new_color
            
            st.success("✅ Branding updated successfully!")
            time.sleep(1) 
            st.rerun() # Refresh app to apply the new color everywhere
            
        except Exception as e:
            st.error(f"❌ Database Error: {str(e)}")
# ==========================================
# 1. CORE PAGE FUNCTIONS (Branding & Wide Layout)
# ==========================================

import streamlit as st
import pandas as pd
import plotly.express as px

# IMPORTANT: Run this as the very first Streamlit command in your app.py
# st.set_page_config(layout="wide") 

def get_active_color():
    """Helper to get the current theme color for consistent UI styling."""
    return st.session_state.get('theme_color', '#1E3A8A')

def show_overview():
    """Standard Overview Page with Dynamic Branding."""
    brand_color = get_active_color()
    st.markdown(f"<h2 style='color: {brand_color};'>📊 Financial Dashboard</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Loans", "0", "+0%")
    col2.metric("Active Borrowers", "0", "0")
    col3.metric("Revenue", "0 UGX", "0")
    
    st.info("👋 Welcome! Start by selecting a category from the sidebar.")

def show_dashboard_view():
    """
    Main Dashboard view. 
    Synchronized with Tenant brand_color and Wide Layout.
    """
    brand_color = get_active_color()
    st.markdown(f"<h2 style='color: {brand_color};'>📊 Financial Dashboard</h2>", unsafe_allow_html=True)
    
    # 1. LOAD DATA
    df = get_cached_data("loans")
    pay_df = get_cached_data("payments")
    exp_df = get_cached_data("expenses") 
    bor_df = get_cached_data("borrowers")

    if df.empty:
        st.info("👋 Welcome! Start by adding your first borrower or loan in the sidebar.")
        return

    # 2. STANDARDIZE COLUMNS
    for d in [df, pay_df, exp_df, bor_df]:
        if not d.empty:
            d.columns = d.columns.str.strip().str.replace(" ", "_")

    # 3. BRIDGE: Map borrower names
    bor_map = {}
    if not bor_df.empty and 'id' in bor_df.columns:
        bor_map = dict(zip(bor_df['id'].astype(str), bor_df['name'].astype(str)))
        
    if 'borrower_id' in df.columns:
        df['Borrower_Name'] = df['borrower_id'].astype(str).map(bor_map).fillna("Unknown")
    else:
        df['Borrower_Name'] = df.get('Borrower', 'Unknown')

    # 4. CLEAN DATA (Prevents 'int' object errors)
    def clean_val(dataframe, col):
        if col in dataframe.columns:
            return pd.to_numeric(dataframe[col], errors="coerce").fillna(0)
        return pd.Series(0, index=dataframe.index)

    df["Principal"] = clean_val(df, "Principal")
    df["Interest"] = clean_val(df, "Interest")
    df["Amount_Paid"] = clean_val(df, "Amount_Paid")
    df["End_Date"] = pd.to_datetime(df.get("End_Date"), errors="coerce")
    
    # Status Normalization
    df["Status_Clean"] = df["Status"].astype(str).str.title() if "Status" in df.columns else "Active"
    
    today = pd.Timestamp.now().normalize()
    active_statuses = ["Active", "Overdue", "Rolled/Overdue"]
    active_df = df[df["Status_Clean"].isin(active_statuses)].copy()

    # 5. METRICS CALCULATION
    total_issued = active_df["Principal"].sum() if not active_df.empty else 0
    total_interest_expected = active_df["Interest"].sum() if not active_df.empty else 0
    total_collected = df["Amount_Paid"].sum() 
    overdue_count = active_df[(active_df["End_Date"] < today) & (active_df["Status_Clean"] != "Cleared")].shape[0] if not active_df.empty else 0

    # 6. BRANDED METRICS ROW
    m1, m2, m3, m4 = st.columns(4)
    metric_style = f"background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid {brand_color};box-shadow:2px 2px 10px rgba(0,0,0,0.05);"
    
    m1.markdown(f'<div style="{metric_style}"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">💰 ACTIVE PRINCIPAL</p><h3 style="margin:0;color:{brand_color};font-size:18px;">{total_issued:,.0f} <span style="font-size:10px;">UGX</span></h3></div>', unsafe_allow_html=True)
    m2.markdown(f'<div style="{metric_style}"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">📈 EXPECTED INTEREST</p><h3 style="margin:0;color:{brand_color};font-size:18px;">{total_interest_expected:,.0f} <span style="font-size:10px;">UGX</span></h3></div>', unsafe_allow_html=True)
    m3.markdown(f'<div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #2E7D32;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">✅ TOTAL COLLECTED</p><h3 style="margin:0;color:#2E7D32;font-size:18px;">{total_collected:,.0f} <span style="font-size:10px;">UGX</span></h3></div>', unsafe_allow_html=True)
    m4.markdown(f'<div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #FF4B4B;box-shadow:2px 2px 10px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">🚨 OVERDUE FILES</p><h3 style="margin:0;color:#FF4B4B;font-size:18px;">{overdue_count}</h3></div>', unsafe_allow_html=True)

    st.write("---")
    
    # 7. BRANDED TABLES (Row HTML Logic Re-added)
    t1, t2 = st.columns(2)

    with t1:
        st.markdown(f"<h4 style='color: {brand_color};'>📝 Recent Portfolio Activity</h4>", unsafe_allow_html=True)
        rows_html = ""
        if not active_df.empty:
            recent_loans = active_df.sort_values(by="End_Date", ascending=False).head(5)
            for i, (_, r) in enumerate(recent_loans.iterrows()):
                bg = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
                rows_html += f"""<tr style="background-color: {bg}; border-bottom: 1px solid #eee;">
                    <td style="padding:10px;">{r.get('Borrower_Name', 'Unknown')}</td>
                    <td style="padding:10px; text-align:right; font-weight:bold; color:{brand_color};">{float(r.get('Principal', 0)):,.0f}</td>
                    <td style="padding:10px; text-align:center;"><span style="font-size:10px; background:{brand_color}22; color:{brand_color}; padding:2px 5px; border-radius:5px;">{r.get('Status_Clean', 'Active')}</span></td>
                    <td style="padding:10px; text-align:center; color:#666;">{pd.to_datetime(r.get('End_Date')).strftime('%d %b') if pd.notna(r.get('End_Date')) else "-"}</td>
                </tr>"""
        
        st.markdown(f"""<table style="width:100%; border-collapse:collapse; font-family:sans-serif; font-size:12px; border: 1px solid {brand_color}33;">
            <thead><tr style="background:{brand_color}; color:white;"><th style="padding:10px;">Borrower</th><th style="padding:10px; text-align:right;">Principal</th><th style="padding:10px; text-align:center;">Status</th><th style="padding:10px; text-align:center;">Due</th></tr></thead>
            <tbody>{rows_html if rows_html else "<tr><td colspan='4' style='text-align:center;padding:10px;'>No active loans</td></tr>"}</tbody>
        </table>""", unsafe_allow_html=True)

    with t2:
        st.markdown("<h4 style='color: #2E7D32;'>💸 Recent Cash Inflows</h4>", unsafe_allow_html=True)
        pay_rows = ""
        if not pay_df.empty:
            if 'borrower_id' in pay_df.columns:
                 pay_df['Borrower_Name'] = pay_df['borrower_id'].astype(str).map(bor_map).fillna("Unknown")
            
            recent_pay = pay_df.sort_values(by="Date", ascending=False).head(5)
            for i, (_, r) in enumerate(recent_pay.iterrows()):
                bg = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                pay_rows += f"""<tr style="background-color: {bg}; border-bottom: 1px solid #ddd;">
                    <td style="padding:10px;">{r.get('Borrower_Name', 'Unknown')}</td>
                    <td style="padding:10px; text-align:right; font-weight:bold; color:green;">{float(r.get('Amount', 0)):,.0f}</td>
                    <td style="padding:10px; text-align:center; color:#666;">{pd.to_datetime(r.get('Date')).strftime('%d %b') if pd.notna(r.get('Date')) else "-"}</td>
                </tr>"""
        
        st.markdown(f"""<table style="width:100%; border-collapse:collapse; font-family:sans-serif; font-size:12px; border: 1px solid #2E7D32;">
            <thead><tr style="background:#2E7D32; color:white;"><th style="padding:10px;">Borrower</th><th style="padding:10px; text-align:right;">Amount</th><th style="padding:10px; text-align:center;">Date</th></tr></thead>
            <tbody>{pay_rows if pay_rows else "<tr><td colspan='3' style='text-align:center;padding:10px;'>No recent payments</td></tr>"}</tbody>
        </table>""", unsafe_allow_html=True)

    # 8. DASHBOARD VISUALS (Charts Re-added)
    st.markdown("---")
    c_pie, c_bar = st.columns(2)

    with c_pie:
        if not df.empty:
            status_counts = df["Status_Clean"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            fig_pie = px.pie(status_counts, names="Status", values="Count", hole=0.5, title="Loan Distribution", color_discrete_sequence=["#4A90E2", "#FF4B4B", "#FFA500"])
            fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="#2B3F87", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_pie, use_container_width=True)

    with c_bar:
        if not pay_df.empty:
            pay_df["Date"] = pd.to_datetime(pay_df.get("Date"), errors='coerce')
            inc_m = pay_df.groupby(pay_df["Date"].dt.strftime('%b %Y'))["Amount"].sum().reset_index()
            
            # Use empty df for expenses if none exist to avoid merge crash
            if not exp_df.empty:
                exp_df["Date"] = pd.to_datetime(exp_df.get("Date"), errors='coerce')
                exp_m = exp_df.groupby(exp_df["Date"].dt.strftime('%b %Y'))["Amount"].sum().reset_index()
            else:
                exp_m = pd.DataFrame(columns=["Date", "Amount"])

            m_cash = pd.merge(inc_m, exp_m, on="Date", how="outer", suffixes=('_Inc', '_Exp')).fillna(0)
            m_cash.columns = ["Month", "Income", "Expenses"]
            fig_bar = px.bar(m_cash, x="Month", y=["Income", "Expenses"], barmode="group", title="Performance", color_discrete_map={"Income": "#2E7D32", "Expenses": "#FF4B4B"})
            fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#2B3F87")
            st.plotly_chart(fig_bar, use_container_width=True)
# ==========================================
# FINAL APP ROUTER (REACTIVE & STABLE)
# ==========================================

if __name__ == "__main__":
    if not st.session_state.get("logged_in"):
        st.session_state['theme_color'] = "#1E3A8A"
        apply_master_theme()
        run_auth_ui(supabase)
    else:
        try:
            # Wrap the authenticated logic in a try block
            check_session_timeout()
            
            # 1. SIDEBAR FIRST (Fetch color)
            page = render_sidebar()
            
            # 2. THEME SECOND (Apply color)
            apply_master_theme()
            
            # 3. CONTENT THIRD
            if page == "Settings":
                show_settings()
            elif page == "Overview":
                show_dashboard_view()
            elif page == "Loans":
                show_loans()
            elif page == "Borrowers":
                show_borrowers()
            elif page == "Collateral":
                show_collateral()
            elif page == "Calendar":
                show_calendar()
            elif page == "Ledger":
                show_ledger()
            elif page == "Overdue Tracker":
                show_overdue_tracker()
            elif page == "Payments":
                show_payments()
            elif page == "Expenses":
                show_expenses()
            elif page == "Petty Cash":
                show_petty_cash()
            elif page == "Payroll":
                show_payroll()
            else:
                st.info(f"The {page} module is coming online soon.")
                
        except Exception as e:
            st.error(f"Application Error: {e}")
