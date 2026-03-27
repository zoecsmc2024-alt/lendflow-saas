import streamlit as st
from st_supabase_connection import SupabaseConnection
from streamlit_option_menu import option_menu
import pandas as pd

# --- 1. CONFIG ---
st.set_page_config(page_title="LendFlow Africa", layout="wide", initial_sidebar_state="expanded")

# --- 2. CONNECTION ---
conn = st.connection("supabase", type=SupabaseConnection)

# --- 3. SESSION STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "tenant_id" not in st.session_state:
    st.session_state.tenant_id = None

# --- 4. DATA HELPER ---
@st.cache_data(ttl=300)
def get_tenant_data(tenant_id):
    try:
        res = conn.table("tenants").select("*").eq("id", tenant_id).single().execute()
        return res.data
    except:
        return None

# --- 5. PAGE MODULES ---
def render_dashboard(tenant):
    st.title("📊 Analytics Dashboard")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Active Loans", "142", "+12%")
    col2.metric("Total Disbursed", "UGX 45M", "+5.4%")
    col3.metric("Repayment Rate", "94%", "0.2%")
    col4.metric("Pending Approvals", "18", "-2")
    st.divider()
    st.info("Charts and deeper analytics modules are being integrated.")

# --- 6. MAIN APP FLOW ---
def main_app():
    # 1. Fetch data safely
    tenant = get_tenant_data(st.session_state.tenant_id)
    
    if not tenant:
        st.error("Account Error: Could not fetch workspace details.")
        if st.button("Back to Login"):
            st.session_state.clear()
            st.rerun()
        return

    # 2. Sidebar Navigation
    with st.sidebar:
        st.markdown(f"## 🚀 {tenant.get('company_name', 'LendFlow')}")
        st.markdown("---")
        
        selected = option_menu(
            menu_title=None,
            options=["Dashboard", "Portfolio", "Treasury", "Admin", "Settings"],
            icons=["grid-fill", "people-fill", "cash-coin", "shield-lock", "gear-wide-connected"],
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "transparent"},
                "icon": {"color": "#a2a3b7", "font-size": "18px"}, 
                "nav-link": {
                    "font-size": "16px", "text-align": "left", "margin":"5px", 
                    "color": "#ffffff", "--hover-color": "#2c2c3d"
                },
                "nav-link-selected": {"background-color": tenant.get("theme_color", "#2B3F87")},
            }
        )
        
        # Logout styling & button
        st.markdown("<br>" * 10, unsafe_allow_html=True)
        st.markdown("""<style>
            div.stButton > button:first-child {
                background-color: transparent; color: #ff4b4b; border: 1px solid #3d3d4d;
            }
            div.stButton > button:first-child:hover {
                background-color: #ff4b4b; color: white; border: 1px solid #ff4b4b;
            }
        </style>""", unsafe_allow_html=True)

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # 3. Page Routing
    if selected == "Dashboard":
        render_dashboard(tenant)
    else:
        st.title(f"🛠️ {selected}")
        st.info(f"The {selected} module is coming soon.")

# --- 7. LOGIN SCREEN ---
def login_screen():
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown("<h1 style='text-align:center;'>🚀 LendFlow</h1>", unsafe_allow_html=True)
        with st.container(border=True):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.button("Login", type="primary", use_container_width=True):
                try:
                    res = conn.table("profiles").select("tenant_id").eq("email", email).execute()
                    if res.data and len(res.data) > 0:
                        st.session_state.logged_in = True
                        st.session_state.tenant_id = res.data[0]["tenant_id"]
                        st.rerun()
                    else:
                        st.error("User not found.")
                except Exception as e:
                    st.error("Login service unavailable.")

# --- 8. EXECUTION ---
if st.session_state.logged_in:
    main_app()
else:
    login_screen()

def render_settings(tenant):
    st.title("⚙️ Workspace Settings")
    st.markdown("Manage your organization's branding and regional configurations.")

    col_form, col_preview = st.columns([1.5, 1])

    with col_form:
        with st.container(border=True):
            st.subheader("🎨 Branding & Identity")
            
            # Use columns inside the form for a tighter look
            new_name = st.text_input("Company Name", value=tenant.get("company_name", "LendFlow"))
            
            c1, c2 = st.columns(2)
            with c1:
                new_color = st.color_picker("Brand Theme Color", value=tenant.get("theme_color", "#2B3F87"))
            with c2:
                new_currency = st.selectbox("Operating Currency", ["UGX", "KES", "USD", "TZS", "NGN"], 
                                           index=0 if tenant.get("currency") == "UGX" else 1)

            st.divider()
            
            if st.button("💾 Save Changes", type="primary", use_container_width=True):
                with st.spinner("Updating workspace..."):
                    try:
                        conn.table("tenants").update({
                            "company_name": new_name, 
                            "theme_color": new_color,
                            "currency": new_currency
                        }).eq("id", tenant['id']).execute()
                        
                        st.cache_data.clear() # Force refresh of the 'get_tenant_data' function
                        st.toast("Settings updated successfully!", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update settings: {e}")

    with col_preview:
        st.subheader("👁️ Live Preview")
        # Show the user what their sidebar header will look like
        with st.container(border=True):
            st.markdown(f"""
                <div style="background-color: #1e1e2d; padding: 20px; border-radius: 10px;">
                    <h3 style="color: white; margin: 0;">🚀 {new_name}</h3>
                    <hr style="border: 0.5px solid #3d3d4d;">
                    <div style="background-color: {new_color}; color: white; padding: 10px; border-radius: 5px; text-align: center; font-weight: bold;">
                        Selected Menu Item
                    </div>
                </div>
                <p style="text-align: center; color: gray; font-size: 12px; margin-top: 10px;">
                    This is how your sidebar will appear to staff.
                </p>
            """, unsafe_allow_html=True)
