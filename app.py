import streamlit as st
from st_supabase_connection import SupabaseConnection
from streamlit_option_menu import option_menu
import pandas as pd

# --- 1. INITIALIZE CONNECTION ---
conn = st.connection("supabase", type=SupabaseConnection)

# --- 2. GLOBAL CONFIG ---
st.set_page_config(
    page_title="LendFlow Africa",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 3. CACHED TENANT FETCH ---
@st.cache_data(ttl=300)
def get_tenant_data(tenant_id):
    try:
        res = (
            conn.table("tenants")
            .select("*")
            .eq("id", tenant_id)
            .single()
            .execute()
        )
        return res.data
    except Exception as e:
        # It's helpful to log the error during development
        # st.error(f"Error fetching tenant: {e}")
        return None

# --- 4. UI HELPERS ---
def section_card(title):
    st.markdown(f"### {title}")

def show_empty(message):
    st.info(f"ℹ️ {message}")

# --- 5. MODULES ---
def render_dashboard(tenant):
    # Safety check: if tenant is None, use defaults
    if not tenant:
        tenant = {}
        
    company = tenant.get("company_name", "LendFlow")
    currency = tenant.get("currency", "UGX")

    st.title(f"📊 {company} Overview")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Loan Book", f"{currency} 0", "+0%")
    col2.metric("Active Borrowers", "0", "+0")
    col3.metric("Monthly Revenue", f"{currency} 0", "+0%")
    col4.metric("Default Rate", "0%", "-0%")

    st.divider()
    show_empty("Advanced analytics & charts coming soon.")


# --- PORTFOLIO ---
def render_portfolio(tenant_id):
    st.title("📂 Portfolio Management")

    tab1, tab2, tab3 = st.tabs([
        "👥 Borrowers",
        "📑 Loans Book",
        "🛡️ Collateral Vault"
    ])

    # --- BORROWERS ---
    with tab1:
        col_form, col_list = st.columns([1, 2])

        # FORM
        with col_form:
            section_card("➕ Add Borrower")

            with st.form("borrower_form", clear_on_submit=True):
                name = st.text_input("Full Name")
                phone = st.text_input("Phone Number")
                nin = st.text_input("National ID")

                submitted = st.form_submit_button("Save Borrower", type="primary")

                if submitted:
                    if not name or not phone:
                        st.error("Name and phone are required.")
                    else:
                        with st.spinner("Saving borrower..."):
                            try:
                                conn.table("borrowers").insert({
                                    "tenant_id": tenant_id,
                                    "name": name,
                                    "phone": phone,
                                    "national_id": nin
                                }).execute()

                                st.success(f"{name} added successfully")
                                st.rerun()

                            except Exception as e:
                                st.error("Failed to save borrower.")

        # LIST
        with col_list:
            section_card("📋 Borrower List")

            with st.spinner("Loading borrowers..."):
                try:
                    res = (
                        conn.table("borrowers")
                        .select("name, phone, national_id")
                        .eq("tenant_id", tenant_id)
                        .execute()
                    )

                    if res.data:
                        df = pd.DataFrame(res.data)
                        st.dataframe(df, use_container_width=True)
                    else:
                        show_empty("No borrowers yet.")

                except Exception as e:
                    st.error("Failed to load borrowers.")

    # --- LOANS ---
    with tab2:
        section_card("📑 Loan Book")
        show_empty("Loan engine coming next.")

    # --- COLLATERAL ---
    with tab3:
        section_card("🛡️ Collateral Vault")
        show_empty("Collateral tracking coming soon.")
# --- TREASURY ---
def render_treasury():
    st.title("💰 Treasury & Cashflow")
    tab1, tab2, tab3 = st.tabs(["📥 Payments", "📤 Expenses", "☕ Petty Cash"])
    
    with tab1:
        show_empty("Payment tracking module coming soon.")
    with tab2:
        show_empty("Expense tracking module coming soon.")
    with tab3:
        show_empty("Petty cash management coming soon.")

# --- ADMIN ---
def render_admin():
    st.title("🧾 Admin & Payroll")

    tab1, tab2, tab3 = st.tabs([
        "👥 Staff",
        "💸 Payroll",
        "🏛️ Taxes (URA/NSSF)"
    ])

    with tab1:
        show_empty("Role-based access control coming soon.")

    with tab2:
        show_empty("Payroll system coming soon.")

    with tab3:
        show_empty("Tax integrations coming soon.")


# --- SETTINGS ---
def render_settings(tenant):
    st.title("⚙️ Workspace Settings")

    with st.container(border=True):
        section_card("🎨 Branding")

        # Fallback values to prevent crashes if keys are missing
        current_name = tenant.get("company_name", "LendFlow")
        current_color = tenant.get("theme_color", "#2B3F87")

        new_name = st.text_input("Company Name", value=current_name)
        new_color = st.color_picker("Primary Color", value=current_color)

        if st.button("Save Changes", type="primary"):
            with st.spinner("Updating settings..."):
                try:
                    conn.table("tenants").update({
                        "company_name": new_name,
                        "theme_color": new_color
                    }).eq("id", tenant["id"]).execute()

                    # Clear cache so the app fetches the fresh data immediately
                    st.cache_data.clear()
                    st.success("Settings updated successfully.")
                    st.rerun()

                except Exception as e:
                    st.error("Failed to update settings.")

# --- 6. MAIN INTERFACE (SIDEBAR VERSION) ---
def main_interface():
    if "tenant_id" not in st.session_state:
        st.error("Session expired. Please log in again.")
        st.stop()

    tenant = get_tenant_data(st.session_state.tenant_id)

    if not tenant:
        st.error("Workspace not found.")
        st.stop()

    brand_color = tenant.get("theme_color", "#2B3F87")
    company = tenant.get("company_name", "LendFlow")

    # --- SIDEBAR NAVIGATION ---
    

    # --- ROUTING ---
    # The main area now just displays the content based on sidebar selection
    if selected == "Dashboard":
        render_dashboard(tenant)
    elif selected == "Portfolio":
        render_portfolio(st.session_state.tenant_id)
    elif selected == "Treasury":
        render_treasury()
    elif selected == "Admin":
        render_admin()
    elif selected == "Settings":
        render_settings(tenant)


# --- 7. LOGIN SYSTEM ---
def login_screen():
    st.markdown("<h1 style='text-align:center;'>🚀 LendFlow Africa</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;'>The Operating System for Modern Lenders</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        tab1, tab2 = st.tabs(["🔐 Login", "🏢 Register"])

        # LOGIN
        with tab1:
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")

            if st.button("Login", type="primary", use_container_width=True):
                with st.spinner("Authenticating..."):
                    try:
                        res = (
                            conn.table("profiles")
                            .select("tenant_id")
                            .eq("email", email)
                            .execute()
                        )

                        if res.data:
                            st.session_state.logged_in = True
                            st.session_state.tenant_id = res.data[0]["tenant_id"]
                            st.rerun()
                        else:
                            st.error("Invalid credentials.")
                    except Exception as e:
                        st.error("Login failed.")

        # REGISTER
        with tab2:
            with st.form("register_form"):
                biz = st.text_input("Business Name")
                reg_email = st.text_input("Admin Email")

                if st.form_submit_button("Create Workspace", type="primary"):
                    if not biz or not reg_email:
                        st.warning("All fields required.")
                    else:
                        try:
                            tenant_res = conn.table("tenants").insert({"company_name": biz}).execute()
                            t_id = tenant_res.data[0]["id"]
                            conn.table("profiles").insert({
                                "tenant_id": t_id,
                                "email": reg_email,
                                "role": "Admin"
                            }).execute()
                            st.success("Workspace created. Please log in.")
                        except Exception as e:
                            st.error("Registration failed.")

# --- 8. APP ENTRY ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in:
    main_interface()
else:
    login_screen()
