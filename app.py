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
from twilio.rest import Client as TwilioClient
import time
import streamlit as st
import pandas as pd
from datetime import datetime

# 1. CORE DATA ENGINE (Must be at the top level)
@st.cache_data(ttl=600)
def get_cached_data(table_name):
    """Fetches and caches data from Supabase for all pages."""
    try:
        # Use your existing supabase client connection here
        response = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        # This provides the error message you saw in your screenshots
        st.error(f"Error fetching data from {table_name}: {e}")
        return pd.DataFrame()

# Move this to the absolute top to prevent "Set Page Config" errors
st.set_page_config(
    page_title="Lending Manager Pro",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

SESSION_TIMEOUT = 30

# ==============================
# 1. THEME ENGINE (ENTERPRISE SAFE)
# ==============================
def apply_master_theme():
    # Fallback to a default if theme_color is missing
    brand_color = st.session_state.get("theme_color", "#1E3A8A")
    st.markdown(f"""
        <style>
            [data-testid="stSidebar"] {{
                background-color: {brand_color} !important;
            }}
            [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {{
                color: white !important;
                font-weight: 500 !important;
                font-size: 1rem !important;
            }}
            div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] div[data-bv-tabindex] {{
                border: 2px solid white !important;
            }}
            div[data-testid="stSidebar"] .stRadio div[role="radiogroup"] div[data-bv-tabindex="0"] > div {{
                background-color: #FF4B4B !important;
            }}
            [data-testid="stSidebar"] button {{
                background-color: white !important;
                color: {brand_color} !important;
                border-radius: 8px !important;
            }}
            /* Metric Card styling fix */
            div[data-testid="stMetricValue"] {{
                font-size: 1.8rem !important;
            }}
        </style>
    """, unsafe_allow_html=True)


# ==============================
# 2. SUPABASE INIT (SINGLE SOURCE OF TRUTH)
# ==============================
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets["supabase_url"]
        key = st.secrets["supabase_key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase connection credentials missing or invalid: {e}")
        st.stop()

supabase = init_supabase()


# ==============================
# 3. MULTI-TENANT SESSION CORE
# ==============================
if "tenant_id" not in st.session_state:
    st.session_state.tenant_id = None
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "theme_color" not in st.session_state:
    st.session_state.theme_color = "#2B3F87"


def get_tenant_id():
    return st.session_state.get("tenant_id")


def require_tenant():
    if not st.session_state.get("tenant_id"):
        st.error("Session expired or unauthorized access. Please log in again.")
        st.stop()


# ==============================
# 4. STORAGE HELPERS (FIXED + SAFE)
# ==============================
def upload_image(file, bucket="collateral-photos"):
    try:
        require_tenant()
        tenant_id = get_tenant_id()

        # Sanitize filename: remove special characters
        clean_name = re.sub(r'[^a-zA-Z0-9._-]', '_', file.name)
        file_name = f"{tenant_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{clean_name}"

        # Get file content and type
        file_content = file.getvalue()
        content_type = file.type

        # Upload to Supabase
        supabase.storage.from_(bucket).upload(
            path=file_name,
            file=file_content,
            file_options={"content-type": content_type}
        )
        
        # Get and return URL
        response = supabase.storage.from_(bucket).get_public_url(file_name)
        return response
        
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None


# ==============================
# 5. DATA LAYER (MERGED - NO DUPLICATES)
# ==============================

# INITIALIZE FIRST
loans_df = pd.DataFrame() 
borrowers_df = pd.DataFrame()

# THEN ATTEMPT TO FETCH
try:
    loans_df = get_cached_data("loans")
    borrowers_df = get_cached_data("borrowers")
except Exception as e:
    st.error(f"Error fetching data: {e}")
@st.cache_data(ttl=600)
def get_cached_data(table_name):
    try:
        require_tenant()
        tenant_id = get_tenant_id()
        
        # Execute Supabase query with tenant filter
        res = supabase.table(table_name)\
            .select("*")\
            .eq("tenant_id", tenant_id)\
            .execute()
            
        if res.data:
            df = pd.DataFrame(res.data)
            # Standardize column casing immediately upon load
            df.columns = df.columns.str.strip().str.lower()
            return df
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Database Fetch Error [{table_name}]: {e}")
        return pd.DataFrame()


def save_data(table_name, dataframe):
    try:
        require_tenant()
        if dataframe is None or dataframe.empty:
            return False

        # Ensure every record has the tenant_id before saving
        dataframe["tenant_id"] = get_tenant_id()
        
        # Convert to records and handle potential NaN values which Supabase dislikes
        records = dataframe.replace({np.nan: None}).to_dict("records")
        
        supabase.table(table_name).upsert(records).execute()
        
        # Clear cache to ensure the UI updates with new data
        st.cache_data.clear()
        return True

    except Exception as e:
        st.error(f"Database Save Error [{table_name}]: {e}")
        return False


# ==============================
# 6. AUTH CORE (UNIFIED - NO LOSS)
# ==============================
def authenticate(supabase, company_code, email, password):
    try:
        # Step 1: Auth with Supabase Identity
        res = supabase_client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if not res.user:
            return {"success": False, "error": "Invalid email or password"}

        # Step 2: Fetch Multi-tenant Profile
        profile = supabase_client.table("users")\
            .select("tenant_id, role, tenants(company_code, name)")\
            .eq("id", res.user.id)\
            .execute()

        if not profile.data:
            return {"success": False, "error": "User profile not found"}

        record = profile.data[0]
        tenant_info = record.get("tenants")

        if not tenant_info:
            return {"success": False, "error": "No business entity linked to this account"}

        # Step 3: Verify Company Code (Case-Insensitive)
        if tenant_info["company_code"].strip().upper() != company_code.strip().upper():
            return {"success": False, "error": "Incorrect Company Code"}

        return {
            "success": True,
            "user_id": res.user.id,
            "tenant_id": record["tenant_id"],
            "role": record.get("role", "Staff"),
            "company": tenant_info.get("name")
        }

    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            return {"success": False, "error": "Invalid email or password"}
        return {"success": False, "error": f"Authentication system error: {error_msg}"}


# ==============================
# 7. SESSION CREATION (FIXED)
# ==============================
def create_session(user_data):
    st.session_state.update({
        "logged_in": True,
        "user_id": user_data["user_id"],
        "tenant_id": user_data["tenant_id"],
        "role": user_data["role"],
        "company": user_data["company"],
        "last_activity": datetime.now()
    })
    try:
        st.rerun()
    except:
        pass


# ==============================
# 8. SESSION SECURITY
# ==============================
def check_session_timeout():
    if not st.session_state.get("logged_in"):
        return

    last = st.session_state.get("last_activity", datetime.now())
    if (datetime.now() - last) > timedelta(minutes=SESSION_TIMEOUT):
        # Full clear for security
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.warning("Your session has timed out for security. Please log in again.")
        st.stop()

    st.session_state["last_activity"] = datetime.now()


# ==============================
# 9. RATE LIMITING (SAFE)
# ==============================
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 10

def check_rate_limit(email):
    attempts = st.session_state.get("login_attempts", {})
    if email in attempts:
        count, last = attempts[email]
        if count >= MAX_ATTEMPTS and (datetime.now() - last) < timedelta(minutes=LOCKOUT_MINUTES):
            return False
    return True


def record_failed_attempt(email):
    attempts = st.session_state.setdefault("login_attempts", {})
    count, _ = attempts.get(email, (0, datetime.now()))
    attempts[email] = (count + 1, datetime.now())


# ==============================
# 10. CORE FIX: TENANT ISOLATION
# ==============================
def tenant_filter(df):
    """Secondary guard to ensure data belongs to the current tenant"""
    if df is None or df.empty:
        return df
    if "tenant_id" not in df.columns:
        return df
    return df[df["tenant_id"] == get_tenant_id()].copy()


import streamlit as st
from supabase import create_client

# ==============================
# 🔌 SUPABASE INIT (MUST BE FIRST)
# ==============================
import os

SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("🚨 Supabase credentials not configured")
    st.stop()
# ==============================
# 🔐 SESSION HANDLER
# ==============================
def create_session(result, remember_me=False):
    st.session_state["user"] = result.get("user")
    st.session_state["authenticated"] = True

    if remember_me:
        st.session_state["remember"] = True

    st.success("Login successful")
    st.rerun()

# ==============================
# 🔒 AUTH UI WRAPPER & ROUTER
# ==============================
def run_auth_ui(supabase):
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        login_page(supabase)   # ✅ PASS IT HERE
    else:
        st.success("Welcome to the dashboard 🚀")

    # 1. Check Authentication Status
    if st.session_state["authenticated"]:
        st.success("Welcome to the dashboard 🚀")
        if st.button("Log Out"):
            st.session_state["authenticated"] = False
            st.rerun()
        return # 👉 Your main app dashboard code would be called here

    # 2. Routing Logic for Unauthenticated Users
    if st.session_state.view == "login":
        login_page(supabase)
    elif st.session_state.view == "signup":
        # Ensure you have a signup_page function defined
        st.markdown("### 🆕 Sign Up Page") 
        if st.button("Back to Login"):
            st.session_state.view = "login"
            st.rerun()
    elif st.session_state.view == "forgot_password":
        st.markdown("### 🔑 Reset Password")
        if st.button("Back to Login"):
            st.session_state.view = "login"
            st.rerun()

# ==============================
# 🔑 LOGIN PAGE
# ==============================
def login_page(supabase):
    _, col, _ = st.columns([1, 2, 1])

    with col:
        st.image("https://via.placeholder.com/150", width=100)
        st.markdown("## 🔐 Finance Portal Login")

        company = st.text_input("Company Code").strip().upper()
        email = st.text_input("Email").strip().lower()
        password = st.text_input("Password", type="password")

        remember_me = st.checkbox("Remember Me", key="login_remember")

        if st.button("Access Dashboard", use_container_width=True):
            if not company or not email or not password:
                st.error("Please fill in all fields")
                return

            try:
                result = authenticate(supabase, company, email, password)
                if result.get("success"):
                    create_session(result, remember_me)
                else:
                    st.error(result.get("error", "Login failed"))
            except Exception as e:
                st.error(f"Login system error: {e}")

        # Navigation
        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("🆕 Create Account", use_container_width=True):
                st.session_state.view = "signup"
                st.rerun()

        with col2:
            if st.button("🔑 Forgot Password?", use_container_width=True):
                st.session_state.view = "forgot_password"
                st.rerun()

# ==============================
# 🔐 AUTH FUNCTION
# ==============================
def authenticate(supabase, company, email, password):
    try:
        # In a true multi-tenant setup, you'd verify the 'company' code here
        # against a 'tenants' table before attempting auth.
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if response.user:
            return {
                "success": True,
                "user": response.user
            }

        return {"success": False, "error": "Invalid login credentials"}

    except Exception as e:
        return {"success": False, "error": str(e)}

# ==============================
# 🚀 APP ENTRY POINT
# ==============================
if __name__ == "__main__":
    run_auth_ui(supabase)


# ==============================
# 12. ROUTER
# ==============================
def run_auth_ui():
    if "view" not in st.session_state:
        st.session_state.view = "login"

    if not st.session_state.get("logged_in"):
        login_page()
    else:
        # This will be handled by your main view logic
        pass


def render_sidebar():
    """
    ENTERPRISE MULTI-TENANT SIDEBAR (UPGRADED SAFELY)
    - No logic removed
    - Tenant switching hardened
    - Logo system fixed
    - Navigation state stabilized
    """

    # ==============================
    # 1. FETCH TENANTS (SAFE + ROBUST)
    # ==============================
    try:
        # Optimization: select only what we need to minimize bandwidth
        tenants_res = supabase.table("tenants")\
            .select("id, name, brand_color, logo_url")\
            .execute()

        tenant_map = {
            row['name']: row for row in tenants_res.data
        } if tenants_res.data else {}

    except Exception as e:
        st.sidebar.error(f"Error fetching tenants: {e}")
        tenant_map = {}

    current_tenant_id = st.session_state.get('tenant_id')

    # ==============================
    # 2. SIDEBAR UI
    # ==============================
    with st.sidebar:
        # ------------------------------
        # TENANT SWITCHER (HARDENED)
        # ------------------------------
        if tenant_map:
            options = list(tenant_map.keys())
            default_index = 0

            # Safe lookup of current tenant to set the default dropdown value
            if current_tenant_id:
                for i, name in enumerate(options):
                    if str(tenant_map[name]['id']) == str(current_tenant_id):
                        default_index = i
                        break

            Active_company_name = st.selectbox(
                "Business Portal:",
                options,
                index=default_index,
                key="sidebar_portal_select"
            )

            Active_company = tenant_map.get(Active_company_name, None)

            # ------------------------------
            # CRITICAL SYNC FIX (NO LOGIC LOSS)
            # ------------------------------
            if Active_company:
                # Only trigger a rerun if the tenant actually changed
                if str(st.session_state.get('tenant_id')) != str(Active_company['id']):
                    st.session_state['tenant_id'] = Active_company['id']
                    st.session_state['theme_color'] = Active_company.get('brand_color', '#2B3F87')
                    st.session_state['company'] = Active_company.get('name')

                    # Clear cache so the new company's data loads immediately
                    st.cache_data.clear()
                    try:
                        st.rerun()
                    except:
                        pass
        else:
            st.warning("No business entities found.")
            st.stop()

        # ==============================
        # 3. LOGO RENDER (FIXED + SAFE)
        # ==============================
        st.write("") # Spacer
        _, col_mid, _ = st.columns([1, 2, 1])

        with col_mid:
            logo_val = Active_company.get('logo_url') if Active_company else None

            # Logic to handle missing or null logo values
            if logo_val and str(logo_val).lower() not in ["0", "none", "null", ""]:
                # 1. If it's a direct URL
                if str(logo_val).startswith("http"):
                    final_logo_url = logo_val
                # 2. If it's a Supabase storage path
                else:
                    try:
                        project_url = st.secrets["supabase_url"].strip("/")
                        final_logo_url = f"{project_url}/storage/v1/object/public/company-logos/{logo_val}"
                    except Exception:
                        final_logo_url = None

                # Render with cache-busting timestamp to ensure updates show immediately
                if final_logo_url:
                    try:
                        st.image(f"{final_logo_url}?t={int(time.time())}", width=80)
                    except Exception:
                        st.markdown("<h1 style='text-align:center;'>🏢</h1>", unsafe_allow_html=True)
                else:
                    st.markdown("<h1 style='text-align:center;'>🏢</h1>", unsafe_allow_html=True)
            else:
                st.markdown("<h1 style='text-align:center;'>🌍</h1>", unsafe_allow_html=True)

        st.divider()

        # ==============================
        # 4. NAVIGATION MENU (PRESERVED)
        # ==============================
        menu = {
            "Overview": "📈",
            "Loans": "💵",
            "Borrowers": "👥",
            "Collateral": "🛡️",
            "Calendar": "📅",
            "Ledger": "📄",
            "Payroll": "💳",
            "Expenses": "📉",
            "Petty Cash": "🪙",
            "Overdue Tracker": "🚨",
            "Payments": "💰",
            "Settings": "⚙️"
        }

        menu_options = [f"{emoji} {name}" for name, emoji in menu.items()]
        current_p = st.session_state.get('current_page', "Overview")

        # Find the index of the current page for the radio button
        try:
            default_ix = list(menu.keys()).index(current_p)
        except (ValueError, Exception):
            default_ix = 0

        selection = st.radio(
            "Navigation",
            menu_options,
            index=default_ix,
            label_visibility="collapsed",
            key="navigation_radio"
        )

        st.divider()

        # ==============================
        # 5. LOGOUT (HARDENED SESSION WIPE)
        # ==============================
        if st.button("🚪 Logout", use_container_width=True):
            # Preserve only system-level settings if needed, wipe user data
            for key in list(st.session_state.keys()):
                if key not in ["theme_color"]: # Optional: keep theme through logout
                    del st.session_state[key]
            
            try:
                st.rerun()
            except:
                pass

    # ==============================
    # 6. PAGE RESOLUTION (SAFE PARSING)
    # ==============================
    try:
        # Extract the page name from the "Emoji Name" string
        final_page = selection.split(" ", 1)[1]
    except (IndexError, Exception):
        final_page = "Overview"

    st.session_state['current_page'] = final_page

    return final_page
        
# ==============================
# 12. BORROWERS MANAGEMENT PAGE (SAAS + DEBUG FIXED + ENTERPRISE UPGRADE)
# ==============================
import uuid 
import streamlit as st
import pandas as pd
import numpy as np

def show_borrowers():
    brand_color = st.session_state.get("theme_color", "#2B3F87")
    st.markdown(f"<h2 style='color: {brand_color};'>👥 Borrowers Management</h2>", unsafe_allow_html=True)
    
    # ==============================
    # 🔐 SAAS TENANT CONTEXT (HARDENED)
    # ==============================
    current_tenant = st.session_state.get('tenant_id')

    if not current_tenant:
        st.error("🔐 Session expired. Please login again.")
        st.stop()

    # ==============================
    # 1. FETCH DATA
    # ==============================
    df_raw = get_cached_data("borrowers")

    # ==============================
    # 🧠 ENTERPRISE SAFETY LAYER
    # ==============================
    if df_raw is not None and not df_raw.empty:
        # Standardize columns first
        df_raw.columns = df_raw.columns.str.strip().str.lower().str.replace(" ", "_")
        
        # Isolation Guard: Filter only for this tenant
        if "tenant_id" in df_raw.columns:
            df = df_raw[df_raw["tenant_id"].astype(str) == str(current_tenant)].copy()
        else:
            df = df_raw.copy()
            df["tenant_id"] = current_tenant
    else:
        df = pd.DataFrame(columns=[
            "id", "name", "phone", "email", "address",
            "national_id", "next_of_kin", "status", "tenant_id"
        ])

    # Ensure required columns exist for UI rendering
    required_cols = ["id", "name", "phone", "email", "address", "national_id", "next_of_kin", "status", "tenant_id"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    # Column Detection Logic (Preserved)
    name_col = next((c for c in df.columns if 'name' in c or 'borrower' in c), "name")
    phone_col = next((c for c in df.columns if 'phone' in c), "phone")
    status_col = next((c for c in df.columns if 'status' in c), "status")

    tab_view, tab_add, tab_audit = st.tabs(["📑 View All", "➕ Add New", "⚙️ Audit & Manage"])

    # ==============================
    # TAB 1: VIEW (HTML LEAK FIXED)
    # ==============================
    with tab_view:
        col1, col2 = st.columns([3, 1]) 
        with col1:
            search = st.text_input("🔍 Search Name or Phone", key="bor_search").lower()
        with col2:
            status_filter = st.selectbox("Filter Status", ["All", "Active", "InActive"], key="bor_status_filt")

        if not df.empty:
            filtered_df = df.copy()
            
            # String conversions for searching
            filtered_df[name_col] = filtered_df[name_col].astype(str)
            if phone_col in filtered_df.columns:
                filtered_df[phone_col] = filtered_df[phone_col].astype(str)
            
            # Application of Search Mask
            mask = filtered_df[name_col].str.lower().str.contains(search, na=False)
            if phone_col in filtered_df.columns:
                mask |= filtered_df[phone_col].str.contains(search, na=False)
                
            filtered_df = filtered_df[mask]
            
            if status_filter != "All" and status_col in filtered_df.columns:
                filtered_df = filtered_df[
                    filtered_df[status_col].astype(str).str.title() == status_filter
                ]

            if not filtered_df.empty:
                rows_html = ""
                for i, r in filtered_df.reset_index(drop=True).iterrows():
                    bg_color = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
                    
                    name_val = r.get(name_col, 'Unknown')
                    phone_val = r.get(phone_col, 'N/A')
                    email_val = r.get('email', 'N/A')
                    nok_val = r.get('next_of_kin', 'N/A')
                    stat_val = r.get(status_col, 'Active')
                    
                    rows_html += f"""
                    <tr style="background-color: {bg_color}; border-bottom: 1px solid #eee;">
                        <td style="padding:10px;">{name_val}</td>
                        <td style="padding:10px;">{phone_val}</td>
                        <td style="padding:10px;">{email_val}</td>
                        <td style="padding:10px;">{nok_val}</td>
                        <td style="padding:10px;"><span style="background:{brand_color};color:white;padding:3px 10px;border-radius:12px;font-size:11px;">{stat_val}</span></td>
                    </tr>"""
                
                st.markdown(f"""
                    <div style="overflow-x:auto;">
                        <table style="width:100%; border-collapse:collapse; font-size:14px;">
                            <thead>
                                <tr style="background:{brand_color}; color:white; text-align:left;">
                                    <th style="padding:12px;">Name</th>
                                    <th style="padding:12px;">Phone</th>
                                    <th style="padding:12px;">Email</th>
                                    <th style="padding:12px;">Next of Kin</th>
                                    <th style="padding:12px;">Status</th>
                                </tr>
                            </thead>
                            <tbody>{rows_html}</tbody>
                        </table>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.info("No matching borrowers found.")
        else:
            st.info("No borrowers registered yet.")
            

    # ==============================
    # TAB 2: ADD (ID CONFLICT FIXED)
    # ==============================
    with tab_add:
        with st.form("add_borrower_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name_in = c1.text_input("Full Name*")
            phone_in = c2.text_input("Phone Number*")

            email_in = st.text_input("Email (Optional)")
            address_in = st.text_input("Address (Optional)")
            nid_in = st.text_input("National ID (Optional)")
            nok_in = st.text_input("Next of Kin (Optional)")

            if st.form_submit_button("🚀 Save Borrower Profile"):
                if name_in and phone_in:
                    # Logic: Create a fresh record
                    new_entry = {
                        "id": str(uuid.uuid4()),
                        "name": name_in,
                        "phone": phone_in,
                        "email": email_in,
                        "address": address_in,
                        "national_id": nid_in,
                        "next_of_kin": nok_in,
                        "status": "Active",
                        "tenant_id": str(current_tenant)
                    }
                    
                    # Merge with existing dataframe safely
                    temp_df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)

                    if save_data("borrowers", temp_df):
                        st.success(f"✅ Borrower '{name_in}' successfully registered!")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    st.error("⚠️ Name and Phone Number are required fields.")

    # ==============================
    # TAB 3: AUDIT (TENANT-SAFE JOINS)
    # ==============================
    with tab_audit:
        if not df.empty:
            target_name = st.selectbox("Search & Select Borrower to Manage", df[name_col].unique())
            b_data = df[df[name_col] == target_name].iloc[0]

            # Fetch loans for this specific borrower
            u_loans = get_cached_data("loans")

            if u_loans is not None and not u_loans.empty:
                # Security: Force filter loans by tenant_id
                if "tenant_id" in u_loans.columns:
                    u_loans = u_loans[u_loans["tenant_id"].astype(str) == str(current_tenant)]

                u_loans.columns = u_loans.columns.str.strip().str.lower().str.replace(" ", "_")
                loan_bor_ref = next((c for c in u_loans.columns if 'borrower' in c), None)
                
                if loan_bor_ref:
                    # Link logic: match based on name or ID
                    user_loans = u_loans[u_loans[loan_bor_ref].astype(str) == str(target_name)]

                    st.markdown("### 📊 Borrower Activity")
                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric("Total Loans", len(user_loans))
                    
                    if not user_loans.empty:
                        st.dataframe(user_loans, use_container_width=True)
                    else:
                        st.info("No loan history found for this borrower.")

            st.divider()
            st.markdown("### 🛠️ Administrative Actions")
            ca1, ca2 = st.columns(2)

            # Update Logic (Atomic)
            if ca1.button("💾 Save Profile Changes", use_container_width=True):
                # Logic to update specific record in current DF
                df.loc[df["id"] == b_data["id"], "name"] = target_name
                if save_data("borrowers", df):
                    st.success("✅ Records updated.")
                    st.cache_data.clear()
                    st.rerun()

            # Delete Logic (Tenant-Aware)
            if ca2.button("🗑️ Permanent Delete", use_container_width=True):
                # Filter out the target ID
                updated_df = df[df["id"] != b_data["id"]]
                if save_data("borrowers", updated_df):
                    st.warning(f"🗑️ Record for {target_name} deleted.")
                    st.cache_data.clear()
                    st.rerun()
        else:
            st.info("💡 Start by adding borrowers in the 'Add New' tab.")
# ==============================
# 🔐 SAAS TENANT CONTEXT (HARDENED)
# ==============================
def get_current_tenant():
    """Returns current tenant_id from session (SaaS isolation layer)"""
    return st.session_state.get("tenant_id", "default_tenant")

# ==============================
# 🧠 DATABASE ADAPTER (MULTI-TENANT SAFE)
# ==============================
def get_data(table_name):
    """Multi-tenant safe data fetch with auto-migration for old records"""
    tenant_id = get_current_tenant()
    df = get_cached_data(table_name)

    if df is not None and not df.empty:
        # Standardize column names to lowercase/underscore
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
        
        if "tenant_id" in df.columns:
            # Force string comparison for UUID/Integer flexibility
            df = df[df["tenant_id"].astype(str) == str(tenant_id)].copy()
        else:
            # Auto-assign tenant_id if it's a legacy table missing the column
            df["tenant_id"] = tenant_id
    
    return df

def save_data_saas(table_name, df):
    """Multi-tenant safe save with hard enforcement of boundaries"""
    tenant_id = get_current_tenant()
    
    # Force the tenant_id on every single row before it touches the DB
    df["tenant_id"] = str(tenant_id)
    
    # Restore user-friendly column names for the database if necessary
    # (Optional: depends on if your DB expects "Loan ID" or "loan_id")
    return save_data(table_name, df)


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
    loans_df = get_cached_data("loans")
    borrowers_df = get_cached_data("borrowers")

    # ✅ SAFETY (prevents future crashes)
    if loans_df is None:
        loans_df = pd.DataFrame()

    if borrowers_df is None:
        borrowers_df = pd.DataFrame()

    # Standardize Borrowers
    if not borrowers_df.empty:
        Active_borrowers = borrowers_df[borrowers_df["status"] == "Active"]
    else:
        Active_borrowers = pd.DataFrame()

    if loans_df.empty:
        loans_df = pd.DataFrame(columns=[
            "id", "borrower", "principal", "interest",
            "total_repayable", "amount_paid", "balance",
            "status", "start_date", "end_date"
        ])

    # 2. AUTO-CALC & DATA CLEANING
    num_cols = ["principal", "interest", "total_repayable", "amount_paid", "balance"]

    for col in num_cols:
        if col in loans_df.columns:
            loans_df[col] = pd.to_numeric(loans_df[col], errors='coerce').fillna(0)

    loans_df["balance"] = (loans_df["total_repayable"] - loans_df["amount_paid"]).clip(lower=0)

    # ✅ AUTOMATIC STATUS UPDATE FOR SETTLED LOANS
    closed_mask = loans_df["balance"] <= 0
    loans_df.loc[closed_mask, "status"] = "CLOSED"
    loans_df.loc[closed_mask, "balance"] = 0

    tab_view, tab_add, tab_manage, tab_actions = st.tabs([
        "📑 Portfolio View", "➕ New Loan", "🛠️ Manage/Edit", "⚙️ Actions"
    ])

    # ==============================
    # TAB: PORTFOLIO VIEW
    # ==============================
    with tab_view:
        # 1. Define styling function (Top of tab for clarity)
        def style_loan_table(row):
            status = str(row.get("status", "")).upper()
            colors = {
                "ACTIVE": "#4A90E2", "CLOSED": "#2E7D32", "OVERDUE": "#D32F2F",
                "ROLLED": "#7B1FA2", "BCF": "#FFA500", "PENDING": "#FBC02D"
            }
            s_color = colors.get(status, "#9E9E9E")
            styles = ['background-color: #FFF9F5; color: #0A192F;'] * len(row)
            
            if "status" in row.index:
                status_idx = row.index.get_loc("status")
                styles[status_idx] = (
                    f'background-color: {s_color}; color: white; font-weight: bold; '
                    f'border-radius: 6px; text-align: center; padding: 4px;'
                )
            return styles

        # 2. Check Data & Build Mapping
        if not loans_df.empty:
            if not borrowers_df.empty:
                bor_map = dict(zip(borrowers_df['id'], borrowers_df['name']))
                loans_df['borrower'] = loans_df['borrower_id'].map(bor_map).fillna("Unknown")
            else:
                loans_df['borrower'] = "No Borrower Data"

            loans_df['display_label'] = loans_df['loan_id_label'].astype(str) + " - " + loans_df['borrower'].astype(str)

            # 3. Selection & Metrics
            sel_label = st.selectbox(
                "🔍 Select Loan to Inspect",
                options=loans_df['display_label'].unique(),
                key="inspect_sel_v5"
            )

            latest_info = loans_df[loans_df["display_label"] == sel_label].iloc[-1]
            rec_val = float(latest_info.get('amount_paid', 0))
            total_rep = float(latest_info.get('total_repayable', 0))
            out_val = total_rep - rec_val
            stat_val = str(latest_info.get('status', 'N/A')).upper()

            if stat_val == "CLOSED":
                out_val = 0

            # 4. Metric Cards
            c1, c2, c3 = st.columns(3)
            card_style = "background-color:#FFF9F5; padding:20px; border-radius:15px; border-left:10px solid #0A192F; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);"
            text_style = "margin:0; color:#0A192F;"

            c1.markdown(f"""<div style="{card_style}"><p style="{text_style} font-size:11px; font-weight:bold;">✅ RECEIVED</p><h3 style="{text_style} font-size:18px;">{rec_val:,.0f} <span style="font-size:10px;">UGX</span></h3></div>""", unsafe_allow_html=True)
            c2.markdown(f"""<div style="{card_style}"><p style="{text_style} font-size:11px; font-weight:bold;">🚨 OUTSTANDING</p><h3 style="{text_style} font-size:18px;">{out_val:,.0f} <span style="font-size:10px;">UGX</span></h3></div>""", unsafe_allow_html=True)
            c3.markdown(f"""<div style="{card_style}"><p style="{text_style} font-size:11px; font-weight:bold;">📑 STATUS</p><h3 style="{text_style} font-size:18px;">{stat_val}</h3></div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # 5. Main Portfolio Table
            show_cols = ["loan_id_label", "borrower", "principal", "total_repayable", "start_date", "status"]
            
            st.dataframe(
                loans_df[show_cols].style
                .format({"principal": "{:,.0f}", "total_repayable": "{:,.0f}"})
                .apply(style_loan_table, axis=1),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No loans found. Head over to 'New Loan' to get started!")

    # ==============================
    # TAB: NEW LOAN (Supabase Integration)
    # ==============================
    with tab_add:
        if Active_borrowers.empty:
            st.info("💡 Tip: Activate a borrower first.")
        else:
            with st.form("loan_issue_form"):
                st.markdown("<h4 style='color: #0A192F;'>📝 Create New Loan Agreement</h4>", unsafe_allow_html=True)
                col1, col2 = st.columns(2)
                
                borrower_map = dict(zip(Active_borrowers["name"], Active_borrowers["id"]))
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
                    t_id = st.session_state.get('tenant_id', 'test-tenant-123')
                    
                    import random
                    readable_label = f"LN-{random.randint(1000, 9999)}"

                    loan_data = {
                        "loan_id_label": readable_label, 
                        "borrower_id": selected_id, 
                        "principal": float(amount), 
                        "interest": float((interest_rate/100)*amount),
                        "total_repayable": float(total_due), 
                        "amount_paid": 0.0,
                        "status": "ACTIVE", # ✅ Matches DB Constraint
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
            st.info("No Active loans to roll over.")
        else:
            eligible_loans = loans_df[loans_df["status"] != "CLOSED"]
            
            if eligible_loans.empty:
                st.success("All loans are currently settled! ✨")
            else:
                roll_sel = st.selectbox("Select Loan to Roll Over", eligible_loans["id"].unique())
                loan_to_roll = eligible_loans[eligible_loans["id"] == roll_sel].iloc[0]
                
                st.warning(f"You are rolling over Loan #{roll_sel}")
                
                current_unpaid = loan_to_roll['balance']
                new_interest_rate = st.number_input("New Monthly Interest (%)", value=10.0)
                
                if st.button("🔥 Execute Rollover", use_container_width=True):
                    # 1. Update old loan - Set status to ROLLED (All Caps to match DB)
                    supabase.table("loans").update({"status": "ROLLED"}).eq("id", loan_to_roll['id']).execute()
                    
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
                        "status": "ACTIVE", # ✅ Starts as Active
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
                e_borr = c1.text_input("Borrower Name (Note: ID remains linked)", value=loan_to_edit['borrower'])
                e_princ = c1.number_input("Principal", value=float(loan_to_edit['principal']))
                # ✅ Selector restricted to your DB Check Constraint options
                e_stat = c2.selectbox("Status", ["ACTIVE", "PENDING", "CLOSED", "OVERDUE", "BCF", "ROLLED"], index=0)
                
                if st.form_submit_button("💾 Save Changes"):
                    update_payload = {
                        "principal": e_princ, 
                        "status": e_stat, 
                        "tenant_id": st.session_state.get('tenant_id', 'default-admin')
                    }
                    
                    # Use direct supabase call for singular edit
                    supabase.table("loans").update(update_payload).eq("id", target_id).execute()
                    st.success("✅ Loan updated!")
                    st.rerun()

            if st.button("🗑️ Delete Loan Permanently", use_container_width=True):
                supabase.table("loans").delete().eq("id", target_id).execute()
                st.warning("Loan Deleted.")
                st.rerun()

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
    # TAB 2: HISTORY
    # ==============================
    with tab_history:
        if payments_df is not None and not payments_df.empty:
            df_display = payments_df.copy().sort_values("date", ascending=False)
            
            # Formatting for display
            df_display["amount_fmt"] = df_display["amount"].apply(lambda x: f"UGX {x:,.0f}")
            
            st.dataframe(
                df_display[["date", "borrower", "amount_fmt", "method", "receipt_no", "recorded_by"]],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No transaction history found for this tenant.")

    # ==============================
    # TAB 3: MANAGE (ADMIN)
    # ==============================
    with tab_manage:
        if payments_df is not None and not payments_df.empty:
            p_sel_id = st.selectbox("Select Receipt to Action", payments_df["receipt_no"].unique())
            p_row = payments_df[payments_df["receipt_no"] == p_sel_id].iloc[0]

            st.warning("⚠️ Warning: Deleting or editing payments requires a manual balance reconciliation of the associated loan.")
            
            if st.button("🗑️ Void Payment Receipt", type="primary", use_container_width=True):
                try:
                    # Tenant-safe deletion check
                    supabase.table("payments").delete().eq("receipt_no", p_sel_id).eq("tenant_id", t_id).execute()
                    st.success(f"Receipt {p_sel_id} voided.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Deletion failed: {e}")

# ==============================
# 15. COLLATERAL MANAGEMENT PAGE (SAAS + ENTERPRISE UPGRADE)
# ==============================
import mimetypes
from datetime import datetime
import pandas as pd
import streamlit as st

def show_collateral():
    brand_color = st.session_state.get("theme_color", "#2B3F87")
    current_tenant = st.session_state.get('tenant_id')

    # ==============================
    # 🔐 SAFETY CHECK (HARDENED)
    # ==============================
    if not current_tenant:
        st.error("🔐 Session expired. Please log in.")
        st.stop()

    st.markdown(f"<h2 style='color: {brand_color};'>🛡️ Collateral & Security</h2>", unsafe_allow_html=True)

    # ==============================
    # FETCH DATA (SAFE)
    # ==============================
    # Using the safe adapters from previous parts
    collateral_df = get_data("collateral") 
    loans_df = get_data("loans")

    # ==============================
    # NORMALIZE LOANS COLUMNS (SAFE)
    # ==============================
    if loans_df is not None and not loans_df.empty:
        # Filter for loans that actually need collateral (Active, Overdue, Pending)
        Active_statuses = ["Active", "overdue", "pending"]
        available_loans = loans_df[loans_df["status"].str.lower().isin(Active_statuses)].copy()
    else:
        available_loans = pd.DataFrame()

    # --- TABS ---
    tab_reg, tab_view = st.tabs(["➕ Register Asset", "📋 Inventory & Status"])

    # ==============================
    # TAB 1: REGISTER COLLATERAL
    # ==============================
    with tab_reg:
        if available_loans.empty:
            st.warning("⚠️ No Active loans found to attach collateral to.")
        else:
            with st.form("collateral_reg_form", clear_on_submit=True):
                st.write("### Link Asset to Loan")
                c1, c2 = st.columns(2)

                # Create dropdown labels: "Borrower Name (Loan ID)"
                loan_labels = available_loans.apply(
                    lambda x: f"{x['borrower']} (ID: {x['loan_id']})", axis=1
                ).tolist()
                
                selected_label = c1.selectbox("Select Loan/Borrower", options=loan_labels)
                asset_type = c2.selectbox(
                    "Asset Type",
                    ["Logbook (Car)", "Land Title", "Electronics", "House Deed", "Business Stock", "Other"]
                )

                desc = st.text_input("Detailed Asset Description (e.g. Plate No, Plot No)")
                est_value = st.number_input("Estimated Market Value (UGX)", min_value=0, step=100000)
                
                st.markdown("---")
                # Photo upload (Note: In a real app, this would stream to Supabase Storage)
                uploaded_photo = st.file_uploader("Upload Asset Photo (Verification)", type=["jpg", "png", "jpeg"])

                if st.form_submit_button("💾 Save & Secure Asset", use_container_width=True):
                    if not desc or est_value <= 0:
                        st.error("Please provide a description and valid value.")
                    else:
                        # Extract the actual loan_id from the label
                        actual_loan_id = selected_label.split("(ID: ")[1].replace(")", "")
                        borrower_name = selected_label.split(" (ID:")[0]

                        new_asset = pd.DataFrame([{
                            "loan_id": actual_loan_id,
                            "tenant_id": str(current_tenant),
                            "borrower": borrower_name,
                            "type": asset_type,
                            "description": desc,
                            "value": float(est_value),
                            "status": "In Custody",
                            "date_added": datetime.now().strftime("%Y-%m-%d")
                        }])

                        if save_data_saas("collateral", new_asset):
                            st.success(f"✅ Asset secured for {borrower_name}!")
                            st.cache_data.clear()
                            st.rerun()

    # ==============================
    # TAB 2: INVENTORY & STATUS
    # ==============================
    with tab_view:
        if collateral_df is None or collateral_df.empty:
            st.info("💡 No assets currently in the registry.")
        else:
            # Metrics
            total_value = collateral_df["value"].sum()
            held_count = len(collateral_df[collateral_df["status"] == "In Custody"])
            
            m1, m2 = st.columns(2)
            m1.metric("Total Asset Value", f"UGX {total_value:,.0f}")
            m2.metric("Items in Custody", held_count)

            st.markdown("### Asset Ledger")
            
            # Clean display for the table
            display_df = collateral_df.copy()
            display_df["value"] = display_df["value"].apply(lambda x: f"{x:,.0f}")
            
            st.dataframe(
                display_df[["date_added", "borrower", "type", "description", "value", "status"]],
                use_container_width=True,
                hide_index=True
            )

            # --- MANAGE SECTION ---
            with st.expander("⚙️ Release or Dispose Assets"):
                # Filter for assets that haven't been released yet
                manageable = collateral_df[collateral_df["status"] != "Released"].copy()
                
                if manageable.empty:
                    st.write("All assets are currently released.")
                else:
                    asset_to_manage = st.selectbox(
                        "Select Asset to Update", 
                        manageable.apply(lambda x: f"{x['borrower']} - {x['description']}", axis=1)
                    )
                    
                    # Logic to find the specific ID
                    selected_idx = manageable.index[manageable.apply(lambda x: f"{x['borrower']} - {x['description']}", axis=1) == asset_to_manage][0]
                    asset_id = manageable.at[selected_idx, "id"] if "id" in manageable.columns else None

                    col_stat, col_btn = st.columns([2,1])
                    new_stat = col_stat.selectbox("Set New Status", ["In Custody", "Released", "Disposed (Auctioned)", "Held for Pickup"])
                    
                    if col_btn.button("Update Status", use_container_width=True):
                        update_row = pd.DataFrame([{
                            "id": asset_id, # Requires the DB generated ID
                            "status": new_stat,
                            "tenant_id": str(current_tenant)
                        }])
                        
                        if save_data_saas("collateral", update_row):
                            st.success("Asset status updated!")
                            st.cache_data.clear()
                            st.rerun()
            

# ==============================
# 17. ACTIVITY CALENDAR PAGE
# ==============================
def show_calendar():
    
    st.markdown("<h2 style='color: #2B3F87;'>📅 Activity Calendar</h2>", unsafe_allow_html=True)

    # 1. FETCH DATA
    loans_df = get_cached_data("loans")
    borrowers_df = get_cached_data("borrowers") # Added to fetch names

    if loans_df is None or loans_df.empty:
        st.info("📅 Calendar is clear! No active loans to track.")
        return

    # --- INJECT BORROWER NAMES (Fixes the "Strings" in Calendar & Tables) ---
    if borrowers_df is not None and not borrowers_df.empty:
        bor_map = dict(zip(borrowers_df['id'], borrowers_df['name']))
        loans_df['borrower'] = loans_df['borrower_id'].map(bor_map).fillna("Unknown")
    else:
        loans_df['borrower'] = "Unknown"

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
            # Color logic: Red for overdue, Blue for upcoming
            is_overdue = r['end_date'].date() < today.date()
            ev_color = "#FF4B4B" if is_overdue else "#4A90E2"
            
            # Use the mapped 'borrower' name here
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

    # 2. DAILY WORKLOAD METRICS
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

    # 4. ACTION ITEMS (Formatted with Human Names)
    st.markdown("<h4 style='color: #2B3F87;'>📌 Action Items for Today</h4>", unsafe_allow_html=True)
    if due_today_df.empty:
        st.success("✨ No deadlines for today.")
    else:
        # Fixed: Using 'loan_id_label' for ID and 'borrower' for name
        today_rows = "".join([f"""<tr style="background:#F0F8FF;"><td style="padding:10px;"><b>#{r.get('loan_id_label', r['id'])}</b></td><td style="padding:10px;">{r['borrower']}</td><td style="padding:10px;text-align:right;">{r['total_repayable']:,.0f}</td><td style="padding:10px;text-align:center;"><span style="background:#2B3F87;color:white;padding:2px 8px;border-radius:10px;font-size:10px;">💰 COLLECT NOW</span></td></tr>""" for _, r in due_today_df.iterrows()])
        st.markdown(f"""<div style="border:2px solid #2B3F87;border-radius:10px;overflow:hidden;"><table style="width:100%;border-collapse:collapse;font-size:12px;"><tr style="background:#2B3F87;color:white;"><th style="padding:10px;">ID</th><th style="padding:10px;">Borrower</th><th style="padding:10px;text-align:right;">Amount</th><th style="padding:10px;text-align:center;">Action</th></tr>{today_rows}</table></div>""", unsafe_allow_html=True)

    # 5. OVERDUE FOLLOW-UP
    st.markdown("<br><h4 style='color: #FF4B4B;'>🔴 Past Due (Immediate Attention)</h4>", unsafe_allow_html=True)
    overdue_df = active_loans[active_loans["end_date"] < today].copy()
    if not overdue_df.empty:
        overdue_df["days_late"] = (today - overdue_df["end_date"]).dt.days
        od_rows = ""
        for _, r in overdue_df.iterrows():
            late_color = "#FF4B4B" if r['days_late'] > 7 else "#FFA500"
            # Fixed: Using 'loan_id_label' for ID and 'borrower' for name
            od_rows += f"""<tr style="background:#FFF5F5;"><td style="padding:10px;"><b>#{r.get('loan_id_label', r['id'])}</b></td><td style="padding:10px;">{r['borrower']}</td><td style="padding:10px;color:{late_color};font-weight:bold;">{r['days_late']} Days</td><td style="padding:10px;text-align:center;"><span style="background:{late_color};color:white;padding:2px 8px;border-radius:10px;font-size:10px;">{r['status']}</span></td></tr>"""
        st.markdown(f"""<div style="border:2px solid #FF4B4B;border-radius:10px;overflow:hidden;"><table style="width:100%;border-collapse:collapse;font-size:12px;"><tr style="background:#FF4B4B;color:white;"><th style="padding:10px;">ID</th><th style="padding:10px;">Borrower</th><th style="padding:10px;text-align:center;">Late By</th><th style="padding:10px;text-align:center;">Status</th></tr>{od_rows}</table></div>""", unsafe_allow_html=True)                                                                
                                                                                                                                                                                                                                                                 
# ==============================
# 18. EXPENSE MANAGEMENT PAGE (SAAS + ENTERPRISE UPGRADE)
# ==============================

import plotly.express as px
import uuid
import pandas as pd
import streamlit as st
from datetime import datetime

def show_expenses():
    """
    Tracks business operational costs for specific tenants.
    (Upgraded for enterprise SaaS safety)
    """
    st.markdown("<h2 style='color: #2B3F87;'>📁 Expense Management</h2>", unsafe_allow_html=True)
    
    # ==============================
    # 🔐 SAAS TENANT CONTEXT (HARDENED)
    # ==============================
    current_tenant = st.session_state.get('tenant_id', 'default_tenant')

    # ==============================
    # 1. FETCH DATA (SAFE WRAPPER ADDED)
    # ==============================
    try:
        # Pulling data using your existing cache logic
        df = get_cached_data("expenses")
    except Exception:
        df = pd.DataFrame()

    # ==============================
    # SAAS FILTER (UNCHANGED LOGIC + SAFETY)
    # ==============================
    if df is not None and not df.empty:
        if "tenant_id" in df.columns:
            df = df[df["tenant_id"].astype(str) == str(current_tenant)]
        else:
            df["tenant_id"] = current_tenant

    EXPENSE_CATS = ["Rent", "Insurance Account", "Utilities", "Salaries", "Marketing", "Office Expenses"]

    # ==============================
    # EMPTY DATA SAFE INIT (UNCHANGED STRUCTURE)
    # ==============================
    if df is None or df.empty:
        df = pd.DataFrame(columns=[
            "id", "category", "amount", "date",
            "description", "payment_date", "receipt_no", "tenant_id"
        ])

    # ==============================
    # COLUMN GUARANTEE (NO LOGIC REMOVED)
    # ==============================
    for col in ["id", "category", "amount", "date", "description",
                "payment_date", "receipt_no", "tenant_id"]:
        if col not in df.columns:
            df[col] = None

    # ==============================
    # TABS (UNCHANGED)
    # ==============================
    tab_add, tab_view, tab_manage = st.tabs([
        "➕ Record Expense", "📊 Spending Analysis", "⚙️ Manage/Delete"
    ])

    # ==============================
    # TAB 1: ADD (SAFE WRAPPER ONLY)
    # ==============================
    with tab_add:
        with st.form("add_expense_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            category = col1.selectbox("Category", EXPENSE_CATS)
            amount = col2.number_input("Amount (UGX)", min_value=0, step=1000)
            desc = st.text_input("Description")

            c_date, c_receipt = st.columns(2)
            p_date = c_date.date_input("Actual Payment Date", value=datetime.now())
            receipt_no = c_receipt.text_input("Receipt / Invoice #")

            if st.form_submit_button("🚀 Save Expense Record", use_container_width=True):
                if amount > 0 and desc:
                    try:
                        new_entry = pd.DataFrame([{
                            "id": str(uuid.uuid4()),
                            "category": category,
                            "amount": float(amount),
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "description": desc,
                            "payment_date": p_date.strftime("%Y-%m-%d"),
                            "receipt_no": receipt_no,
                            "tenant_id": current_tenant
                        }])

                        updated_df = pd.concat([df, new_entry], ignore_index=True)

                        if save_data("expenses", updated_df):
                            st.success("✅ Expense recorded!")
                            st.cache_data.clear() # Ensure analytics update
                            st.rerun()
                    except Exception as e:
                        st.error(f"🚨 Save failed: {e}")
                else:
                    st.error("⚠️ Provide amount & description.")

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

    # ==============================
    # TAB 3: MANAGE (ENTERPRISE SAFE)
    # ==============================
    with tab_manage:
        st.markdown("### 🛠️ Manage Outflow Records")

        if df.empty:
            st.info("ℹ️ No expenses found to manage.")
        else:
            try:
                df = df.copy()

                df["id"] = df["id"].astype(str)
                df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

                # Create a selection label for the dropdown
                df["label"] = df.apply(
                    lambda r: f"{r['category']} - {r['amount']:,.0f} UGX | {str(r['payment_date'])[:10]}",
                    axis=1
                )

                exp_map = {row["label"]: row for _, row in df.iterrows()}
                selected_label = st.selectbox("🔍 Select Expense to Edit/Delete", list(exp_map.keys()))

                if selected_label:
                    exp_to_edit = exp_map[selected_label]
                    exp_id = exp_to_edit["id"]

                    with st.form("edit_expense_form"):
                        up_amt = st.number_input("Update Amount", value=float(exp_to_edit['amount']))
                        
                        if st.form_submit_button("💾 Save Changes"):
                            df.loc[df["id"] == exp_id, "amount"] = up_amt
                            # Clean up the helper label before saving
                            final_df = df.drop(columns=['label'])
                            if save_data("expenses", final_df):
                                st.success("✅ Updated!")
                                st.cache_data.clear()
                                st.rerun()

                    st.divider()

                    if st.button("🗑️ Delete Selected Expense", type="secondary", use_container_width=True):
                        df = df[df["id"] != exp_id]
                        final_df = df.drop(columns=['label'])
                        if save_data("expenses", final_df):
                            st.success("✅ Deleted!")
                            st.cache_data.clear()
                            st.rerun()

            except Exception as e:
                st.error(f"🚨 Manage error: {e}")

# ==============================
# 19. PAYROLL MANAGEMENT PAGE
# ==============================

import pandas as pd
import streamlit as st
from datetime import datetime

def show_payroll():
    """
    Handles employee compensation, tax compliance, and multi-tenant payroll logs.
    Preserves exact Excel-matching PAYE and NSSF logic.
    """
    if st.session_state.get("role") != "Admin":
        st.error("🔒 Restricted Access: Only Administrators can process payroll.")
        return

    st.markdown("<h2 style='color: #4A90E2;'>🧾 Payroll Management</h2>", unsafe_allow_html=True)

    current_tenant = st.session_state.get("tenant_id")

    # ==============================
    # 🔐 SAFETY CHECK (SAAS HARD GUARD)
    # ==============================
    if not current_tenant:
        st.error("🔐 Session expired. Please log in again.")
        st.stop()

    # ==============================
    # 1. FETCH TENANT DATA
    # ==============================
    df = get_cached_data("payroll")

    required_keys = [
        "id","employee","tin","designation","mob_no","account_no","nssf_no",
        "arrears","basic_salary","absent_deduction","lst","gross_salary",
        "paye","nssf_5","advance_drs","other_deductions","net_pay",
        "nssf_10","nssf_15","date"
    ]

    if df is None or df.empty:
        df = pd.DataFrame(columns=required_keys)

    # Filter data to only show records for the Active tenant
    if "tenant_id" in df.columns:
        df = df[df["tenant_id"].astype(str) == str(current_tenant)]
    else:
        df["tenant_id"] = current_tenant

    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # ==============================
    # CALC ENGINE (UGANDAN TAX COMPLIANCE)
    # ==============================
    def run_manual_sync_calculations(basic, arrears, absent_deduct, advance, other):
        basic = float(basic or 0)
        arrears = float(arrears or 0)
        absent_deduct = float(absent_deduct or 0)
        advance = float(advance or 0)
        other = float(other or 0)

        # 1. Calculate Gross
        gross = (basic + arrears) - absent_deduct
        
        # 2. Local Service Tax (LST) - Standard 100k/year for gross > 1m
        lst = 100000 / 12 if gross > 1000000 else 0

        # 3. NSSF Calculations (5% Employee, 10% Employer)
        n5, n10 = gross * 0.05, gross * 0.10
        n15 = n5 + n10

        # 4. PAYE (Ugandan Pay As You Earn) Logic
        paye = 0
        if gross > 410000:
            paye = 25000 + (0.30 * (gross - 410000))
        elif gross > 235000:
            paye = (gross - 235000) * 0.10

        total_deductions = paye + lst + n5 + advance + other
        net = gross - total_deductions

        return {
            "gross": round(gross),
            "lst": round(lst),
            "n5": round(n5),
            "n10": round(n10),
            "n15": round(n15),
            "paye": round(paye),
            "net": round(net)
        }

    tab_process, tab_logs = st.tabs(["➕ Process Salary","📜 Payroll History"])

    # ==============================
    # PROCESS TAB
    # ==============================
    with tab_process:
        with st.form("new_payroll_form", clear_on_submit=True):
            name = st.text_input("Employee Name")

            c1, c2, c3 = st.columns(3)
            f_tin = c1.text_input("TIN")
            f_desig = c2.text_input("Designation")
            f_mob = c3.text_input("Mob No.")

            c4, c5 = st.columns(2)
            f_acc = c4.text_input("Account No.")
            f_nssf_no = c5.text_input("NSSF No.")

            c6, c7, c8 = st.columns(3)
            f_arrears = c6.number_input("ARREARS", min_value=0.0)
            f_basic = c7.number_input("SALARY (Basic)", min_value=0.0)
            f_absent = c8.number_input("Absenteeism Deduction", min_value=0.0)

            c9, c10 = st.columns(2)
            f_adv = c9.number_input("S.DRS / ADVANCE", min_value=0.0)
            f_other = c10.number_input("Other Deductions", min_value=0.0)

            if st.form_submit_button("💳 Confirm & Release Payment", use_container_width=True):
                if name and f_basic > 0:
                    calc = run_manual_sync_calculations(
                        f_basic, f_arrears, f_absent, f_adv, f_other
                    )

                    new_row = pd.DataFrame([{
                        "employee": name,
                        "tin": f_tin,
                        "designation": f_desig,
                        "mob_no": f_mob,
                        "account_no": f_acc,
                        "nssf_no": f_nssf_no,
                        "arrears": f_arrears,
                        "basic_salary": f_basic,
                        "absent_deduction": f_absent,
                        "gross_salary": calc["gross"],
                        "lst": calc["lst"],
                        "paye": calc["paye"],
                        "nssf_5": calc["n5"],
                        "nssf_10": calc["n10"],
                        "nssf_15": calc["n15"],
                        "advance_drs": f_adv,
                        "other_deductions": f_other,
                        "net_pay": calc["net"],
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "tenant_id": current_tenant
                    }])

                    if save_data("payroll", new_row):
                        st.success(f"✅ Payroll for {name} saved!")
                        st.cache_data.clear()
                        st.rerun()

    # ==============================
    # LOGS TAB (REPORTS & EXPORT)
    # ==============================
    with tab_logs:
        if not df.empty:
            def fm(x):
                try:
                    return f"{int(float(x)):,}"
                except:
                    return "0"

            header_html = """
            <style>
                .pay-table { width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 13px; }
                .pay-table th { background: #f8f9fa; border: 1px solid #ddd; padding: 10px; }
                .pay-table td { border: 1px solid #ddd; padding: 10px; }
            </style>
            <table class='pay-table'>
                <thead>
                    <tr>
                        <th>#</th><th>Employee</th><th>Arrears</th><th>Basic</th><th>Gross</th>
                        <th>PAYE</th><th>NSSF 5%</th><th>Net Pay</th><th>NSSF 10%</th><th>NSSF 15%</th>
                    </tr>
                </thead>
                <tbody>
            """

            rows_html = ""
            for i, r in df.iterrows():
                rows_html += f"""
                <tr>
                    <td style='text-align:center;'>{i+1}</td>
                    <td><b>{r.get('employee','')}</b><br><small>{r.get('designation','-')}</small></td>
                    <td style='text-align:right;'>{fm(r.get('arrears',0))}</td>
                    <td style='text-align:right;'>{fm(r.get('basic_salary',0))}</td>
                    <td style='text-align:right;font-weight:bold;'>{fm(r.get('gross_salary',0))}</td>
                    <td style='text-align:right;'>{fm(r.get('paye',0))}</td>
                    <td style='text-align:right;'>{fm(r.get('nssf_5',0))}</td>
                    <td style='text-align:right;background:#E3F2FD;font-weight:bold;'>{fm(r.get('net_pay',0))}</td>
                    <td style='text-align:right;background:#FFF9C4;'>{fm(r.get('nssf_10',0))}</td>
                    <td style='text-align:right;background:#FFF9C4;font-weight:bold;'>{fm(r.get('nssf_15',0))}</td>
                </tr>
                """

            total_net = df["net_pay"].sum()

            footer_html = f"""
                </tbody>
                <tfoot>
                    <tr style="background:#2B3F87;color:white;font-weight:bold;">
                        <td colspan="7" style="text-align:center;padding:12px;">GRAND TOTALS</td>
                        <td style="text-align:right;padding:12px;">{fm(total_net)}</td>
                        <td colspan="2"></td>
                    </tr>
                </tfoot>
            </table>
            """

            full_html = header_html + rows_html + footer_html

            if st.button("📥 Print PDF", key="print_pay_btn"):
                st.components.v1.html("<script>window.print();</script>", height=0)

            st.components.v1.html(full_html, height=600, scrolling=True)

            st.write("---")
            with st.expander("⚙️ Manage Record"):
                if not df.empty:
                    sel_opt = st.selectbox(
                        "Select Record",
                        [f"{r.get('employee','')} (ID: {r.get('id','')})" for _, r in df.iterrows()]
                    )

                    if st.button("🗑️ Delete Record"):
                        try:
                            sid = sel_opt.split("(ID: ")[1].replace(")", "")
                            supabase.table("payroll").delete().eq("id", sid).execute()
                            st.warning("Deleted.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete failed: {e}")
# ==============================
# 20. ADVANCED ANALYTICS & REPORTS (SAAS + ENTERPRISE)
# ==============================
import plotly.express as px
import pandas as pd
import streamlit as st

def show_reports():
    """
    Consolidates multi-tenant data to provide financial health metrics.
    Preserves Net Profit logic and Portfolio at Risk (PAR) assessment.
    """
    st.markdown("<h2 style='color: #4A90E2;'>📊 Advanced Analytics & Reports</h2>", unsafe_allow_html=True)

    # ==============================
    # 🔐 SAAS SAFETY (NEW HARD GUARD)
    # ==============================
    current_tenant = st.session_state.get("tenant_id", "default_tenant")

    # 1. FETCH ALL RELEVANT DATA
    loans = get_cached_data("loans")
    payments = get_cached_data("payments")
    expenses = get_cached_data("expenses")
    payroll = get_cached_data("payroll")
    petty = get_cached_data("petty_cash")

    # ==============================
    # 🔐 SAAS FILTER (NEW - CONSISTENCY FIX)
    # ==============================
    def safe_filter(df):
        if df is None or df.empty:
            return df
        if "tenant_id" in df.columns:
            return df[df["tenant_id"].astype(str) == str(current_tenant)]
        return df

    loans = safe_filter(loans)
    payments = safe_filter(payments)
    expenses = safe_filter(expenses)
    payroll = safe_filter(payroll)
    petty = safe_filter(petty)

    if loans is None or loans.empty:
        st.info("📈 Record more loan data to see your financial analytics.")
        return

    # ==============================
    # 2. PAYROLL SAFETY & TAX TOTALS (Logic Intact)
    # ==============================
    nssf_total, paye_total = 0, 0
    if payroll is not None and not payroll.empty:
        n5 = pd.to_numeric(payroll.get("nssf_5", 0), errors="coerce").fillna(0).sum()
        n10 = pd.to_numeric(payroll.get("nssf_10", 0), errors="coerce").fillna(0).sum()
        nssf_total = n5 + n10
        paye_total = pd.to_numeric(payroll.get("paye", 0), errors="coerce").fillna(0).sum()

    # ==============================
    # 3. CONSOLIDATED DATA SUMS
    # ==============================
    l_amt = pd.to_numeric(loans.get("principal", 0), errors="coerce").fillna(0).sum()
    l_int = pd.to_numeric(loans.get("interest", 0), errors="coerce").fillna(0).sum()

    p_amt = pd.to_numeric(payments.get("amount", 0), errors="coerce").fillna(0).sum() if payments is not None else 0
    exp_amt = pd.to_numeric(expenses.get("amount", 0), errors="coerce").fillna(0).sum() if expenses is not None else 0

    petty_out = 0
    if petty is not None and not petty.empty:
        petty_out = pd.to_numeric(
            petty[petty["type"] == "Out"].get("amount", 0),
            errors="coerce"
        ).fillna(0).sum()

    # 💰 FINANCIAL LOGIC (PRESERVED)
    # Total outflow includes operational expenses + petty cash spent + tax liabilities
    total_outflow = exp_amt + petty_out + nssf_total + paye_total
    net_profit = p_amt - total_outflow

    # ==============================
    # 4. KPI DASHBOARD
    # ==============================
    st.subheader("🚀 Financial Performance")
    k1, k2, k3, k4 = st.columns(4)

    k1.markdown(f"""<div style="background-color:#fff;padding:15px;border-radius:10px;border-left:5px solid #4A90E2;box-shadow:2px 2px 8px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">CAPITAL ISSUED</p><h4 style="margin:0;color:#4A90E2;">{l_amt:,.0f}</h4></div>""", unsafe_allow_html=True)
    k2.markdown(f"""<div style="background-color:#fff;padding:15px;border-radius:10px;border-left:5px solid #4A90E2;box-shadow:2px 2px 8px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">INTEREST ACCRUED</p><h4 style="margin:0;color:#4A90E2;">{l_int:,.0f}</h4></div>""", unsafe_allow_html=True)
    k3.markdown(f"""<div style="background-color:#fff;padding:15px;border-radius:10px;border-left:5px solid #2E7D32;box-shadow:2px 2px 8px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">COLLECTIONS</p><h4 style="margin:0;color:#2E7D32;">{p_amt:,.0f}</h4></div>""", unsafe_allow_html=True)

    p_color = "#2E7D32" if net_profit >= 0 else "#FF4B4B"
    k4.markdown(f"""<div style="background-color:#fff;padding:15px;border-radius:10px;border-left:5px solid {p_color};box-shadow:2px 2px 8px rgba(0,0,0,0.05);"><p style="margin:0;font-size:11px;color:#666;font-weight:bold;">NET PROFIT</p><h4 style="margin:0;color:{p_color};">{net_profit:,.0f}</h4></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ==============================
    # 5. VISUAL ANALYTICS
    # ==============================
    st.markdown("---")
    col_left, col_right = st.columns(2)

    with col_left:
        st.write("**💰 Income vs. Expenses (Trend)**")

        if payments is not None and not payments.empty:
            payments = payments.copy()
            payments["date"] = pd.to_datetime(payments.get("date", pd.NaT), errors='coerce')

            inc_trend = payments.groupby(payments["date"].dt.strftime('%Y-%m'))["amount"].sum().reset_index()

            exp_trend = pd.DataFrame(columns=["date", "amount"])
            if expenses is not None and not expenses.empty:
                expenses = expenses.copy()
                expenses["date"] = pd.to_datetime(expenses.get("date", pd.NaT), errors='coerce')
                exp_trend = expenses.groupby(expenses["date"].dt.strftime('%Y-%m'))["amount"].sum().reset_index()

            merged = pd.merge(inc_trend, exp_trend, on="date", how="outer").fillna(0)
            merged.columns = ["Month", "Income", "Expenses"]
            merged = merged.sort_values("Month")

            fig_bar = px.bar(
                merged,
                x="Month",
                y=["Income", "Expenses"],
                barmode="group",
                color_discrete_map={"Income": "#10B981", "Expenses": "#FF4B4B"}
            )
            fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend_title="", margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No transaction history for trend analysis.")

    with col_right:
        st.write("**🛡️ Portfolio Weight (Top 5 Borrowers)**")

        # Group principal issued by borrower to check concentration risk
        top_borrowers = loans.groupby("borrower")["principal"].sum().sort_values(ascending=False).head(5).reset_index()

        fig_pie = px.pie(
            top_borrowers,
            names="borrower",
            values="principal",
            hole=0.5,
            color_discrete_sequence=px.colors.sequential.GnBu_r
        )
        fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', showlegend=True, margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig_pie, use_container_width=True)

    # ==============================
    # 6. RISK INDICATOR (PAR % FIXED SAFETY)
    # ==============================
    st.markdown("---")
    st.subheader("🚨 Risk Assessment (Portfolio at Risk)")

    loans = loans.copy()
    loans["end_date"] = pd.to_datetime(loans.get("end_date", pd.NaT), errors="coerce")
    loans["status"] = loans.get("status", "").astype(str)

    # PAR calculation: Sum of principal on overdue loans / Total principal issued
    overdue_mask = (
        loans["status"].str.lower().isin(["overdue", "rolled/overdue", "pending"]) &
        (loans["end_date"].dt.date < pd.Timestamp.today().date())
    )

    overdue_val = pd.to_numeric(loans.loc[overdue_mask, "principal"], errors="coerce").fillna(0).sum()
    risk_percent = (overdue_val / l_amt * 100) if l_amt > 0 else 0

    r1, r2 = st.columns([2, 1])

    with r1:
        st.write(f"Your Portfolio at Risk (PAR) is **{risk_percent:.1f}%**.")
        # Progress bar colors are handled by the threshold logic in r2
        st.progress(min(float(risk_percent) / 100, 1.0))
        st.write(f"Total Overdue Principal: **{overdue_val:,.0f} UGX**")

    with r2:
        if risk_percent < 10:
            st.success("✅ Healthy Portfolio")
        elif risk_percent < 25:
            st.warning("⚠️ Moderate Risk")
        else:
            st.error("🆘 Critical Risk Level")
# ==============================
# 21. MASTER LEDGER (SAAS + ENTERPRISE)
# ==============================

import pandas as pd
import streamlit as st
from datetime import datetime

def show_ledger():
    """
    Detailed transaction audit for individual loans.
    Generates a consolidated HTML statement with automated running balances.
    """
    st.markdown("<h2 style='color: #2B3F87;'>📘 Master Ledger</h2>", unsafe_allow_html=True)
    
    # 1. LOAD DATA
    loans_df = get_cached_data("loans")
    payments_df = get_cached_data("payments")

    if loans_df is None or loans_df.empty:
        st.info("💡 Your system is clear! No Active loans found.")
        return

    # ==============================
    # 🔐 SAAS SAFETY + NORMALIZATION LAYER
    # ==============================
    # Normalize column names for robust matching
    loans_df.columns = loans_df.columns.str.strip().str.lower().str.replace(" ", "_")

    if payments_df is not None and not payments_df.empty:
        payments_df.columns = payments_df.columns.str.strip().str.lower().str.replace(" ", "_")

    current_tenant = st.session_state.get("tenant_id", "default_tenant")

    # Ensure tenant safety: only show loans belonging to this tenant
    if "tenant_id" in loans_df.columns:
        loans_df = loans_df[loans_df["tenant_id"].astype(str) == str(current_tenant)]

    # ==============================
    # BORROWER RESOLUTION (UNCHANGED LOGIC)
    # ==============================
    borrowers_df = get_cached_data("borrowers")
    bor_map = {}

    if borrowers_df is not None and not borrowers_df.empty:
        borrowers_df.columns = borrowers_df.columns.str.strip().str.lower().str.replace(" ", "_")
        bor_name_col = next((c for c in borrowers_df.columns if "name" in c), "name")
        bor_map = dict(zip(borrowers_df["id"].astype(str), borrowers_df[bor_name_col]))

    if "borrower" not in loans_df.columns:
        # Resolve names from IDs if the direct column is missing
        loans_df["borrower"] = loans_df["borrower_id"].astype(str).map(bor_map).fillna("Unknown")

    # ==============================
    # SELECTION LOGIC
    # ==============================
    loan_options = [f"ID: {r['id']} - {r['borrower']}" for _, r in loans_df.iterrows()]
    selected_loan = st.selectbox("Select Loan to View Full Statement", loan_options, key="ledger_main_select")
    
    try:
        raw_id = int(selected_loan.split(" - ")[0].replace("ID: ", "").strip())
        loan_info = loans_df[loans_df["id"] == raw_id].iloc[0]
    except Exception as e:
        st.error(f"Error locating loan record: {e}")
        return

    # ==============================
    # BALANCE CALCULATIONS (PRESERVED)
    # ==============================
    current_p = float(loan_info.get("principal", 0))
    interest_amt = float(loan_info.get("interest", 0))
    amount_paid = float(loan_info.get("amount_paid", 0))
    
    display_bal = (current_p + interest_amt) - amount_paid

    st.markdown(f"""
        <div style="background-color: #ffffff; padding: 25px; border-radius: 15px; border-left: 5px solid #2B3F87; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); margin-bottom: 20px;">
            <p style="margin:0; font-size:14px; color:#666; font-weight:bold;">CURRENT OUTSTANDING BALANCE (INC. INTEREST)</p>
            <h1 style="margin:0; color:#2B3F87;">{display_bal:,.0f} <span style="font-size:18px;">UGX</span></h1>
        </div>
    """, unsafe_allow_html=True)

    # ==============================
    # LEDGER BUILD (RUNNING BALANCE LOGIC)
    # ==============================
    ledger_data = []

    # 1. Opening Entry
    ledger_data.append({
        "Date": loan_info.get("start_date", "-"),
        "Description": "Initial Loan Disbursement",
        "Debit": current_p,
        "Credit": 0,
        "Balance": current_p
    })

    # 2. Interest Entry
    if interest_amt > 0:
        ledger_data.append({
            "Date": loan_info.get("start_date", "-"),
            "Description": "➕ Interest Charged",
            "Debit": interest_amt,
            "Credit": 0,
            "Balance": current_p + interest_amt
        })

    # 3. Payment Entries
    if payments_df is not None and not payments_df.empty:
        rel_pay = payments_df.copy()

        if "loan_id" in rel_pay.columns:
            rel_pay = rel_pay[rel_pay["loan_id"].astype(str) == str(raw_id)]

        if "date" in rel_pay.columns:
            rel_pay = rel_pay.sort_values("date")

        curr_run_bal = current_p + interest_amt

        for _, pay in rel_pay.iterrows():
            p_amt = float(pay.get("amount", 0))
            curr_run_bal -= p_amt

            ledger_data.append({
                "Date": pay.get("date", "-"),
                "Description": f"✅ Repayment ({pay.get('method', 'Cash')})",
                "Debit": 0,
                "Credit": p_amt,
                "Balance": curr_run_bal
            })

    # Render audit table
    st.dataframe(
        pd.DataFrame(ledger_data).style.format({
            "Debit": "{:,.0f}",
            "Credit": "{:,.0f}",
            "Balance": "{:,.0f}"
        }),
        use_container_width=True,
        hide_index=True
    )

    # ==============================
    # PRINTABLE STATEMENT (HTML/PDF PREVIEW)
    # ==============================
    st.markdown("---")

    if st.button("✨ Preview Consolidated Statement", use_container_width=True):

        borrowers_df = get_cached_data("borrowers")
        current_b_name = loan_info.get("borrower", "Unknown")

        # Fetch detailed borrower contact info for the header
        b_details = {}
        if borrowers_df is not None and not borrowers_df.empty:
            borrowers_df.columns = borrowers_df.columns.str.strip().str.lower().str.replace(" ", "_")
            b_data = borrowers_df[borrowers_df["id"].astype(str) == str(loan_info.get("borrower_id"))]
            b_details = b_data.iloc[0] if not b_data.empty else {}

        navy_blue, baby_blue = "#000080", "#E1F5FE"

        html_statement = f"""
        <div id="printable-area" style="font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; border: 1px solid #eee; background: white; color: #333;">
            <div style="background: {navy_blue}; color: white; padding: 30px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h1 style="margin:0;">{st.session_state.get('company_name', 'ZOE CONSULTS').upper()}</h1>
                    <p style="margin:0; opacity:0.8;">OFFICIAL CLIENT STATEMENT</p>
                </div>
                <div style="text-align: right;">
                    <p style="margin:0; font-size: 18px;"><b>{current_b_name}</b></p>
                    <p style="margin:0;">{datetime.now().strftime('%d %b %Y')}</p>
                </div>
            </div>
            <div style="padding: 15px; border: 1px solid #ddd; border-top: none; background: #fafafa; font-size: 13px;">
                <p style="margin:0;"><b>Phone:</b> {b_details.get('phone', 'N/A')} | <b>Address:</b> {b_details.get('address', 'N/A')}</p>
            </div>
        """

        grand_total = 0.0

        # Filter all loans for this specific borrower to provide a consolidated view
        client_loans = loans_df[loans_df["borrower"] == current_b_name]

        for _, l_row in client_loans.iterrows():
            l_id = l_row['id']
            p, i = float(l_row.get('principal', 0)), float(l_row.get('interest', 0))

            l_pay = 0
            if payments_df is not None and not payments_df.empty:
                l_pay = payments_df[payments_df["loan_id"].astype(str) == str(l_id)]["amount"].sum()

            l_bal = (p + i) - l_pay
            grand_total += l_bal

            html_statement += f"""
            <div style="margin-top: 20px; padding: 12px; background: {baby_blue}; border-left: 4px solid {navy_blue}; font-weight: bold; color: {navy_blue}; display: flex; justify-content: space-between;">
                <span>LOAN REFERENCE: #{l_id}</span>
                <span>BALANCE: {l_bal:,.0f} UGX</span>
            </div>
            """

        html_statement += f"""
            <div style="margin-top: 40px; padding: 25px; border: 2px solid {navy_blue}; text-align: right; background: #f8faff; border-radius: 8px;">
                <h2 style="color: {navy_blue}; margin: 0; font-size: 16px;">TOTAL CONSOLIDATED OUTSTANDING</h2>
                <h1 style="color: #FF4B4B; margin: 0; font-size: 32px;">{grand_total:,.0f} UGX</h1>
            </div>
            <div style="margin-top: 20px; font-size: 10px; color: #999; text-align: center;">
                Generated by Zoe Finance Core • This is a computer-generated document.
            </div>
        </div>"""

        st.components.v1.html(html_statement, height=600, scrolling=True)
# ==============================
# 22. SETTINGS & BRANDING (SAAS CONTROL CENTER)
# ==============================

import streamlit as st
import time

def show_settings():
    """
    Manages tenant identity and UI branding.
    Only displays when the 'Settings' page is selected.
    """

    # ==============================
    # 🔐 TENANT SAFETY LAYER (HARD GUARD)
    # ==============================
    tenant_id = st.session_state.get("tenant_id")

    if not tenant_id:
        st.warning("⚠️ No Active tenant detected. Please log in.")
        return

    # ==============================
    # 1. FETCH TENANT DATA (SAFE + HARDENED)
    # ==============================
    try:
        # Fetching the business profile specifically for this tenant
        tenant_resp = supabase.table("tenants").select("*").eq("id", tenant_id).execute()

        if not tenant_resp.data:
            st.error("❌ Business profile not found.")
            return

        Active_company = tenant_resp.data[0]

    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return

    # ==============================
    # BRANDING FALLBACK SAFETY
    # ==============================
    # Priority: Session State -> Database -> Default Navy
    brand_color = st.session_state.get(
        "theme_color", 
        Active_company.get("brand_color", "#2B3F87")
    )

    st.markdown(
        f"<h2 style='color: {brand_color};'>⚙️ Portal Settings & Branding</h2>",
        unsafe_allow_html=True
    )

    # --- BUSINESS IDENTITY SECTION ---
    st.subheader("🏢 Business Identity")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(f"**Current Business Name:** {Active_company.get('name', 'Unknown')}")

        new_color = st.color_picker(
            "🎨 Change Brand Color",
            Active_company.get('brand_color', '#2B3F87'),
            key="settings_color_picker"
        )

        st.markdown("**Preview:**")
        st.markdown(
            f"""
            <div style='padding:15px; 
                        background-color:{new_color}; 
                        color:white; 
                        border-radius:10px; 
                        text-align:center; 
                        font-weight:bold;'>
                Brand Color Preview
            </div>
            """, 
            unsafe_allow_html=True
        )

    with col2:
        st.markdown("**Company Logo:**")
        
        logo_url = Active_company.get("logo_url")

        # ==============================
        # LOGO DISPLAY SAFETY (CACHE BUSTING)
        # ==============================
        if logo_url:
            try:
                # Append timestamp to URL to force browser refresh on logo update
                logo_display_url = f"{logo_url}?t={int(time.time())}"
                st.image(logo_display_url, use_container_width=True, caption="Current Logo")
            except Exception:
                st.caption("⚠️ Logo could not be loaded.")
        else:
            st.caption("No logo uploaded yet.")

        logo_file = st.file_uploader("Upload New Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])

    st.divider()

    # --- SAVE ACTION ---
    if st.button("💾 Save Branding Changes", use_container_width=True):
        
        updated_data = {"brand_color": new_color}

        # ==============================
        # LOGO UPLOAD SAFETY (STORAGE BUCKET)
        # ==============================
        if logo_file:
            try:
                bucket_name = "company-logos"
                # Use tenant ID in file path to ensure uniqueness and security
                file_path = f"logos/{Active_company.get('id')}_logo.png"

                # Upload to Supabase Storage with upsert enabled
                supabase.storage.from_(bucket_name).upload(
                    path=file_path,
                    file=logo_file.getvalue(),
                    file_options={
                        "x-upsert": "true",
                        "content-type": "image/png"
                    }
                )

                # Generate public URL for database storage
                public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
                updated_data["logo_url"] = public_url

            except Exception as e:
                st.error(f"❌ Storage Error: {str(e)}")
                st.stop()

        # ==============================
        # DATABASE UPDATE (PERSISTENCE)
        # ==============================
        try:
            supabase.table("tenants").update(updated_data).eq("id", Active_company.get("id")).execute()
            
            # Immediately update session state for real-time UI feel
            st.session_state["theme_color"] = new_color
            if "logo_url" in updated_data:
                st.session_state["logo_url"] = updated_data["logo_url"]

            st.success("✅ Branding updated successfully!")
            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Database Error: {str(e)}")
# ==========================================
# 1. CORE PAGE FUNCTIONS (BRANDING & WIDE LAYOUT)
# ==========================================

import streamlit as st
import pandas as pd
import plotly.express as px

def get_Active_color():
    """Helper to get the current theme color for consistent UI styling."""
    return st.session_state.get('theme_color', '#1E3A8A')

def show_dashboard_view():
    """
    Main Dashboard view. 
    Upgraded: performance layer, safer finance engine, SaaS-safe computation.
    """
    # 0. INITIALIZE THEME (Prevents NameError for brand_color)
    brand_color = get_Active_color()
    
    st.markdown(f"<h2 style='color: {brand_color};'>📊 Financial Dashboard</h2>", unsafe_allow_html=True)

    # --- 1. LOAD DATA ---
    df = get_cached_data("loans")
    pay_df = get_cached_data("payments")
    exp_df = get_cached_data("expenses") 
    bor_df = get_cached_data("borrowers")

    if df is None or df.empty:
        st.info("👋 Welcome! Start by adding your first borrower or loan in the sidebar.")
        st.stop()

    # --- 2. SAFE UTILS ---
    def safe_numeric(df, col_list):
        for col in col_list:
            if df is not None and col in df.columns:
                return pd.to_numeric(df[col], errors="coerce").fillna(0)
        return pd.Series(0.0, index=df.index if df is not None else [])

    def safe_date(df, col_list):
        for col in col_list:
            if df is not None and col in df.columns:
                return pd.to_datetime(df[col], errors="coerce")
        return pd.Series(pd.NaT, index=df.index if df is not None else [])

    # --- 3. SAFE COLUMN STANDARDIZATION ---
    def normalize(d):
        if d is not None and not d.empty:
            d.columns = d.columns.str.strip().str.lower().str.replace(" ", "_")
        return d

    df = normalize(df)
    pay_df = normalize(pay_df)
    exp_df = normalize(exp_df)
    bor_df = normalize(bor_df)

    df_clean = df.copy()

    # --- 4. BORROWER MAPPING ---
    bor_map = {}
    if bor_df is not None and not bor_df.empty:
        b_id = next((c for c in bor_df.columns if 'id' in c), None)
        b_nm = next((c for c in bor_df.columns if 'name' in c or 'borrower' in c), None)
        if b_id and b_nm:
            bor_map = dict(zip(bor_df[b_id].astype(str), bor_df[b_nm].astype(str)))

    link_col = next((c for c in df_clean.columns if 'borrower_id' in c or 'borrower' in c), None)
    if link_col:
        df_clean["borrower_name"] = df_clean[link_col].astype(str).map(bor_map).fillna(df_clean[link_col])
    else:
        df_clean["borrower_name"] = "Unknown Borrower"

    # --- 5. FINANCIAL ENGINE ---
    df_clean["principal_clean"] = safe_numeric(df_clean, ["principal", "amount"])
    df_clean["interest_clean"] = safe_numeric(df_clean, ["interest", "interest_amount"])
    df_clean["paid_clean"] = (
        safe_numeric(df_clean, ["paid"]) + 
        safe_numeric(df_clean, ["repaid"]) + 
        safe_numeric(df_clean, ["amount_paid"])
    )

    stat_col = next((c for c in df_clean.columns if "status" in c), None)
    df_clean["status_clean"] = df_clean[stat_col].astype(str).str.title() if stat_col else "Active"
    df_clean["end_date_dt"] = safe_date(df_clean, ["end_date", "due_date", "date"])

    # --- 6. PRE-FILTER ENGINE ---
    today = pd.Timestamp.now().normalize()
    Active_statuses = ["Active", "Overdue", "Rolled/Overdue"]
    Active_df = df_clean[df_clean["status_clean"].isin(Active_statuses)].copy()
    overdue_df = Active_df[Active_df["end_date_dt"] < today]

    # --- 7. CORE METRICS ---
    total_issued = Active_df["principal_clean"].sum()
    total_interest_expected = Active_df["interest_clean"].sum()
    total_collected = df_clean["paid_clean"].sum()
    overdue_count = len(overdue_df)

    # --- 8. DISPLAY METRIC CARDS ---
    m1, m2, m3, m4 = st.columns(4)
    card_style = f"background:#fff;padding:20px;border-radius:15px;border-left:5px solid {brand_color};box-shadow:2px 2px 10px rgba(0,0,0,0.05);"

    m1.markdown(f'<div style="{card_style}"><b>💰 Active PRINCIPAL</b><h3>{total_issued:,.0f} UGX</h3></div>', unsafe_allow_html=True)
    m2.markdown(f'<div style="{card_style}"><b>📈 EXPECTED INTEREST</b><h3>{total_interest_expected:,.0f} UGX</h3></div>', unsafe_allow_html=True)
    m3.markdown(f'<div style="{card_style.replace("#fff","#F0FFF4")}"><b>✅ TOTAL COLLECTED</b><h3>{total_collected:,.0f} UGX</h3></div>', unsafe_allow_html=True)
    m4.markdown(f'<div style="{card_style.replace("#fff","#FFF5F5")}"><b>🚨 OVERDUE FILES</b><h3>{overdue_count}</h3></div>', unsafe_allow_html=True)

    st.write("---")

    # --- 9. RECENT LOANS TABLE (Fixed Indentation) ---
    t1, t2 = st.columns(2)

    with t1:
        st.markdown(f"<h4 style='color:{brand_color};'>📝 Recent Portfolio Activity</h4>", unsafe_allow_html=True)

        if not Active_df.empty:
            recent = Active_df.sort_values("end_date_dt", ascending=False).head(5)
            rows_html = ""
            for idx, (i, r) in enumerate(recent.iterrows()):
                bg = "#F8FAFC" if idx % 2 == 0 else "#FFFFFF"
                rows_html += f"""
                <tr style="background:{bg}; border-bottom: 1px solid #eee;">
                    <td style="padding:8px;">{r.get('borrower_name', 'Unknown')}</td>
                    <td style="padding:8px; text-align:right; color:{brand_color}; font-weight:bold;">{r['principal_clean']:,.0f}</td>
                    <td style="padding:8px; text-align:center;">{r.get('status_clean', 'Active')}</td>
                    <td style="padding:8px; text-align:center;">{r['end_date_dt'].strftime('%d %b') if pd.notna(r['end_date_dt']) else '-'}</td>
                </tr>"""

            full_table_html = f"""
            <table style="width:100%; font-size:13px; border-collapse:collapse; font-family:sans-serif;">
                <tr style="background:{brand_color}; color:white;"><th style="padding:10px; text-align:left;">Borrower</th><th style="padding:10px; text-align:right;">Principal</th><th style="padding:10px; text-align:center;">Status</th><th style="padding:10px; text-align:center;">Due</th></tr>
                {rows_html}
            </table>"""
            st.components.v1.html(full_table_html, height=250)
        else:
            st.info("No Active loans found.")

    # --- 10. PAYMENTS TABLE (Fixed Indentation) ---
    with t2:
        st.markdown("<h4 style='color:#2E7D32;'>💸 Recent Cash Inflows</h4>", unsafe_allow_html=True)
        if pay_df is not None and not pay_df.empty:
            pay_df["amount_clean"] = safe_numeric(pay_df, ["amount", "amount_paid"])
            recent_pay = pay_df.sort_values("date", ascending=False).head(5)
            pay_rows = ""
            for idx, (i, r) in enumerate(recent_pay.iterrows()):
                bg = "#F0F8FF" if idx % 2 == 0 else "#FFFFFF"
                pay_rows += f"""<tr style="background:{bg}; border-bottom:1px solid #eee;"><td style="padding:8px;">{r.get('borrower', 'Unknown')}</td><td style="padding:8px; text-align:right; color:#2E7D32; font-weight:bold;">{r['amount_clean']:,.0f}</td><td style="padding:8px; text-align:center;">{r.get('date', '-')}</td></tr>"""
            
            pay_table_html = f'<table style="width:100%; font-size:13px; border-collapse:collapse; font-family:sans-serif;"><tr style="background:#2E7D32; color:white;"><th style="padding:10px; text-align:left;">Borrower</th><th style="padding:10px; text-align:right;">Amount</th><th style="padding:10px; text-align:center;">Date</th></tr>{pay_rows}</table>'
            st.components.v1.html(pay_table_html, height=250)
        else:
            st.write("No recent payments found.")

    # --- 11. CHARTS (Fixed Indentation) ---
    st.write("---")
    c1, c2 = st.columns(2)

    with c1:
        if not df_clean.empty:
            status_counts = df_clean["status_clean"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            fig = px.pie(status_counts, names="Status", values="Count", hole=0.5, color_discrete_sequence=["#4A90E2","#FF4B4B","#FFA500"])
            fig.update_layout(title="Loan Status Distribution", margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        if pay_df is not None and not pay_df.empty:
            pay_df["date_dt"] = pd.to_datetime(pay_df["date"], errors="coerce")
            inc = pay_df.groupby(pay_df["date_dt"].dt.strftime("%b %Y"))["amount_clean"].sum().reset_index()
            # ... Income/Expense Logic ...
            st.write("Monthly Cashflow View Active")
# ==========================================
# FINAL APP ROUTER (REActive & STABLE)
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
