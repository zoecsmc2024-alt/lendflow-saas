import streamlit as st
from st_supabase_connection import SupabaseConnection
from streamlit_option_menu import option_menu
import pandas as pd

# --- 1. GLOBAL CONFIG ---
st.set_page_config(
    page_title="LendFlow Africa",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded" # Keep it open for that 'Admin' feel
)

# --- 2. INITIALIZE CONNECTION ---
conn = st.connection("supabase", type=SupabaseConnection)

# --- 3. SESSION STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# --- 4. STYLING (The "Neatness" Factor) ---
st.markdown("""
    <style>
    /* Main background */
    .stApp { background-color: #f8f9fa; }
    
    /* Card-like containers for metrics */
    div[data-testid="stMetric"] {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #eee;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #1e1e2d;
        color: white;
    }
    
    /* Title styling */
    h1, h2, h3 { font-weight: 700; color: #2d3436; }
    </style>
""", unsafe_allow_html=True)

# --- 5. UI HELPERS ---
@st.cache_data(ttl=300)
def get_tenant_data(tenant_id):
    try:
        res = conn.table("tenants").select("*").eq("id", tenant_id).single().execute()
        return res.data
    except: return None

# --- 6. MODULES ---
def render_dashboard(tenant):
    st.title("📊 Analytics Dashboard")
    
    # Metrics Row
    col1, col2, col3, col4 = st.columns(4)
    currency = tenant.get("currency", "UGX")
    
    col1.metric("Users", "6,453", "23.4%")
    col2.metric("Page Views", "876", "-12.0%")
    col3.metric("Impressions", "976", "-2.0%")
    col4.metric("Bounce Rate", "346", "23.4%")

    st.markdown("---")
    
    # Placeholder for charts (Using standard Streamlit bar charts for now)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Audience Overview")
        chart_data = pd.DataFrame([10, 20, 30, 25, 45, 30], columns=["Visitors"])
        st.bar_chart(chart_data)
    with c2:
        st.subheader("Web Traffic")
        st.line_chart(chart_data)

# --- 7. NAVIGATION & MAIN ---
def main_interface():
    tenant = get_tenant_data(st.session_state.tenant_id)
    if not tenant:
        st.error("Session expired.")
        st.session_state.logged_in = False
        st.rerun()

    # --- SIDEBAR NAVIGATION ---
    with st.sidebar:
        st.markdown(f"## 🚀 {tenant.get('company_name', 'LendFlow')}")
        st.markdown("---")
        
        selected = option_menu(
            menu_title=None,
            options=["Dashboard", "Portfolio", "Treasury", "Admin", "Settings"],
            icons=["grid-fill", "people-fill", "cash-coin", "shield-lock", "gear-wide-connected"],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "transparent"},
                "icon": {"color": "#a2a3b7", "font-size": "18px"}, 
                "nav-link": {
                    "font-size": "16px", 
                    "text-align": "left", 
                    "margin":"5px", 
                    "color": "#a2a3b7",
                    "--hover-color": "#2c2c3d"
                },
                "nav-link-selected": {"background-color": tenant.get("theme_color", "#2B3F87")},
            }
        )
        
        st.spacer = st.container() # Just for spacing
        st.write("")
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # --- ROUTING ---
    if selected == "Dashboard":
        render_dashboard(tenant)
    else:
        st.title(f"🛠️ {selected}")
        st.info(f"This section is under construction.")

# --- 8. LOGIN SYSTEM ---
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
                    if res.data:
                        st.session_state.logged_in = True
                        st.session_state.tenant_id = res.data[0]["tenant_id"]
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")
                except:
                    st.error("Connection error.")

# --- APP START ---
if st.session_state.logged_in:
    main_interface()
else:
    login_screen()
