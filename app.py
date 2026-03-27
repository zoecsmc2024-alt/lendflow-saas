import streamlit as st
from st_supabase_connection import SupabaseConnection
from streamlit_option_menu import option_menu
import pandas as pd

# --- 1. GLOBAL CONFIG (Must be first) ---
st.set_page_config(
    page_title="LendFlow Africa",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. INITIALIZE CONNECTION ---
# Ensure your .streamlit/secrets.toml has [connections.supabase]
conn = st.connection("supabase", type=SupabaseConnection)

# --- 3. SESSION STATE MANAGEMENT ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "tenant_id" not in st.session_state:
    st.session_state.tenant_id = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None

# --- 4. DATA FETCHING ---
@st.cache_data(ttl=300)
def get_tenant_data(tenant_id):
    try:
        res = conn.table("tenants").select("*").eq("id", tenant_id).single().execute()
        return res.data
    except Exception as e:
        st.error(f"Error fetching tenant: {e}")
        return None

# --- 5. MODULES ---

def render_dashboard(tenant):
    company = tenant.get("company_name", "LendFlow")
    currency = tenant.get("currency", "UGX")
    st.title(f"📊 {company} Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Loan Book", f"{currency} 0", "+0%")
    col2.metric("Active Borrowers", "0", "+0")
    col3.metric("Monthly Revenue", f"{currency} 0", "+0%")
    col4.metric("Default Rate", "0%", "-0%")
    st.divider()
    st.info("ℹ️ Advanced analytics & charts coming soon.")

def render_portfolio(tenant_id):
    st.title("📂 Portfolio Management")
    tab1, tab2, tab3 = st.tabs(["👥 Borrowers", "📑 Loans Book", "🛡️ Collateral"])

    with tab1:
        col_form, col_list = st.columns([1, 2])
        with col_form:
            st.subheader("➕ Add Borrower")
            with st.form("borrower_form", clear_on_submit=True):
                name = st.text_input("Full Name")
                phone = st.text_input("Phone Number")
                nin = st.text_input("National ID")
                if st.form_submit_button("Save Borrower", type="primary"):
                    if name and phone:
                        try:
                            conn.table("borrowers").insert({
                                "tenant_id": tenant_id,
                                "name": name,
                                "phone": phone,
                                "national_id": nin
                            }).execute()
                            st.success(f"{name} added!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Save failed: {e}")
                    else:
                        st.warning("Name and Phone are required.")

        with col_list:
            st.subheader("📋 Borrower List")
            try:
                res = conn.table("borrowers").select("*").eq("tenant_id", tenant_id).execute()
                if res.data:
                    st.dataframe(pd.DataFrame(res.data), use_container_width=True)
                else:
                    st.info("No borrowers found.")
            except:
                st.error("Could not load borrowers.")

def render_settings(tenant):
    st.title("⚙️ Workspace Settings")
    with st.container(border=True):
        new_name = st.text_input("Company Name", value=tenant.get("company_name"))
        new_color = st.color_picker("Primary Theme Color", value=tenant.get("theme_color", "#2B3F87"))
        
        if st.button("Save Changes", type="primary"):
            try:
                conn.table("tenants").update({
                    "company_name": new_name,
                    "theme_color": new_color
                }).eq("id", tenant["id"]).execute()
                st.cache_data.clear()
                st.success("Settings updated!")
                st.rerun()
            except Exception as e:
                st.error(f"Update failed: {e}")

# --- 6. MAIN INTERFACE ---
def main_interface():
    tenant = get_tenant_data(st.session_state.tenant_id)
    if not tenant:
        st.error("Session Error: Workspace not found.")
        if st.button("Back to Login"):
            st.session_state.logged_in = False
            st.rerun()
        st.stop()

    brand_color = tenant.get("theme_color", "#2B3F87")
    
    # Custom CSS for Dynamic Branding
    st.markdown(f"""
        <style>
        .stButton>button {{ border-radius: 5px; }}
        .nav-link-selected {{ background-color: {brand_color} !important; }}
        </style>
    """, unsafe_allow_html=True)

    # Top Navigation Bar
    col_brand, col_nav, col_user = st.columns([1.5, 4, 1])
    with col_brand:
        st.markdown(f"### 🚀 {tenant.get('company_name')}")
    
    with col_nav:
        selected = option_menu(
            None, ["Dashboard", "Portfolio", "Treasury", "Settings"],
            icons=["speedometer2", "briefcase", "cash-stack", "gear"],
            orientation="horizontal",
            styles={"nav-link-selected": {"background-color": brand_color}}
        )

    with col_user:
        if st.button("Log Out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.tenant_id = None
            st.rerun()

    st.divider()

    if selected == "Dashboard": render_dashboard(tenant)
    elif selected == "Portfolio": render_portfolio(st.session_state.tenant_id)
    elif selected == "Settings": render_settings(tenant)
    else: st.info(f"{selected} module coming soon.")

# --- 7. LOGIN SCREEN ---
def login_screen():
    st.markdown("<h1 style='text-align:center;'>LendFlow Africa</h1>", unsafe_allow_html=True)
    
    _, col, _ = st.columns([1, 2, 1])
    with col:
        tab1, tab2 = st.tabs(["🔐 Login", "🏢 Register Business"])
        
        with tab1:
            email = st.text_input("Email", placeholder="admin@business.com")
            password = st.text_input("Password", type="password")
            
            if st.button("Sign In", type="primary", use_container_width=True):
                try:
                    # Query profile based on email
                    res = conn.table("profiles").select("tenant_id").eq("email", email).execute()
                    
                    if res.data and len(res.data) > 0:
                        st.session_state.logged_in = True
                        st.session_state.tenant_id = res.data[0]["tenant_id"]
                        st.session_state.user_email = email
                        st.success("Login Successful!")
                        st.rerun()
                    else:
                        st.error("Account not found. Please register.")
                except Exception as e:
                    st.error(f"Authentication Error: {e}")

        with tab2:
            with st.form("reg_form"):
                biz_name = st.text_input("Business Name")
                admin_email = st.text_input("Admin Email")
                if st.form_submit_button("Create Workspace", use_container_width=True):
                    if biz_name and admin_email:
                        try:
                            # 1. Create Tenant
                            t_res = conn.table("tenants").insert({"company_name": biz_name}).execute()
                            new_id = t_res.data[0]["id"]
                            # 2. Create Profile
                            conn.table("profiles").insert({
                                "tenant_id": new_id, 
                                "email": admin_email,
                                "role": "Admin"
                            }).execute()
                            st.success("Workspace Created! You can now login.")
                        except Exception as e:
                            st.error(f"Registration failed: {e}")
                    else:
                        st.warning("Please fill all fields.")

# --- 8. ROUTING ---
if st.session_state.logged_in:
    main_interface()
else:
    login_screen()
