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
            st.write("Start your lending journey.")
            # Registration form goes here

# --- 4. THE 5-PILLAR ROUTER ---
def main_interface():
    # Fetch branding dynamically
    tenant = conn.table("tenants").select("*").eq("id", st.session_state.tenant_id).single().execute()
    brand_color = tenant.data.get("theme_color", "#2B3F87")
    company = tenant.data.get("company_name", "LendFlow")

    # Horizontal Navigation Bar
    selected = option_menu(
        menu_title=None,
        options=["Dashboard", "Portfolio", "Treasury", "Admin", "Settings"],
        icons=["speedometer2", "briefcase", "cash-stack", "person-badge", "gear"],
        orientation="horizontal",
        styles={"nav-link-selected": {"background-color": brand_color}}
    )

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
