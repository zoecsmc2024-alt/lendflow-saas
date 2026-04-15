# ==============================
# 0. ENTERPRISE SaaS CORE LAYER (UPGRADED)
# ==============================

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

st.set_page_config(layout="wide")

SESSION_TIMEOUT = 30

# ==============================
# 1. THEME ENGINE (ENTERPRISE SAFE)
# ==============================
def apply_master_theme():
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
        </style>
    """, unsafe_allow_html=True)


# ==============================
# 2. SUPABASE INIT (SINGLE SOURCE OF TRUTH)
# ==============================
try:
    SUPABASE_URL = st.secrets["supabase_url"]
    SUPABASE_KEY = st.secrets["supabase_key"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Supabase connection failed: {e}")
    st.stop()


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
        st.error("Session expired")
        st.stop()


# ==============================
# 4. STORAGE HELPERS (FIXED + SAFE)
# ==============================
def upload_image(file, bucket="collateral-photos"):
    try:
        require_tenant()
        tenant_id = get_tenant_id()

        file_name = f"{tenant_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.name}"

        supabase.storage.from_(bucket).upload(file_name, file.getvalue())
        return supabase.storage.from_(bucket).get_public_url(file_name)

    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None


# ==============================
# 5. DATA LAYER (MERGED - NO DUPLICATES)
# ==============================
@st.cache_data(ttl=600)
def get_cached_data(table_name):
    try:
        require_tenant()
        res = supabase.table(table_name)\
            .select("*")\
            .eq("tenant_id", get_tenant_id())\
            .execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.error(f"DB Error {table_name}: {e}")
        return pd.DataFrame()


def save_data(table_name, dataframe):
    try:
        require_tenant()
        if dataframe.empty:
            return False

        dataframe["tenant_id"] = get_tenant_id()
        supabase.table(table_name).upsert(dataframe.to_dict("records")).execute()
        st.cache_data.clear()
        return True

    except Exception as e:
        st.error(f"Save error: {e}")
        return False


# ==============================
# 6. AUTH CORE (UNIFIED - NO LOSS)
# ==============================
def authenticate(supabase, company_code, email, password):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if not res.user:
            return {"success": False, "error": "Invalid login"}

        profile = supabase.table("users")\
            .select("tenant_id, role, tenants(company_code, name)")\
            .eq("id", res.user.id)\
            .execute()

        if not profile.data:
            return {"success": False, "error": "No profile"}

        record = profile.data[0]
        tenant = record.get("tenants")

        if not tenant:
            return {"success": False, "error": "No tenant linked"}

        if tenant["company_code"].strip().upper() != company_code.strip().upper():
            return {"success": False, "error": "Invalid company code"}

        return {
            "success": True,
            "user_id": res.user.id,
            "tenant_id": record["tenant_id"],
            "role": record.get("role", "Admin"),
            "company": tenant.get("name")
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


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
    st.rerun()


# ==============================
# 8. SESSION SECURITY
# ==============================
def check_session_timeout():
    if not st.session_state.get("logged_in"):
        return

    last = st.session_state.get("last_activity", datetime.now())
    if datetime.now() - last > timedelta(minutes=SESSION_TIMEOUT):
        st.session_state.clear()
        st.warning("Session expired")
        st.rerun()

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
        if count >= MAX_ATTEMPTS and datetime.now() - last < timedelta(minutes=LOCKOUT_MINUTES):
            return False
    return True


def record_failed_attempt(email):
    attempts = st.session_state.setdefault("login_attempts", {})
    count, _ = attempts.get(email, (0, datetime.now()))
    attempts[email] = (count + 1, datetime.now())


# ==============================
# 10. CORE FIX: NO MORE DUPLICATES ANYWHERE
# ==============================
def tenant_filter(df):
    if df is None or df.empty:
        return df
    return df[df["tenant_id"] == get_tenant_id()].copy()


# ==============================
# 11. LOGIN PAGE (SAFE + CLEAN)
# ==============================
def login_page():
    col = st.columns(3)[1]

    with col:
        st.markdown("## 🔐 Login")

        company = st.text_input("Company Code").strip().upper()
        email = st.text_input("Email").strip().lower()
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            result = authenticate(supabase, company, email, password)

            if result["success"]:
                create_session(result)
                st.success("Welcome!")
            else:
                st.error(result["error"])


# ==============================
# 12. ROUTER
# ==============================
def run_auth_ui():
    if "view" not in st.session_state:
        st.session_state.view = "login"

    if st.session_state.view == "login":
        login_page()



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
        tenants_res = supabase.table("tenants")\
            .select("id, name, brand_color, logo_url")\
            .execute()

        tenant_map = {
            row['name']: row for row in tenants_res.data
        } if tenants_res.data else {}

    except Exception as e:
        st.error(f"Error fetching tenants: {e}")
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

            # Safe lookup of current tenant
            if current_tenant_id:
                for i, name in enumerate(options):
                    if str(tenant_map[name]['id']) == str(current_tenant_id):
                        default_index = i
                        break

            active_company_name = st.selectbox(
                "Business Portal:",
                options,
                index=default_index,
                key="sidebar_portal_select"
            )

            active_company = tenant_map.get(active_company_name, None)

            # ------------------------------
            # CRITICAL SYNC FIX (NO LOGIC LOSS)
            # ------------------------------
            if active_company:
                if str(st.session_state.get('tenant_id')) != str(active_company['id']):
                    st.session_state['tenant_id'] = active_company['id']
                    st.session_state['theme_color'] = active_company.get('brand_color', '#2B3F87')

                    # SAFE: reset cached tenant-dependent data
                    if hasattr(st, "cache_data"):
                        st.cache_data.clear()

                    st.rerun()
        else:
            st.warning("No tenants available.")
            st.stop()

        # ==============================
        # 3. LOGO RENDER (FIXED + SAFE)
        # ==============================
        _, col_mid, _ = st.columns([1, 2, 1])

        with col_mid:
            logo_val = active_company.get('logo_url') if active_company else None

            if logo_val and str(logo_val) not in ["0", "None", "null"]:

                import time

                # If full URL already exists
                if str(logo_val).startswith("http"):
                    final_logo_url = logo_val

                else:
                    # SAFE Supabase URL construction
                    try:
                        project_url = st.secrets["supabase_url"]
                        final_logo_url = f"{project_url}/storage/v1/object/public/company-logos/{logo_val}"
                    except Exception:
                        final_logo_url = None

                # Render logo safely with cache-busting
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

        try:
            default_ix = list(menu.keys()).index(current_p)
        except Exception:
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

            # FULL SESSION CLEANUP (SAFER THAN CLEAR)
            keys_to_keep = ["theme_color"]  # optional preservation

            for key in list(st.session_state.keys()):
                if key not in keys_to_keep:
                    del st.session_state[key]

            st.rerun()

    # ==============================
    # 6. PAGE RESOLUTION (SAFE PARSING)
    # ==============================
    try:
        final_page = selection.split(" ", 1)[1]
    except Exception:
        final_page = "Overview"

    st.session_state['current_page'] = final_page

    return final_page
        
# ==============================
# 12. BORROWERS MANAGEMENT PAGE (SAAS + DEBUG FIXED + ENTERPRISE UPGRADE)
# ==============================
import uuid 
import streamlit as st
import pandas as pd

def show_borrowers():
    brand_color = st.session_state.get("theme_color", "#2B3F87")
    st.markdown(f"<h2 style='color: {brand_color};'>👥 Borrowers Management</h2>", unsafe_allow_html=True)
    
    # ==============================
    # 🔐 SAAS TENANT CONTEXT (HARDENED)
    # ==============================
    current_tenant = st.session_state.get('tenant_id', None)

    if not current_tenant:
        st.error("🔐 Session expired. Please login again.")
        st.stop()

    # ==============================
    # 1. FETCH DATA
    # ==============================
    df = get_cached_data("borrowers")

    # ==============================
    # 🧠 ENTERPRISE SAFETY LAYER (ADDED)
    # Ensures ALL data is tenant-isolated even if backend leaks
    # ==============================
    if df is not None and not df.empty:
        if "tenant_id" in df.columns:
            df = df[df["tenant_id"].astype(str) == str(current_tenant)]
        else:
            df["tenant_id"] = current_tenant
    
    if df is None or df.empty:
        df = pd.DataFrame(columns=[
            "id", "name", "phone", "email", "address",
            "national_id", "next_of_kin", "status", "tenant_id"
        ])
    else:
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Ensure required columns exist (UNCHANGED LOGIC)
    for col in ["id", "name", "phone", "email", "address", "national_id", "next_of_kin", "status", "tenant_id"]:
        if col not in df.columns:
            df[col] = None

    # ==============================
    # COLUMN DETECTION (UNCHANGED LOGIC)
    # ==============================
    name_col = next((c for c in df.columns if 'name' in c or 'borrower' in c), "name")
    phone_col = next((c for c in df.columns if 'phone' in c), "phone")
    status_col = next((c for c in df.columns if 'status' in c), "status")

    tab_view, tab_add, tab_audit = st.tabs(["📑 View All", "➕ Add New", "⚙️ Audit & Manage"])

    # ==============================
    # TAB 1: VIEW (ENHANCED SAFETY ONLY)
    # ==============================
    with tab_view:
        col1, col2 = st.columns([3, 1]) 
        with col1:
            search = st.text_input("🔍 Search Name or Phone", key="bor_search").lower()
        with col2:
            status_filter = st.selectbox("Filter Status", ["All", "Active", "Inactive"], key="bor_status_filt")

        filtered_df = df.copy()
        
        if not filtered_df.empty:
            filtered_df[name_col] = filtered_df[name_col].astype(str)
            if phone_col in filtered_df.columns:
                filtered_df[phone_col] = filtered_df[phone_col].astype(str)
            
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
                for i, r in filtered_df.reset_index().iterrows():
                    bg_color = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                    
                    name_val = r.get(name_col, 'Unknown')
                    phone_val = r.get(phone_col, 'N/A')
                    email_val = r.get('email', 'N/A')
                    nok_val = r.get('next_of_kin', 'N/A')
                    stat_val = r.get(status_col, 'Active')
                    
                    rows_html += f"""<tr style="background-color: {bg_color};">
                        <td>{name_val}</td><td>{phone_val}</td>
                        <td>{email_val}</td><td>{nok_val}</td>
                        <td><span style="background:{brand_color};color:white;padding:4px 8px;border-radius:8px;">{stat_val}</span></td>
                    </tr>"""
                
                st.markdown(f"""
                    <div style="overflow-x:auto;">
                        <table style="width:100%;border-collapse:collapse;">
                            <thead>
                                <tr style="background:{brand_color};color:white;">
                                    <th>Name</th><th>Phone</th><th>Email</th><th>NOK</th><th>Status</th>
                                </tr>
                            </thead>
                            <tbody>{rows_html}</tbody>
                        </table>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.info("No borrowers found.")
        else:
            st.info("No borrowers registered yet.")

    # ==============================
    # TAB 2: ADD (ENTERPRISE FIX ADDED)
    # ==============================
    with tab_add:
        with st.form("add_borrower_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            
            name = c1.text_input("Full Name*")
            phone = c2.text_input("Phone Number*")

            email = st.text_input("Email (Optional)")
            address = st.text_input("Address (Optional)")
            national_id = st.text_input("National ID (Optional)")
            next_of_kin = st.text_input("Next of Kin (Optional)")

            if st.form_submit_button("🚀 Save Borrower Profile"):
                if name and phone:
                    new_entry = pd.DataFrame([{
                        "id": str(uuid.uuid4()),
                        "name": name,
                        "phone": phone,
                        "email": email,
                        "address": address,
                        "national_id": national_id,
                        "next_of_kin": next_of_kin,
                        "status": "Active",
                        "tenant_id": current_tenant
                    }])
                    
                    # ==============================
                    # 🔐 SAFER WRITE (DOES NOT MUTATE ORIGINAL DF)
                    # ==============================
                    updated_df = pd.concat([df, new_entry], ignore_index=True)

                    if save_data("borrowers", updated_df):
                        st.success("✅ Saved!")
                        st.cache_data.clear()  # ENTERPRISE FIX (cache sync)
                        st.rerun()
                else:
                    st.error("⚠️ Name and Phone are required.")

    # ==============================
    # TAB 3: AUDIT (HARDENED + SAFE LOAN JOIN)
    # ==============================
    with tab_audit:
        if not df.empty:
            target_name = st.selectbox("Select Borrower", df[name_col].tolist())
            b_data = df[df[name_col] == target_name].iloc[0]

            u_loans = get_cached_data("loans")

            # ==============================
            # 🔐 TENANT SAFE LOAN FILTER (ENHANCED)
            # ==============================
            if u_loans is not None and not u_loans.empty:
                if "tenant_id" in u_loans.columns:
                    u_loans = u_loans[u_loans["tenant_id"].astype(str) == str(current_tenant)]

                u_loans.columns = u_loans.columns.str.strip().str.lower().str.replace(" ", "_")

                loan_bor_ref = next((c for c in u_loans.columns if 'borrower' in c), None)
                
                if loan_bor_ref:
                    user_loans = u_loans[u_loans[loan_bor_ref].astype(str) == str(target_name)]

                    if not user_loans.empty:
                        st.metric("Loans", len(user_loans))
                        st.dataframe(user_loans)

            # ==============================
            # UPDATE (UNCHANGED LOGIC)
            # ==============================
            if st.button("💾 Update"):
                df.loc[df["id"] == b_data.get("id"), "name"] = target_name

                if save_data("borrowers", df):
                    st.success("✅ Updated")
                    st.cache_data.clear()
                    st.rerun()

            # ==============================
            # DELETE (ENTERPRISE SAFE FIX)
            # ==============================
            if st.button("🗑️ Delete"):
                df = df[df["id"] != b_data.get("id")]

                if save_data("borrowers", df):
                    st.success("✅ Deleted")
                    st.cache_data.clear()
                    st.rerun()

        else:
            st.info("💡 No borrowers found.")
# ==============================
# 🔐 SAAS TENANT CONTEXT (NEW)
# ==============================
def get_current_tenant():
    """
    Returns current tenant_id from session (SaaS isolation layer)
    """
    return st.session_state.get("tenant_id", "default_tenant")


# ==============================
# 🧠 DATABASE ADAPTER (REPLACES GOOGLE SHEETS)
# ==============================
def get_data(table_name):
    """
    Multi-tenant safe data fetch
    """
    tenant_id = get_current_tenant()
    df = get_cached_data(table_name)

    # ==============================
    # 🔐 ENTERPRISE SAFETY LAYER (ADDED)
    # Prevents cross-tenant leakage even if DB returns mixed data
    # ==============================
    if df is not None and not df.empty:
        if "tenant_id" in df.columns:
            df = df[df["tenant_id"].astype(str) == str(tenant_id)]
        else:
            # 🔥 Auto-migrate old data (no tenant_id → assign default)
            df["tenant_id"] = tenant_id

    return df


def save_data_saas(table_name, df):
    """
    Multi-tenant safe save
    """
    tenant_id = get_current_tenant()

    if "tenant_id" not in df.columns:
        df["tenant_id"] = tenant_id

    # ==============================
    # 🔐 HARD ENFORCEMENT (ADDED)
    # Ensures no row escapes tenant boundary
    # ==============================
    df["tenant_id"] = tenant_id

    return save_data(table_name, df)


# ==============================
# 13. LOANS MANAGEMENT PAGE (SAAS UPGRADE)
# ==============================
def show_loans():
    """
    Core engine for issuing and managing loan agreements.
    NOW SaaS-enabled with tenant isolation.
    """
    st.markdown("<h2 style='color: #0A192F;'>💵 Loans Management</h2>", unsafe_allow_html=True)
    
    tenant_id = get_current_tenant()

    # ==============================
    # 🧠 SESSION CACHE SAFETY (ADDED ONLY)
    # Prevents stale cross-tenant data in memory
    # ==============================
    if st.session_state.get("active_tenant") != tenant_id:
        st.session_state.pop("loans", None)
        st.session_state["active_tenant"] = tenant_id

    # ==============================
    # 1. LOAD & NORMALIZE DATA
    # ==============================
    if "loans" in st.session_state and not st.session_state.loans.empty:
        loans_df = st.session_state.loans.copy()
        loans_df = loans_df[loans_df.get("tenant_id", tenant_id) == tenant_id]
    else:
        loans_df = get_data("Loans")
        if loans_df is not None:
            st.session_state.loans = loans_df.copy()

    borrowers_df = get_data("Borrowers")
    
    if borrowers_df is not None and not borrowers_df.empty:
        borrowers_df.columns = [str(c).strip().replace(" ", "_") for c in borrowers_df.columns]

        # ==============================
        # 🔐 FIXED SAFETY FILTER (ADDED ONLY)
        # ==============================
        if "Status" in borrowers_df.columns:
            active_borrowers = borrowers_df[borrowers_df["Status"] == "Active"]
        elif "status" in borrowers_df.columns:
            active_borrowers = borrowers_df[borrowers_df["status"] == "Active"]
        else:
            active_borrowers = pd.DataFrame()
    else:
        active_borrowers = pd.DataFrame()
    
    if loans_df is None or loans_df.empty:
        loans_df = pd.DataFrame(columns=[
            "Loan_ID", "Borrower", "Principal", "Interest",
            "Total_Repayable", "Amount_Paid", "Balance",
            "Status", "Start_Date", "End_Date", "tenant_id"
        ])
    
    loans_df.columns = [str(col).strip().replace(" ", "_") for col in loans_df.columns]

    if "tenant_id" not in loans_df.columns:
        loans_df["tenant_id"] = tenant_id

    # ==============================
    # CLEAN NUMERIC (UNCHANGED LOGIC)
    # ==============================
    num_cols = ["Principal", "Interest", "Total_Repayable", "Amount_Paid", "Balance"]
    for col in num_cols:
        if col in loans_df.columns:
            loans_df[col] = pd.to_numeric(loans_df[col], errors='coerce').fillna(0)

    loans_df["Balance"] = loans_df["Total_Repayable"] - loans_df["Amount_Paid"]

    # ==============================
    # AUTO CLOSE ENGINE (UNCHANGED LOGIC)
    # ==============================
    if not loans_df.empty:
        loans_df["Balance"] = loans_df["Balance"].clip(lower=0)
        closed_mask = loans_df["Balance"] <= 0

        loans_df.loc[closed_mask, "Status"] = "Closed"
        loans_df.loc[closed_mask, "Balance"] = 0
        loans_df.loc[closed_mask, "Total_Repayable"] = loans_df.loc[closed_mask, "Amount_Paid"]

    tab_view, tab_add, tab_manage, tab_actions = st.tabs([
        "📑 Portfolio View", "➕ New Loan", "🛠️ Manage/Edit", "⚙️ Actions"
    ])

    # ==============================
    # TAB: NEW LOAN (UNCHANGED LOGIC + SAFE DISPLAY ONLY)
    # ==============================
    with tab_add:
        if active_borrowers.empty:
            st.info("💡 Tip: Activate a borrower in the 'Borrowers' section.")
        else:
            with st.form("loan_issue_form"):
                col1, col2 = st.columns(2)
                
                selected_borrower = col1.selectbox(
                    "Select Borrower",
                    active_borrowers.get("Name", active_borrowers.columns[0]).unique()
                )

                amount = col1.number_input("Principal Amount (UGX)", min_value=0, step=50000)
                date_issued = col1.date_input("Start Date", value=datetime.now())
                
                l_type = col2.selectbox("Loan Type", ["Business", "Personal", "Emergency", "Other"])
                interest_rate = col2.number_input("Monthly Interest Rate (%)", min_value=0.0, step=0.5)
                date_due = col2.date_input("Due Date", value=date_issued + timedelta(days=30))

                interest = (interest_rate / 100) * amount
                total_due = amount + interest

                if st.form_submit_button("🚀 Confirm & Issue Loan", use_container_width=True):
                    if amount > 0:
                        last_id = pd.to_numeric(loans_df["Loan_ID"], errors='coerce').max()
                        new_id = int(last_id + 1) if pd.notna(last_id) else 1
                        
                        new_loan = pd.DataFrame([{
                            "Loan_ID": new_id,
                            "Borrower": selected_borrower,
                            "Type": l_type,
                            "Principal": float(amount),
                            "Interest": float(interest),
                            "Total_Repayable": float(total_due),
                            "Amount_Paid": 0.0,
                            "Status": "Active",
                            "Start_Date": date_issued.strftime("%Y-%m-%d"),
                            "End_Date": date_due.strftime("%Y-%m-%d"),
                            "tenant_id": tenant_id
                        }])
                        
                        updated_df = pd.concat([loans_df, new_loan], ignore_index=True).fillna(0)

                        final_save = updated_df.copy()
                        final_save.columns = [c.replace("_", " ") for c in final_save.columns]
                        
                        if save_data_saas("Loans", final_save):
                            st.success(f"✅ Loan #{new_id} issued!")
                            st.rerun()

    # ==============================
    # TAB: MANAGE (UNCHANGED LOGIC + SAFETY ONLY)
    # ==============================
    with tab_manage:
        if loans_df.empty:
            st.info("No loans available to manage.")
        else:
            loans_df['display_name'] = loans_df.apply(
                lambda x: f"ID: {str(x['Loan_ID']).replace('.0', '')} - {x['Borrower']}", axis=1
            )

            selected_display = st.selectbox(
                "Select Loan", loans_df['display_name'].unique()
            )

            clean_id = selected_display.split(" - ")[0].replace("ID: ", "").strip()

            loan_to_edit = loans_df[
                loans_df["Loan_ID"].astype(str).str.replace(".0", "", regex=False) == clean_id
            ].iloc[0]

            with st.form("edit_loan_form"):
                new_principal = st.number_input("Principal", value=float(loan_to_edit['Principal']))
                
                if st.form_submit_button("💾 Save Changes"):
                    idx = loans_df[
                        loans_df["Loan_ID"].astype(str).str.replace(".0", "", regex=False) == clean_id
                    ].index[0]

                    loans_df.at[idx, 'Principal'] = new_principal

                    save_df = loans_df.drop(columns=['display_name'], errors='ignore').copy()
                    save_df.columns = [c.replace("_", " ") for c in save_df.columns]

                    if save_data_saas("Loans", save_df):
                        st.success("✅ Updated!")
                        st.rerun()

# ==============================
# 14. PAYMENTS & COLLECTIONS PAGE (ENTERPRISE SaaS - UPGRADED)
# ==============================

import random

# -------------------------------
# SAFE USER SERIALIZER
# -------------------------------
def get_user_identity():
    user = st.session_state.get("user", None)

    if user is None:
        return "system"

    if hasattr(user, "id"):
        return str(user.id)

    if hasattr(user, "email"):
        return str(user.email)

    return str(user)


# -------------------------------
# STATUS NORMALIZER
# -------------------------------
VALID_STATUSES = {"ACTIVE", "PENDING", "CLOSED", "OVERDUE", "BCF", "ROLLED_OVER"}

def normalize_status(status):
    if pd.isna(status):
        return "PENDING"
    cleaned = str(status).strip().upper().replace(" ", "_")
    return cleaned if cleaned in VALID_STATUSES else "PENDING"


# -------------------------------
# JSON SAFETY (CRITICAL FIX)
# -------------------------------
def make_json_safe(df):
    if df is None or df.empty:
        return df
    return df.applymap(
        lambda x: str(x)
        if not isinstance(x, (str, int, float, bool, type(None)))
        else x
    )


# -------------------------------
# SAFE SAVE WRAPPER (ENTERPRISE)
# -------------------------------
def save_data_safe(table, df):
    try:
        df = make_json_safe(df)
        data = df.to_dict(orient="records")
        supabase.table(table).upsert(data).execute()
        return True
    except Exception as e:
        st.error(f"Error saving to {table}: {e}")
        return False


# ==============================
# MAIN PAYMENTS MODULE
# ==============================
def show_payments():
    """
    Manages cash inflows. Includes payment posting,
    automatic loan status updates, and history logs.
    SaaS multi-tenant safe.
    """

    st.markdown("<h2 style='color: #2B3F87;'>💵 Payments Management</h2>", unsafe_allow_html=True)

    # -------------------------------
    # FETCH TENANT DATA (SAFE)
    # -------------------------------
    loans_df = get_cached_data("loans")
    payments_df = get_cached_data("payments")
    borrowers_df = get_cached_data("borrowers")

    # -------------------------------
    # SAFETY CHECKS
    # -------------------------------
    if loans_df is None or loans_df.empty:
        st.info("ℹ️ No loans found in the system.")
        return

    loans_df.columns = loans_df.columns.str.strip().str.lower().str.replace(" ", "_")

    if payments_df is not None and not payments_df.empty:
        payments_df.columns = payments_df.columns.str.strip().str.lower().str.replace(" ", "_")

    if borrowers_df is not None and not borrowers_df.empty:
        borrowers_df.columns = borrowers_df.columns.str.strip().str.lower().str.replace(" ", "_")
        bor_name_col = next((c for c in borrowers_df.columns if 'name' in c), "name")
        bor_map = dict(zip(borrowers_df['id'].astype(str), borrowers_df[bor_name_col]))
    else:
        bor_map = {}

    tab_new, tab_history, tab_manage = st.tabs([
        "➕ Record Payment", "📜 History & Trends", "⚙️ Edit/Delete"
    ])

    # ==============================
    # TAB 1: RECORD PAYMENT
    # ==============================
    with tab_new:

        active_loans = loans_df.copy()

        if "status" in active_loans.columns:
            active_loans = active_loans[
                active_loans["status"].astype(str).str.lower() != "closed"
            ]

        if active_loans.empty:
            st.success("🎉 All loans are currently cleared!")
            return

        active_loans["borrower_display"] = active_loans.get("borrower_id", pd.Series()).astype(str).map(bor_map).fillna("Unknown")

        loan_options = active_loans.apply(
            lambda x: f"ID: {x.get('id', '0')} | {x.get('loan_id_label', 'LN')} - {x.get('borrower_display', 'Unknown')}",
            axis=1
        ).tolist()

        selected_option = st.selectbox("Select Loan to Credit", loan_options, key="pay_sel")

        # -------------------------------
        # SAFE LOAN RESOLUTION
        # -------------------------------
        try:
            raw_id_str = selected_option.split(" | ")[0].replace("ID: ", "").strip()

            loan_df_filtered = active_loans[
                active_loans["id"].astype(str) == raw_id_str
            ]

            if loan_df_filtered.empty:
                st.error("Loan not found.")
                return

            loan = loan_df_filtered.iloc[0]

        except Exception as e:
            st.error(f"❌ Error identifying Loan: {e}")
            st.stop()

        # -------------------------------
        # CALCULATIONS
        # -------------------------------
        total_rep = float(loan.get("total_repayable", 0))
        paid_so_far = float(loan.get("amount_paid", 0))
        outstanding = total_rep - paid_so_far

        borrower_name = loan.get('borrower_display', 'Unknown')

        # -------------------------------
        # TENANT SAFETY
        # -------------------------------
        t_id = st.session_state.get('tenant_id')
        if not t_id:
            st.error("Tenant session missing.")
            return

        # -------------------------------
        # UI FORM
        # -------------------------------
        with st.form("payment_form", clear_on_submit=True):
            col_a, col_b, col_c = st.columns(3)

            pay_amount = col_a.number_input("Amount Received (UGX)", min_value=0, step=10000)
            pay_method = col_b.selectbox("Method", ["Mobile Money", "Cash", "Bank Transfer", "Cheque"])
            pay_date = col_c.date_input("Payment Date", value=datetime.now())

            if st.form_submit_button("✅ Post Payment", use_container_width=True):

                if pay_amount <= 0:
                    st.warning("Enter a valid amount.")
                    return

                try:
                    if pay_amount > outstanding:
                        st.warning("Overpayment adjusted.")
                        pay_amount = outstanding

                    receipt_no = f"RCPT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}"

                    # PAYMENT RECORD
                    new_payment = pd.DataFrame([{
                        "loan_id": str(loan["id"]),
                        "borrower": str(borrower_name),
                        "amount": float(pay_amount),
                        "date": pay_date.strftime("%Y-%m-%d"),
                        "method": str(pay_method),
                        "recorded_by": get_user_identity(),
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "receipt_no": receipt_no,
                        "tenant_id": str(t_id)
                    }])

                    # LOAN UPDATE
                    new_total_paid = paid_so_far + float(pay_amount)

                    new_status = "CLOSED" if new_total_paid >= (total_rep - 10) else normalize_status(loan.get("status", "ACTIVE"))

                    loan_update = pd.DataFrame([{
                        "id": loan["id"],
                        "amount_paid": float(new_total_paid),
                        "status": normalize_status(new_status),
                        "tenant_id": str(t_id),
                        "last_payment_date": pay_date.strftime("%Y-%m-%d")
                    }])

                    if save_data_safe("payments", new_payment) and save_data_safe("loans", loan_update):
                        st.success(f"Payment posted for {borrower_name}")

                        if new_status == "CLOSED":
                            st.balloons()

                        st.cache_data.clear()
                        st.rerun()

                except Exception as e:
                    st.error(f"Error: {e}")

    # ==============================
    # TAB 2: HISTORY
    # ==============================
    with tab_history:
        if payments_df is not None and not payments_df.empty:

            df_display = payments_df.copy()

            def get_level(amt):
                if amt >= 5000000:
                    return "🟢 Large"
                if amt >= 1000000:
                    return "🔵 Medium"
                return "⚪ Small"

            df_display["level"] = df_display["amount"].apply(get_level)

            df_display["amount"] = df_display["amount"].apply(lambda x: f"{x:,.0f}")

            st.dataframe(
                df_display.sort_values("date", ascending=False),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No payment history found.")

    # ==============================
    # TAB 3: EDIT / DELETE
    # ==============================
    with tab_manage:
        if payments_df is not None and not payments_df.empty:

            p_sel_id = st.selectbox("Select Receipt ID", payments_df["id"].unique())
            p_row = payments_df[payments_df["id"] == p_sel_id].iloc[0]

            with st.form("edit_payment"):
                new_amt = st.number_input("Amount", value=float(p_row["amount"]))
                new_date = st.date_input("Date", value=pd.to_datetime(p_row["date"]))

                if st.form_submit_button("Update"):
                    update_df = pd.DataFrame([{
                        "id": p_sel_id,
                        "amount": new_amt,
                        "date": new_date.strftime("%Y-%m-%d"),
                        "tenant_id": st.session_state.get("tenant_id")
                    }])

                    if save_data_safe("payments", update_df):
                        st.success("Updated successfully")
                        st.cache_data.clear()
                        st.rerun()

            st.markdown("---")

            if st.button("🗑️ Delete Receipt", type="primary"):
                try:
                    supabase.table("payments").delete().eq("id", p_sel_id).execute()
                    st.warning("Deleted")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")

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

    # ==============================
    # FETCH DATA (SAFE)
    # ==============================
    collateral_df = get_cached_data("collateral")
    loans_df = get_cached_data("loans")

    # ==============================
    # SAAS FILTER (HARDENED - NO BREAKS)
    # ==============================
    if collateral_df is None:
        collateral_df = pd.DataFrame()

    if loans_df is None:
        loans_df = pd.DataFrame()

    if not collateral_df.empty:
        if "tenant_id" in collateral_df.columns:
            collateral_df = collateral_df[
                collateral_df["tenant_id"].astype(str) == str(current_tenant)
            ]
        else:
            collateral_df["tenant_id"] = current_tenant

    if not loans_df.empty:
        if "tenant_id" in loans_df.columns:
            loans_df = loans_df[
                loans_df["tenant_id"].astype(str) == str(current_tenant)
            ]
        else:
            loans_df["tenant_id"] = current_tenant

    # ==============================
    # NORMALIZE LOANS COLUMNS (SAFE)
    # ==============================
    l_id_col, l_bor_col, l_stat_col = "id", "borrower", "status"

    if not loans_df.empty:
        loans_df.columns = (
            loans_df.columns.str.strip().str.lower().str.replace(" ", "_")
        )

        l_id_col = next((c for c in loans_df.columns if "id" in c), "id")
        l_bor_col = next((c for c in loans_df.columns if "borrower" in c or "name" in c), "borrower")
        l_stat_col = next((c for c in loans_df.columns if "status" in c), "status")

    # --- TABS ---
    tab_reg, tab_view = st.tabs(["➕ Register Asset", "📋 Inventory & Status"])

    # ==============================
    # TAB 1: REGISTER COLLATERAL
    # ==============================
    with tab_reg:

        if loans_df.empty:
            st.warning("⚠️ No loans found.")
        else:
            active_statuses = ["Active", "Overdue", "Rolled/Overdue", "Pending"]

            if l_stat_col not in loans_df.columns:
                st.error("Loan status column missing.")
                return

            available_loans = loans_df[
                loans_df[l_stat_col].astype(str).str.title().fillna("").isin(active_statuses)
            ].copy()

            if available_loans.empty:
                st.info("✅ No active loans.")
            else:
                with st.form("collateral_form", clear_on_submit=True):

                    c1, c2 = st.columns(2)

                    loan_options = []
                    loan_id_lookup = {}

                    for _, row in available_loans.iterrows():
                        loan_id_val = row.get(l_id_col, "UNKNOWN")
                        borrower_val = str(row.get(l_bor_col, "UNKNOWN"))

                        display_label = f"{borrower_val.upper()} ({str(loan_id_val)[:8]})"

                        loan_options.append(display_label)
                        loan_id_lookup[display_label] = loan_id_val

                    selected_label = c1.selectbox("Select Loan", options=loan_options)

                    asset_type = c2.selectbox(
                        "Asset Type",
                        ["Logbook (Car)", "Land Title", "Electronics", "House Deed", "Other"]
                    )

                    desc = st.text_input("Asset Description")
                    est_value = st.number_input("Estimated Value", min_value=0, step=100000)
                    uploaded_photo = st.file_uploader(
                        "Upload Asset Photo",
                        type=["jpg", "png", "jpeg"]
                    )

                    submit = st.form_submit_button("💾 Save & Secure Asset")

                if submit:

                    if not desc or est_value <= 0:
                        st.warning("Please fill all required fields.")
                    else:
                        try:
                            actual_loan_id = loan_id_lookup.get(selected_label)

                            if actual_loan_id is None:
                                st.error("Invalid loan selection.")
                            else:
                                clean_borrower_name = selected_label.split(" (")[0]

                                new_asset = pd.DataFrame([{
                                    "loan_id": actual_loan_id,
                                    "tenant_id": current_tenant,
                                    "borrower": clean_borrower_name,
                                    "type": asset_type,
                                    "description": desc,
                                    "value": float(est_value),
                                    "status": "Held",
                                    "date_added": datetime.now().strftime("%Y-%m-%d")
                                }])

                                if save_data("collateral", new_asset):
                                    st.success("✅ Asset saved successfully!")
                                    st.cache_data.clear()
                                    st.rerun()

                        except Exception as e:
                            st.error(f"❌ Error saving collateral: {e}")

    # ==============================
    # TAB 2: INVENTORY
    # ==============================
    with tab_view:

        if collateral_df.empty:
            st.info("💡 No assets yet.")
        else:
            collateral_df["value"] = pd.to_numeric(
                collateral_df.get("value", 0),
                errors='coerce'
            ).fillna(0)

            c_bor_col = next((c for c in collateral_df.columns if 'borrower' in c), "borrower")
            c_stat_col = next((c for c in collateral_df.columns if 'status' in c), "status")
            c_id_col = next((c for c in collateral_df.columns if 'id' in c), "id")

            total_val = collateral_df[
                ~collateral_df[c_stat_col].astype(str).str.lower().isin(["released"])
            ]["value"].sum()

            in_custody = collateral_df[
                collateral_df[c_stat_col].astype(str).str.lower().isin(["in custody", "held"])
            ].shape[0]

            m1, m2 = st.columns(2)
            m1.metric("Total Value", f"{total_val:,.0f}")
            m2.metric("Active Assets", in_custody)

            rows_html = ""
            for i, r in collateral_df.reset_index().iterrows():
                bg = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                display_id = str(r.get(c_id_col, ""))[:8]

                rows_html += f"""
                <tr style="background:{bg};">
                    <td>{display_id}</td>
                    <td>{r.get(c_bor_col, '')}</td>
                    <td>{r.get('type','')}</td>
                    <td>{r.get('description','')}</td>
                    <td>{float(r.get('value',0)):,.0f}</td>
                    <td>{r.get(c_stat_col,'')}</td>
                    <td>{r.get('date_added','')}</td>
                </tr>
                """

            st.markdown(f"<table>{rows_html}</table>", unsafe_allow_html=True)

            # ==============================
            # MANAGE COLLATERAL (SAFE FIXED)
            # ==============================
            with st.expander("⚙️ Manage Collateral Records"):

                manage_list = collateral_df.apply(
                    lambda x: f"{str(x.get(c_id_col,''))[:8]} | {x.get(c_bor_col,'')}",
                    axis=1
                ).tolist()

                selected_col = st.selectbox("Select Asset", manage_list)

                selected_idx = manage_list.index(selected_col)
                c_row = collateral_df.iloc[selected_idx]

                ce1, ce2 = st.columns(2)

                upd_desc = ce1.text_input(
                    "Description",
                    value=str(c_row.get("description", ""))
                )

                upd_val = ce1.number_input(
                    "Value",
                    value=float(c_row.get("value", 0))
                )

                status_opts = ["In Custody", "Released", "Disposed", "Held"]
                current_stat = str(c_row.get(c_stat_col, "Held")).title()

                if current_stat not in status_opts:
                    status_opts.append(current_stat)

                upd_stat = ce2.selectbox("Status", status_opts)

                if st.button("💾 Save Changes"):

                    update_df = pd.DataFrame([{
                        "id": c_row.get(c_id_col),
                        "description": upd_desc,
                        "value": upd_val,
                        "status": upd_stat,
                        "tenant_id": current_tenant
                    }])

                    if save_data("collateral", update_df):
                        st.success("✅ Updated successfully!")
                        st.cache_data.clear()
                        st.rerun()
            

# ==============================
# 17. ACTIVITY CALENDAR PAGE (SAAS + ENTERPRISE UPGRADE)
# ==============================

from streamlit_calendar import calendar
import pandas as pd
import streamlit as st

def show_calendar():
    st.markdown("<h2 style='color: #2B3F87;'>📅 Activity Calendar</h2>", unsafe_allow_html=True)
    
    # ==============================
    # 🔐 SAAS TENANT CONTEXT (ENHANCED SAFETY)
    # ==============================
    tenant_id = st.session_state.get("tenant_id", "default_tenant")

    # ==============================
    # 1. FETCH DATA (SAFETY WRAPPER ADDED)
    # ==============================
    try:
        loans_df = get_cached_data("Loans")  # keeps your logic
    except Exception:
        loans_df = pd.DataFrame()

    # ==============================
    # SAAS FILTER (HARDENED - NO LOGIC CHANGE)
    # ==============================
    if loans_df is not None and not loans_df.empty:
        if "tenant_id" in loans_df.columns:
            loans_df = loans_df[loans_df["tenant_id"] == tenant_id]
        else:
            loans_df["tenant_id"] = tenant_id

    # ==============================
    # EMPTY STATE (UNCHANGED LOGIC)
    # ==============================
    if loans_df is None or loans_df.empty:
        st.info("📅 Calendar is clear! No active loans to track.")
        return

    # ==============================
    # COLUMN NORMALIZATION (ENHANCED SAFETY ONLY)
    # ==============================
    loans_df.columns = (
        loans_df.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    # ==============================
    # SAFE COLUMN DETECTION (IMPROVED GUARDS ONLY)
    # ==============================
    l_id_col = next((c for c in loans_df.columns if 'id' in c), "id")
    l_bor_col = next((c for c in loans_df.columns if 'borrower' in c or 'name' in c or 'label' in c), "borrower_id")
    l_stat_col = next((c for c in loans_df.columns if 'status' in c), "status")
    l_end_col = next((c for c in loans_df.columns if 'end' in c or 'due' in c), "end_date")
    l_rev_col = next((c for c in loans_df.columns if 'repayable' in c or 'amount' in c), "total_repayable")

    # ==============================
    # SAFE COLUMN FALLBACKS (NO LOGIC REMOVED)
    # ==============================
    for col in [l_id_col, l_bor_col, l_stat_col, l_end_col, l_rev_col]:
        if col not in loans_df.columns:
            loans_df[col] = None

    # ==============================
    # TYPE STANDARDIZATION (HARDENED)
    # ==============================
    loans_df[l_end_col] = pd.to_datetime(loans_df[l_end_col], errors="coerce")
    loans_df[l_rev_col] = pd.to_numeric(loans_df[l_rev_col], errors="coerce").fillna(0)
    loans_df[l_bor_col] = loans_df[l_bor_col].astype(str).str.upper()

    today = pd.Timestamp.today().normalize()

    active_loans = loans_df[loans_df[l_stat_col].astype(str).str.lower() != "closed"].copy()

    # ==============================
    # CALENDAR EVENTS (UNCHANGED LOGIC + SAFETY)
    # ==============================
    calendar_events = []
    for _, r in active_loans.iterrows():
        if pd.notna(r[l_end_col]):
            try:
                is_overdue = r[l_end_col].date() < today.date()
            except Exception:
                is_overdue = False

            ev_color = "#FF4B4B" if is_overdue else "#4A90E2"

            calendar_events.append({
                "title": f"UGX {float(r[l_rev_col]):,.0f} - {r[l_bor_col]}",
                "start": r[l_end_col].strftime("%Y-%m-%d"),
                "end": r[l_end_col].strftime("%Y-%m-%d"),
                "color": ev_color,
                "allDay": True,
            })

    calendar_options = {
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek"
        },
        "initialView": "dayGridMonth",
        "selectable": True,
    }

    calendar(events=calendar_events, options=calendar_options, key="collection_cal")

    st.markdown("---")

    # ==============================
    # METRICS (SAFETY ENHANCED ONLY)
    # ==============================
    try:
        due_today_df = active_loans[active_loans[l_end_col].dt.date == today.date()]
        upcoming_df = active_loans[
            (active_loans[l_end_col] > today) & 
            (active_loans[l_end_col] <= today + pd.Timedelta(days=7))
        ]
        overdue_count = active_loans[active_loans[l_end_col] < today].shape[0]
    except Exception:
        due_today_df = pd.DataFrame()
        upcoming_df = pd.DataFrame()
        overdue_count = 0

    m1, m2, m3 = st.columns(3)

    m1.markdown(
        f"""<div style="background-color:#fff;padding:20px;border-radius:15px;border-left:5px solid #2B3F87;">
        <p style='margin:0;font-size:0.8em;color:grey;'>DUE TODAY</p><p style='margin:0;font-size:1.5em;font-weight:bold;'>{len(due_today_df)} Accounts</p></div>""",
        unsafe_allow_html=True
    )

    m2.markdown(
        f"""<div style="background-color:#F0F8FF;padding:20px;border-radius:15px;border-left:5px solid #2B3F87;">
        <p style='margin:0;font-size:0.8em;color:grey;'>UPCOMING</p><p style='margin:0;font-size:1.5em;font-weight:bold;'>{len(upcoming_df)} Accounts</p></div>""",
        unsafe_allow_html=True
    )

    m3.markdown(
        f"""<div style="background-color:#FFF5F5;padding:20px;border-radius:15px;border-left:5px solid #D32F2F;">
        <p style='margin:0;font-size:0.8em;color:grey;'>OVERDUE</p><p style='margin:0;font-size:1.5em;font-weight:bold;'>{overdue_count}</p></div>""",
        unsafe_allow_html=True
    )

    # ==============================
    # MASTER LOAN LEDGER (HARDENED ONLY)
    # ==============================
    st.markdown("### 🏢 Master Loan Ledger")

    if active_loans.empty:
        st.info("ℹ️ No loan records found.")
    else:
        df = active_loans.copy()

        def find_col(names):
            for col in df.columns:
                if any(n in col.lower() for n in names):
                    return col
            return None

        id_col = find_col(["id"])
        borrower_col = find_col(["borrower", "name"])
        amount_col = find_col(["amount", "principal"])
        status_col = find_col(["status"])
        due_col = find_col(["due", "end"])

        if not id_col or not borrower_col:
            st.error("❌ Required columns missing")
            st.stop()

        df[id_col] = df[id_col].astype(str)

        if amount_col:
            df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce").fillna(0)

        if due_col:
            df[due_col] = pd.to_datetime(df[due_col], errors="coerce")

        display_cols = {id_col: "ID", borrower_col: "Borrower"}

        if amount_col:
            display_cols[amount_col] = "Amount"
        if due_col:
            display_cols[due_col] = "Due Date"
        if status_col:
            display_cols[status_col] = "Status"

        view_df = df[list(display_cols.keys())].rename(columns=display_cols)

        if "Amount" in view_df.columns:
            view_df["Amount"] = view_df["Amount"].apply(lambda x: f"{x:,.0f}")

        if "Due Date" in view_df.columns:
            view_df["Due Date"] = pd.to_datetime(view_df["Due Date"], errors='coerce').dt.strftime("%Y-%m-%d")

        st.dataframe(view_df, use_container_width=True)

        if due_col:
            overdue_count_check = (df[due_col] < pd.Timestamp.now()).sum()

            if overdue_count_check > 0:
                st.warning(f"⚠️ {overdue_count_check} loan(s) overdue")
            else:
                st.success("✅ No overdue loans")                                                                                                                      
                                                                                                                                                                                                                                                                 
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
        df = get_cached_data("expenses")
    except Exception:
        df = pd.DataFrame()

    # ==============================
    # SAAS FILTER (UNCHANGED LOGIC + SAFETY)
    # ==============================
    if df is not None and not df.empty:
        if "tenant_id" in df.columns:
            df = df[df["tenant_id"] == current_tenant]
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
                            st.rerun()
                    except Exception as e:
                        st.error(f"🚨 Save failed: {e}")
                else:
                    st.error("⚠️ Provide amount & description.")

    # ==============================
    # TAB 2: VIEW (SAFE + CRASH PROTECTION)
    # ==============================
    with tab_view:
        if not df.empty:
            try:
                df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
                total_spent = df["amount"].sum()

                st.markdown(f"<h3>Total Spent: {total_spent:,.0f} UGX</h3>", unsafe_allow_html=True)

                cat_summary = df.groupby("category")["amount"].sum().reset_index()
                fig_exp = px.pie(cat_summary, names="category", values="amount", title="Expenses by Category")
                st.plotly_chart(fig_exp, use_container_width=True)

            except Exception:
                st.warning("⚠️ Unable to generate analytics due to data format issues.")
        else:
            st.info("💡 No expenses recorded.")

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
                                st.rerun()

                    st.divider()

                    if st.button("🗑️ Delete Selected Expense", type="secondary"):
                        df = df[df["id"] != exp_id]
                        final_df = df.drop(columns=['label'])
                        if save_data("expenses", final_df):
                            st.success("✅ Deleted!")
                            st.rerun()

            except Exception as e:
                st.error(f"🚨 Manage error: {e}")
# ==============================
# 13. LOANS MANAGEMENT PAGE (Luxe Edition + ENTERPRISE SAAS UPGRADE)
# ==============================

def show_loans():
    """
    Core engine for issuing and managing loan agreements.
    Features Midnight Blue branding, Start Date tracking, and formatted currency.
    (Upgraded for enterprise SaaS stability)
    """
    st.markdown("<h2 style='color: #0A192F;'>💵 Loans Management</h2>", unsafe_allow_html=True)

    # ==============================
    # 🔐 SAAS CONTEXT (HARDENED)
    # ==============================
    current_tenant = st.session_state.get("tenant_id")

    # ==============================
    # 1. LOAD & NORMALIZE DATA (SAFE WRAPPER)
    # ==============================
    try:
        if "loans" in st.session_state and not st.session_state.loans.empty:
            loans_df = st.session_state.loans.copy()
        else:
            loans_df = get_cached_data("Loans")

            if loans_df is not None:
                st.session_state.loans = loans_df.copy()
    except Exception:
        loans_df = pd.DataFrame()

    try:
        borrowers_df = get_cached_data("Borrowers")
    except Exception:
        borrowers_df = pd.DataFrame()

    # ==============================
    # BORROWER NORMALIZATION (UNCHANGED LOGIC + SAFETY)
    # ==============================
    if borrowers_df is not None and not borrowers_df.empty:
        borrowers_df.columns = [str(c).strip().replace(" ", "_") for c in borrowers_df.columns]
        try:
            active_borrowers = borrowers_df[
                borrowers_df["Status"].astype(str).str.lower() == "active"
            ]
        except Exception:
            active_borrowers = pd.DataFrame()
    else:
        active_borrowers = pd.DataFrame()

    # ==============================
    # EMPTY SAFE INIT (UNCHANGED)
    # ==============================
    if loans_df is None or loans_df.empty:
        loans_df = pd.DataFrame(columns=[
            "Loan_ID","Borrower","Principal","Interest",
            "Total_Repayable","Amount_Paid","Balance",
            "Status","Start_Date","End_Date"
        ])

    # ==============================
    # COLUMN NORMALIZATION (SAFE)
    # ==============================
    loans_df.columns = [str(col).strip().replace(" ", "_") for col in loans_df.columns]

    # ==============================
    # 🔐 MULTI-TENANT FIX (ENHANCED SAFETY)
    # ==============================
    if "tenant_id" in loans_df.columns:
        try:
            loans_df = loans_df[
                loans_df["tenant_id"].astype(str) == str(current_tenant)
            ]
        except Exception:
            pass

    # ==============================
    # NUMERIC CLEANING (HARDENED)
    # ==============================
    num_cols = ["Principal","Interest","Total_Repayable","Amount_Paid","Balance"]

    for col in num_cols:
        if col in loans_df.columns:
            loans_df[col] = pd.to_numeric(loans_df[col], errors="coerce").fillna(0)

    loans_df["Balance"] = loans_df["Total_Repayable"] - loans_df["Amount_Paid"]

    # ==============================
    # AUTO CLOSE ENGINE (UNCHANGED LOGIC + SAFE GUARD)
    # ==============================
    if not loans_df.empty:
        loans_df["Balance"] = loans_df["Balance"].clip(lower=0)

        try:
            closed_mask = loans_df["Balance"] <= 0
            loans_df.loc[closed_mask, "Status"] = "Closed"
            loans_df.loc[closed_mask, "Balance"] = 0
        except Exception:
            pass

    # ==============================
    # TABS (UNCHANGED)
    # ==============================
    tab_view, tab_add, tab_manage, tab_actions = st.tabs([
        "📑 Portfolio View","➕ New Loan","🛠️ Manage/Edit","⚙️ Actions"
    ])

    # ==============================
    # TAB VIEW (SAFE WRAPPER ONLY)
    # ==============================
    with tab_view:
        if not loans_df.empty:
            display_df = loans_df.copy()

            display_df["Loan_ID"] = display_df["Loan_ID"].astype(str).str.replace(".0","",regex=False)

            active_view = display_df.copy()

            if not active_view.empty:
                sel_id = st.selectbox(
                    "🔍 Select Loan to Inspect",
                    active_view["Loan_ID"].unique()
                )

                loan_history = active_view[
                    active_view["Loan_ID"].astype(str) == str(sel_id)
                ]

                if not loan_history.empty:
                    latest_info = loan_history.sort_values("Start_Date").iloc[-1]

                    rec_val = float(latest_info.get("Amount_Paid",0))
                    out_val = float(latest_info.get("Balance",0))
                    stat_val = str(latest_info.get("Status","Active")).upper()
                else:
                    rec_val, out_val, stat_val = 0,0,"N/A"

                if stat_val == "CLOSED":
                    out_val = 0
        else:
            st.info("📭 No loan records available.")

    # ==============================
    # TAB MANAGE (HARDENED ONLY)
    # ==============================
    with tab_manage:
        if loans_df.empty:
            st.info("No loans available to manage.")
        else:
            loans_df["display_name"] = loans_df.apply(
                lambda x: f"ID: {str(x['Loan_ID']).replace('.0','')} - {x['Borrower']}",
                axis=1
            )

            selected_display = st.selectbox(
                "Select Loan to Manage/Edit",
                loans_df["display_name"].unique()
            )

            clean_id = selected_display.split(" - ")[0].replace("ID: ","").strip()

            try:
                match = loans_df[
                    loans_df["Loan_ID"].astype(str) == str(clean_id)
                ]
            except Exception:
                match = pd.DataFrame()

            if not match.empty:
                loan_to_edit = match.iloc[0]
            else:
                st.error("Loan not found")
                return

            st.markdown(f"#### 🛠️ Edit Loan #{clean_id}")

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
    # 🔐 SAFETY CHECK (NEW - SAAS HARD GUARD)
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

    # 🔐 SaaS FIX: isolate tenant
    if "tenant_id" in df.columns:
        df = df[df["tenant_id"].astype(str) == str(current_tenant)]
    else:
        df["tenant_id"] = current_tenant

    # ==============================
    # 🧠 COLUMN NORMALIZATION (NEW - PREVENT BREAKS)
    # ==============================
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    def run_manual_sync_calculations(basic, arrears, absent_deduct, advance, other):
        basic = float(basic or 0)
        arrears = float(arrears or 0)
        absent_deduct = float(absent_deduct or 0)
        advance = float(advance or 0)
        other = float(other or 0)

        gross = (basic + arrears) - absent_deduct

        lst = 100000 / 12 if gross > 1000000 else 0

        n5, n10 = gross * 0.05, gross * 0.10
        n15 = n5 + n10

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
                        st.rerun()

    with tab_logs:
        if not df.empty:
            def fm(x):
                try:
                    return f"{int(float(x)):,}"
                except:
                    return "0"

            rows_html = ""

            for i, r in df.iterrows():
                rows_html += f"""
                <tr>
                    <td style='text-align:center;border:1px solid #ddd;padding:10px;'>{i+1}</td>
                    <td style='border:1px solid #ddd;padding:10px;'><b>{r.get('employee','')}</b><br><small>{r.get('designation','-')}</small></td>
                    <td style='text-align:right;border:1px solid #ddd;padding:10px;'>{fm(r.get('arrears',0))}</td>
                    <td style='text-align:right;border:1px solid #ddd;padding:10px;'>{fm(r.get('basic_salary',0))}</td>
                    <td style='text-align:right;border:1px solid #ddd;padding:10px;font-weight:bold;'>{fm(r.get('gross_salary',0))}</td>
                    <td style='text-align:right;border:1px solid #ddd;padding:10px;'>{fm(r.get('paye',0))}</td>
                    <td style='text-align:right;border:1px solid #ddd;padding:10px;'>{fm(r.get('nssf_5',0))}</td>
                    <td style='text-align:right;border:1px solid #ddd;padding:10px;background:#E3F2FD;font-weight:bold;'>{fm(r.get('net_pay',0))}</td>
                    <td style='text-align:right;border:1px solid #ddd;padding:10px;background:#FFF9C4;'>{fm(r.get('nssf_10',0))}</td>
                    <td style='text-align:right;border:1px solid #ddd;padding:10px;background:#FFF9C4;font-weight:bold;'>{fm(r.get('nssf_15',0))}</td>
                </tr>
                """

            total_net = df["net_pay"].sum()

            rows_html += f"""
            <tr style="background:#2B3F87;color:white;font-weight:bold;">
                <td colspan="7" style="text-align:center;padding:12px;">GRAND TOTALS</td>
                <td style="text-align:right;padding:12px;">{fm(total_net)}</td>
                <td colspan="2"></td>
            </tr>
            """

            if st.button("📥 Print PDF", key="print_pay_btn"):
                st.components.v1.html("<script>window.print();</script>", height=0)

            st.components.v1.html(f"<table>{rows_html}</table>", height=600, scrolling=True)

            # DELETE SAFE FIX
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
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete failed: {e}")


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
            fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend_title="")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No transaction history for trend analysis.")

    with col_right:
        st.write("**🛡️ Portfolio Weight (Top 5)**")

        top_borrowers = loans.groupby("borrower")["principal"].sum().sort_values(ascending=False).head(5).reset_index()

        fig_pie = px.pie(
            top_borrowers,
            names="borrower",
            values="principal",
            hole=0.5,
            color_discrete_sequence=px.colors.sequential.GnBu_r
        )
        fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', showlegend=True)
        st.plotly_chart(fig_pie, use_container_width=True)

    # ==============================
    # 6. RISK INDICATOR (PAR % FIXED SAFETY)
    # ==============================
    st.markdown("---")
    st.subheader("🚨 Risk Assessment")

    loans = loans.copy()
    loans["end_date"] = pd.to_datetime(loans.get("end_date", pd.NaT), errors="coerce")
    loans["status"] = loans.get("status", "").astype(str)

    overdue_mask = (
        loans["status"].isin(["Overdue", "Rolled/Overdue", "Pending"]) &
        (loans["end_date"] < pd.Timestamp.today())
    )

    overdue_val = pd.to_numeric(loans.loc[overdue_mask, "principal"], errors="coerce").fillna(0).sum()
    risk_percent = (overdue_val / l_amt * 100) if l_amt > 0 else 0

    r1, r2 = st.columns([2, 1])

    with r1:
        st.write(f"Your Portfolio at Risk (PAR) is **{risk_percent:.1f}%**.")
        st.progress(min(float(risk_percent) / 100, 1.0))
        st.write(f"Total Overdue Principal: **{overdue_val:,.0f} UGX**")

    with r2:
        if risk_percent < 10:
            st.success("✅ Healthy Portfolio")
        elif risk_percent < 25:
            st.warning("⚠️ Moderate Risk")
        else:
            st.error("🆘 Critical Risk Level")

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
        st.info("💡 Your system is clear! No active loans found.")
        return

    # ==============================
    # 🔐 SAAS SAFETY + NORMALIZATION LAYER (ADDED ONLY)
    # ==============================
    loans_df.columns = loans_df.columns.str.strip().str.lower().str.replace(" ", "_")

    if payments_df is not None and not payments_df.empty:
        payments_df.columns = payments_df.columns.str.strip().str.lower().str.replace(" ", "_")

    current_tenant = st.session_state.get("tenant_id", "default_tenant")

    # ensure tenant safety (non-destructive)
    if "tenant_id" in loans_df.columns:
        loans_df = loans_df[loans_df["tenant_id"].astype(str) == str(current_tenant)]

    # ==============================
    # BORROWER RESOLUTION (UNCHANGED LOGIC + SAFE EXTENSION)
    # ==============================
    borrowers_df = get_cached_data("borrowers")
    bor_map = {}

    if borrowers_df is not None and not borrowers_df.empty:
        borrowers_df.columns = borrowers_df.columns.str.strip().str.lower().str.replace(" ", "_")
        bor_name_col = next((c for c in borrowers_df.columns if "name" in c), "name")
        bor_map = dict(zip(borrowers_df["id"].astype(str), borrowers_df[bor_name_col]))

    if "borrower" not in loans_df.columns:
        loans_df["borrower"] = loans_df["borrower_id"].astype(str).map(bor_map).fillna("Unknown")

    # ==============================
    # SELECTION LOGIC (UNCHANGED)
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
    # BALANCE CALCULATIONS (UNCHANGED)
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
    # LEDGER BUILD (UNCHANGED)
    # ==============================
    ledger_data = []

    ledger_data.append({
        "Date": loan_info.get("start_date", "-"),
        "Description": "Initial Loan Disbursement",
        "Debit": current_p,
        "Credit": 0,
        "Balance": current_p
    })

    if interest_amt > 0:
        ledger_data.append({
            "Date": loan_info.get("start_date", "-"),
            "Description": "➕ Interest Charged",
            "Debit": interest_amt,
            "Credit": 0,
            "Balance": current_p + interest_amt
        })

    # ==============================
    # PAYMENTS SAFETY LAYER (ADDED ONLY)
    # ==============================
    if payments_df is not None and not payments_df.empty:
        rel_pay = payments_df.copy()

        if "loan_id" in rel_pay.columns:
            rel_pay = rel_pay[rel_pay["loan_id"] == raw_id]

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

    # Render table (UNCHANGED)
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
    # PRINTABLE STATEMENT (UNCHANGED LOGIC + SAFE EXTENSIONS)
    # ==============================
    st.markdown("---")

    if st.button("✨ Preview Consolidated Statement", use_container_width=True):

        borrowers_df = get_cached_data("borrowers")

        current_b_name = loan_info.get("borrower", loan_info.get("borrower_id", "Unknown"))

        b_details = {}
        if borrowers_df is not None and not borrowers_df.empty:
            borrowers_df.columns = borrowers_df.columns.str.strip().str.lower().str.replace(" ", "_")
            b_data = borrowers_df[borrowers_df["id"].astype(str) == str(loan_info.get("borrower_id"))]
            b_details = b_data.iloc[0] if not b_data.empty else {}

        navy_blue, baby_blue = "#000080", "#E1F5FE"

        html_statement = f"""
        <div id="printable-area" style="font-family: Arial, sans-serif; padding: 25px; border: 1px solid #eee; background: white; color: #333;">
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

        client_loans = loans_df[loans_df["borrower"] == current_b_name] if "borrower" in loans_df.columns else loans_df[loans_df["borrower_id"].astype(str) == str(loan_info["borrower_id"])]

        for _, l_row in client_loans.iterrows():
            l_id = l_row['id']
            p, i = float(l_row.get('principal', 0)), float(l_row.get('interest', 0))

            l_pay = 0
            if payments_df is not None and not payments_df.empty:
                l_pay = payments_df[payments_df["loan_id"] == l_id]["amount"].sum()

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

import streamlit as st
import time

def show_settings():
    """
    Manages tenant identity and UI branding.
    Only displays when the 'Settings' page is selected.
    """

    # ==============================
    # 🔐 TENANT SAFETY LAYER (ADDED)
    # ==============================
    tenant_id = st.session_state.get("tenant_id")

    if not tenant_id:
        st.warning("⚠️ No active tenant detected. Please log in.")
        return

    # ==============================
    # 1. FETCH TENANT DATA (SAFE + HARDENED)
    # ==============================
    try:
        tenant_resp = supabase.table("tenants").select("*").eq("id", tenant_id).execute()

        if not tenant_resp.data:
            st.error("❌ Business profile not found.")
            return

        active_company = tenant_resp.data[0]

    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return

    # ==============================
    # BRANDING FALLBACK SAFETY (ADDED)
    # ==============================
    brand_color = st.session_state.get(
        "theme_color",
        active_company.get("brand_color", "#2B3F87")
    )

    st.markdown(
        f"<h2 style='color: {brand_color};'>⚙️ Portal Settings & Branding</h2>",
        unsafe_allow_html=True
    )

    # --- BUSINESS IDENTITY SECTION ---
    st.subheader("🏢 Business Identity")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(f"**Current Business Name:** {active_company.get('name', 'Unknown')}")

        new_color = st.color_picker(
            "🎨 Change Brand Color",
            active_company.get('brand_color', '#2B3F87'),
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

        logo_url = active_company.get("logo_url")

        # ==============================
        # LOGO DISPLAY SAFETY (ADDED)
        # ==============================
        if logo_url:
            try:
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
        # LOGO UPLOAD SAFETY (HARDENED)
        # ==============================
        if logo_file:
            try:
                bucket_name = "company-logos"
                file_path = f"logos/{active_company.get('id')}_logo.png"

                supabase.storage.from_(bucket_name).upload(
                    path=file_path,
                    file=logo_file.getvalue(),
                    file_options={
                        "x-upsert": "true",
                        "content-type": "image/png"
                    }
                )

                public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
                updated_data["logo_url"] = public_url

            except Exception as e:
                st.error(f"❌ Storage Error: {str(e)}")
                st.stop()

        # ==============================
        # DATABASE UPDATE (SAFE + UNCHANGED LOGIC)
        # ==============================
        try:
            supabase.table("tenants").update(updated_data).eq("id", active_company.get("id")).execute()

            st.session_state["theme_color"] = new_color

            st.success("✅ Branding updated successfully!")
            time.sleep(1)
            st.rerun()

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
    Upgraded: performance layer, safer finance engine, SaaS-safe computation.
    """
    brand_color = get_active_color()
    st.markdown(f"<h2 style='color: {brand_color};'>📊 Financial Dashboard</h2>", unsafe_allow_html=True)

    # --- 1. LOAD DATA ---
    df = get_cached_data("loans")
    pay_df = get_cached_data("payments")
    exp_df = get_cached_data("expenses") 
    bor_df = get_cached_data("borrowers")

    if df is None or df.empty:
        st.info("👋 Welcome! Start by adding your first borrower or loan in the sidebar.")
        st.stop()

    # --- 2. SAFE COLUMN STANDARDIZATION ---
    def normalize(d):
        if d is not None and not d.empty:
            d.columns = d.columns.str.strip().str.lower().str.replace(" ", "_")
        return d

    df = normalize(df)
    pay_df = normalize(pay_df)
    exp_df = normalize(exp_df)
    bor_df = normalize(bor_df)

    df_clean = df.copy()

    # --- 3. SAFE UTILS (UPGRADE ENGINE) ---
    def safe_numeric(df, col_list):
        for col in col_list:
            if df is not None and col in df.columns:
                return pd.to_numeric(df[col], errors="coerce").fillna(0)
        return pd.Series(0, index=df.index if df is not None else [])

    def safe_date(df, col_list):
        for col in col_list:
            if df is not None and col in df.columns:
                return pd.to_datetime(df[col], errors="coerce")
        return pd.NaT

    # --- 4. BORROWER MAPPING (OPTIMIZED) ---
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

    # --- 5. FINANCIAL ENGINE (UPGRADED SAFE CALCS) ---
    df_clean["principal_clean"] = safe_numeric(df_clean, ["principal"])
    df_clean["interest_clean"] = safe_numeric(df_clean, ["interest"])
    df_clean["paid_clean"] = (
        safe_numeric(df_clean, ["paid"]) +
        safe_numeric(df_clean, ["repaid"]) +
        safe_numeric(df_clean, ["amount_paid"])
    )

    stat_col = next((c for c in df_clean.columns if "status" in c), None)
    df_clean["status_clean"] = df_clean[stat_col].astype(str).str.title() if stat_col else "Active"

    date_col = next((c for c in df_clean.columns if "end" in c or "due" in c or "date" in c), None)
    df_clean["end_date_dt"] = safe_date(df_clean, ["end_date", "due_date", "date"])

    # --- 6. PRE-FILTER ENGINE (FAST PERFORMANCE UPGRADE) ---
    today = pd.Timestamp.now().normalize()

    active_statuses = ["Active", "Overdue", "Rolled/Overdue"]
    active_df = df_clean[df_clean["status_clean"].isin(active_statuses)].copy()

    overdue_df = active_df[active_df["end_date_dt"] < today]

    # --- 7. CORE METRICS ---
    total_issued = active_df["principal_clean"].sum()
    total_interest_expected = active_df["interest_clean"].sum()
    total_collected = df_clean["paid_clean"].sum()
    overdue_count = len(overdue_df)

    # --- 8. DISPLAY METRICS ---
    m1, m2, m3, m4 = st.columns(4)
    style = f"background:#fff;padding:20px;border-radius:15px;border-left:5px solid {brand_color};box-shadow:2px 2px 10px rgba(0,0,0,0.05);"

    m1.markdown(f'<div style="{style}"><b>💰 ACTIVE PRINCIPAL</b><h3>{total_issued:,.0f} UGX</h3></div>', unsafe_allow_html=True)
    m2.markdown(f'<div style="{style}"><b>📈 EXPECTED INTEREST</b><h3>{total_interest_expected:,.0f} UGX</h3></div>', unsafe_allow_html=True)
    m3.markdown(f'<div style="{style.replace("#fff","#F0FFF4")}"><b>✅ TOTAL COLLECTED</b><h3>{total_collected:,.0f} UGX</h3></div>', unsafe_allow_html=True)
    m4.markdown(f'<div style="{style.replace("#fff","#FFF5F5")}"><b>🚨 OVERDUE FILES</b><h3>{overdue_count}</h3></div>', unsafe_allow_html=True)

    st.write("---")

    # --- 9. RECENT LOANS TABLE ---
    t1, t2 = st.columns(2)

    with t1:
        st.markdown(f"<h4 style='color:{brand_color};'>📝 Recent Portfolio Activity</h4>", unsafe_allow_html=True)

        if not active_df.empty:
            recent = active_df.sort_values("end_date_dt", ascending=False).head(5)
            rows = ""

            for i, r in recent.iterrows():
                bg = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
                rows += f"""
                <tr style="background:{bg}">
                    <td>{r['borrower_name']}</td>
                    <td style="text-align:right;color:{brand_color};font-weight:bold;">
                        {r['principal_clean']:,.0f}
                    </td>
                    <td style="text-align:center;">{r['status_clean']}</td>
                    <td style="text-align:center;">
                        {r['end_date_dt'].strftime('%d %b') if pd.notna(r['end_date_dt']) else '-'}
                    </td>
                </tr>
                """

            st.markdown(f"""
            <table style="width:100%;font-size:12px;border-collapse:collapse">
                <thead>
                    <tr style="background:{brand_color};color:white;">
                        <th>Borrower</th><th>Principal</th><th>Status</th><th>Due</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
            """, unsafe_allow_html=True)

    # --- 10. PAYMENTS TABLE (SAFE) ---
    with t2:
        st.markdown("<h4 style='color:#2E7D32;'>💸 Recent Cash Inflows</h4>", unsafe_allow_html=True)

        if pay_df is not None and not pay_df.empty:
            pay_df["amount_clean"] = pd.to_numeric(pay_df.get("amount"), errors="coerce").fillna(0)

            recent_pay = pay_df.sort_values("date", ascending=False).head(5)

            pay_rows = ""
            for i, r in recent_pay.iterrows():
                bg = "#F0F8FF" if i % 2 == 0 else "#FFFFFF"
                pay_rows += f"""
                <tr style="background:{bg}">
                    <td>{r.get('borrower', 'Unknown')}</td>
                    <td style="text-align:right;color:green;font-weight:bold;">
                        {r['amount_clean']:,.0f}
                    </td>
                    <td style="text-align:center;">
                        {pd.to_datetime(r.get('date')).strftime('%d %b') if pd.notna(r.get('date')) else '-'}
                    </td>
                </tr>
                """

            st.markdown(f"""
            <table style="width:100%;font-size:12px;border-collapse:collapse">
                <thead>
                    <tr style="background:#2E7D32;color:white;">
                        <th>Borrower</th><th>Amount</th><th>Date</th>
                    </tr>
                </thead>
                <tbody>{pay_rows}</tbody>
            </table>
            """, unsafe_allow_html=True)

    # --- 11. CHARTS (SAFE MERGE FIX) ---
    st.write("---")
    c1, c2 = st.columns(2)

    with c1:
        if not df_clean.empty:
            status_counts = df_clean["status_clean"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]

            fig = px.pie(status_counts, names="Status", values="Count",
                         hole=0.5, color_discrete_sequence=["#4A90E2","#FF4B4B","#FFA500"])
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        if pay_df is not None and not pay_df.empty:
            pay_df["date"] = pd.to_datetime(pay_df.get("date"), errors="coerce")
            inc = pay_df.groupby(pay_df["date"].dt.strftime("%b %Y"))["amount_clean"].sum().reset_index()

            if exp_df is not None and not exp_df.empty:
                exp_df["date"] = pd.to_datetime(exp_df.get("date"), errors="coerce")
                exp_df["amount_clean"] = pd.to_numeric(exp_df.get("amount"), errors="coerce").fillna(0)
                exp = exp_df.groupby(exp_df["date"].dt.strftime("%b %Y"))["amount_clean"].sum().reset_index()
            else:
                exp = pd.DataFrame(columns=["date","amount_clean"])

            merged = pd.merge(inc, exp, on="date", how="outer").fillna(0)
            merged.columns = ["Month","Income","Expenses"]

            fig2 = px.bar(merged, x="Month", y=["Income","Expenses"],
                          barmode="group",
                          color_discrete_map={"Income":"#2E7D32","Expenses":"#FF4B4B"})
            st.plotly_chart(fig2, use_container_width=True)
# ==========================================
# FINAL APP ROUTER (REACTIVE + SAAS STABLE + THEME SAFE)
# ==========================================

import streamlit as st

if __name__ == "__main__":

    # ==============================
    # 0. SAFE DEFAULTS (FIRST LOAD)
    # ==============================
    if "theme_color" not in st.session_state:
        st.session_state["theme_color"] = "#1E3A8A"

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    try:
        # ==============================
        # 1. AUTH FLOW (UNAUTHENTICATED)
        # ==============================
        if not st.session_state.get("logged_in"):

            apply_master_theme()
            def run_auth_ui(supabase_client):
            st.stop()

        # ==============================
        # 2. AUTHENTICATED SESSION SAFETY
        # ==============================
        check_session_timeout()

        # ==============================
        # 3. APPLY THEME EARLY (CRITICAL FIX)
        # Ensures sidebar + pages inherit color correctly
        # ==============================
        apply_master_theme()

        # ==============================
        # 4. SIDEBAR NAVIGATION
        # ==============================
        page = render_sidebar()

        # ==============================
        # 5. PAGE ROUTER (MAIN CONTENT)
        # ==============================
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

        elif page == "Payments":
            show_payments()

        elif page == "Expenses":
            show_expenses()

        elif page == "Petty Cash":
            show_petty_cash()

        elif page == "Payroll":
            show_payroll()

        elif page == "Reports":
            show_reports()

        else:
            st.info(f"📦 The '{page}' module is coming online soon.")

    except Exception as e:
        st.error("🚨 Application Error")
        st.exception(e)
