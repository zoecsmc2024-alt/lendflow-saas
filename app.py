import streamlit as st
from st_supabase_connection import SupabaseConnection
from streamlit_option_menu import option_menu
import pandas as pd

# --- 1. GLOBAL CONFIGURATION ---
st.set_page_config(page_title="LendFlow Africa | SaaS", layout="wide")

# Custom CSS for Navy/Baby Blue palette & Small Buttons
st.markdown("""
    <style>
        div.stButton > button { background-color: #2B3F87; color: white; border-radius: 5px; padding: 5px 15px; font-size: 14px; border: none; }
        div.stButton > button:hover { background-color: #1E2D61; color: white; border: none; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [data-baseweb="tab"] { background-color: #E1F5FE; border-radius: 5px 5px 0 0; padding: 5px 20px; color: #2B3F87; }
        .stTabs [aria-selected="true"] { background-color: #2B3F87 !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

# Connect to Supabase
conn = st.connection("supabase", type=SupabaseConnection)

# --- 2. SESSION STATE MANAGEMENT ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "tenant_id" not in st.session_state:
    st.session_state.tenant_id = None
if "user_email" not in st.session_state:
    st.session_state.user_email = ""

# --- 3. GATEKEEPER (LOGIN/SIGNUP) ---
def login_screen():
    st.markdown("<h1 style='text-align: center; color: #2B3F87;'>🚀 LendFlow Africa</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_log, tab_reg = st.tabs(["🔐 Staff Login", "🏢 Register Business"])
        with tab_log:
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            if st.button("Enter Workspace", use_container_width=True):
                # Temporary simulated login - We'll link this to Supabase Auth later
                res = conn.table("tenants").select("*").limit(1).execute()
                if res.data:
                    st.session_state.logged_in = True
                    st.session_state.tenant_id = res.data[0]['id']
                    st.session_state.user_email = email
                    st.rerun()
        with tab_reg:
            st.markdown("##### 🏢 Create your Lending Workspace")
            with st.form("register_form", clear_on_submit=True):
                new_biz = st.text_input("Business Name (e.g., Zoe Consults)")
                new_email = st.text_input("Admin Email")
                new_pwd = st.text_input("Password", type="password")
                
                agree = st.checkbox("I agree to the Privacy Policy & Terms")
                
                if st.form_submit_button("Start My Journey", type="primary"):
                    if not agree:
                        st.error("Please agree to the terms.")
                    elif not new_biz or not new_email or not new_pwd:
                        st.warning("All fields are required.")
                    else:
                        try:
                            # 1. CREATE THE BUSINESS (TENANT)
                            t_res = conn.table("tenants").insert({
                                "company_name": new_biz,
                                "theme_color": "#2B3F87"
                            }).execute()
                            t_id = t_res.data[0]['id']
                            
                            # 2. CREATE THE STAFF PROFILE (ADMIN)
                            # Note: We'll link this to Supabase Auth properly next, 
                            # but for now, we'll just save the profile.
                            conn.table("profiles").insert({
                                "tenant_id": t_id,
                                "email": new_email,
                                "full_name": "Business Owner",
                                "role": "Admin"
                            }).execute()
                            
                            st.success(f"🚀 {new_biz} is ready! Switch to 'Staff Login' to enter.")
                        except Exception as e:
                            st.error(f"Registration error: {e}")

# --- 4. THE 5-PILLAR ROUTER ---
def main_interface():
    # 1. Fetch branding
    tenant = conn.table("tenants").select("*").eq("id", st.session_state.tenant_id).single().execute()
    brand_color = tenant.data.get("theme_color", "#2B3F87")
    company = tenant.data.get("company_name", "LendFlow")

    # 2. TOP BAR LAYOUT (Company Name + Navigation + Logout)
    col_logo, col_nav, col_exit = st.columns([1, 4, 1])
    
    with col_logo:
        st.markdown(f"<h3 style='color: {brand_color}; margin-top: 5px;'>🚀 {company}</h3>", unsafe_allow_html=True)

    with col_nav:
        selected = option_menu(
            menu_title=None,
            options=["Dashboard", "Portfolio", "Treasury", "Admin", "Settings"],
            icons=["speedometer2", "briefcase", "cash-stack", "person-badge", "gear"],
            orientation="horizontal",
            styles={"nav-link-selected": {"background-color": brand_color}}
        )

    with col_exit:
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

    st.markdown("---") # Visual separator

    # 3. PAGE ROUTING (Rest of the code stays the same)
    if selected == "Dashboard":
        # ... your dashboard code ...

    # PAGE ROUTING
    if selected == "Dashboard":
        st.title(f"📊 {company} Overview")
        st.info("Coming soon: CEO Metrics & Performance Charts.")

    elif selected == "Portfolio":
        st.title("📂 Portfolio Management")
        t1, t2, t3 = st.tabs(["👥 Borrowers", "📑 Loans", "🛡️ Collateral"])
        with t1: st.write("### Manage Borrowers")
        with t2: st.write("### Loan Book")
        with t3: st.write("### Collateral Tracker")

    elif selected == "Treasury":
        st.title("💰 Treasury & Cashflow")
        t1, t2, t3 = st.tabs(["📥 Payments", "📤 Expenses", "☕ Petty Cash"])
        with t1: st.write("### Incoming Payments")
        with t2: st.write("### Operating Expenses")
        with t3: st.write("### Daily Petty Cash")

    elif selected == "Admin":
        st.title("🧾 Admin & Payroll")
        t1, t2, t3 = st.tabs(["👥 Staff", "💸 Payroll", "🏛️ Taxes (URA/NSSF)"])
        with t1: st.write("### Team Access Control")

    elif selected == "Settings":
        # We will drop our branding code here
        st.title("⚙️ Workspace Settings")

    # Logout in sidebar
    with st.sidebar:
        st.markdown(f"### {company}")
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

# --- 5. EXECUTION ---
if not st.session_state.logged_in:
    login_screen()
else:
    main_interface()
