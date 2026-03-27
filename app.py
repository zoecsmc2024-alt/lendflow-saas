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
    company = tenant.get("company_name", "LendFlow")
    currency = tenant.get("currency", "UGX")
    brand_color = tenant.get("theme_color", "#2B3F87")

    st.title(f"📊 {company} Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with st.container(border=True):
            st.caption("TOTAL LOAN BOOK")
            st.subheader(f"{currency} 125.4M")
            st.write("📈 +12% from last month")
    with col2:
        with st.container(border=True):
            st.caption("ACTIVE BORROWERS")
            st.subheader("1,240")
            st.write("👥 +48 new this week")
    with col3:
        with st.container(border=True):
            st.caption("REVENUE (INTEREST)")
            st.subheader(f"{currency} 12.8M")
            st.write("💰 On track")
    with col4:
        with st.container(border=True):
            st.caption("PAR @ 30 DAYS")
            st.subheader("2.4%")
            st.write("📉 -0.5% improvement")

    st.write("---")
    left_col, right_col = st.columns([2, 1])
    with left_col:
        with st.container(border=True):
            section_card("📅 Recent Disbursements")
            mock_data = pd.DataFrame({
                "Borrower": ["John Doe", "Mary Jane", "Alpha Ltd", "Sarah K."],
                "Amount": [500000, 1200000, 5000000, 300000],
                "Status": ["Approved", "Pending", "Approved", "Approved"]
            })
            st.dataframe(mock_data, use_container_width=True, hide_index=True)
    with right_col:
        with st.container(border=True):
            section_card("🔔 Alerts")
            st.warning("5 Loans overdue today")
            st.info("3 Collateral inspections due")
            st.success("NSSF Returns generated")

def render_portfolio(tenant_id):
    st.title("📂 Portfolio Management")
    tab1, tab2, tab3 = st.tabs(["👥 Borrowers", "📑 Loans Book", "🛡️ Collateral Vault"])

    with tab1:
        col_form, col_list = st.columns([1, 2])
        with col_form:
            with st.container(border=True):
                section_card("➕ Add Borrower")
                with st.form("borrower_form", clear_on_submit=True):
                    name = st.text_input("Full Name")
                    phone = st.text_input("Phone Number")
                    nin = st.text_input("National ID")
                    if st.form_submit_button("Save Borrower", type="primary", use_container_width=True):
                        if not name or not phone:
                            st.error("Name and phone required.")
                        else:
                            try:
                                conn.table("borrowers").insert({
                                    "tenant_id": tenant_id, "name": name, "phone": phone, "national_id": nin
                                }).execute()
                                st.success("Added!")
                                st.rerun()
                            except: st.error("Error saving.")
        with col_list:
            with st.container(border=True):
                section_card("📋 Borrower List")
                try:
                    res = conn.table("borrowers").select("*").eq("tenant_id", tenant_id).execute()
                    if res.data:
                        df = pd.DataFrame(res.data)
                        st.dataframe(df[["name", "phone", "national_id"]], use_container_width=True, hide_index=True)
                    else: show_empty("No borrowers found.")
                except: st.error("Connection error.")

def render_treasury():
    st.title("💰 Treasury")
    show_empty("Treasury module coming soon.")

def render_admin():
    st.title("🧾 Admin")
    show_empty("Admin module coming soon.")

def render_settings(tenant):
    st.title("⚙️ Workspace Settings")

    # --- BRANDING SECTION ---
    with st.container(border=True):
        section_card("🎨 Branding & Identity")
        
        col_text, col_logo = st.columns([2, 1])
        
        with col_text:
            new_name = st.text_input("Company Name", value=tenant.get("company_name", "LendFlow"))
            new_color = st.color_picker("Brand Color", value=tenant.get("theme_color", "#2B3F87"))
            
        with col_logo:
            current_logo = tenant.get("logo_url")
            if current_logo:
                st.image(current_logo, caption="Current Logo", width=150)
            else:
                st.info("No logo uploaded.")

        # LOGO UPLOAD
        uploaded_file = st.file_uploader("Upload New Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])

        if st.button("Save Workspace Changes", type="primary"):
            with st.spinner("Updating..."):
                try:
                    update_data = {
                        "company_name": new_name,
                        "theme_color": new_color
                    }

                    # If a new file is uploaded, push to Supabase Storage
                    if uploaded_file:
                        file_ext = uploaded_file.name.split(".")[-1]
                        file_path = f"{tenant['id']}/logo.{file_ext}"
                        
                        # Upload to 'logos' bucket
                        conn.upload("logos", file_path, uploaded_file, upsert=True)
                        
                        # Get Public URL (Replace 'YOUR_PROJECT_ID' with your actual Supabase project ID)
                        # Standard Supabase URL format:
                        project_id = "your-project-id" # Tip: You can grab this from your secrets
                        public_url = f"https://{project_id}.supabase.co/storage/v1/object/public/logos/{file_path}"
                        update_data["logo_url"] = public_url

                    # Update Database
                    conn.table("tenants").update(update_data).eq("id", tenant["id"]).execute()
                    
                    st.cache_data.clear()
                    st.success("Settings updated! Refreshing...")
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

# --- 6. MAIN INTERFACE ---
def main_interface():
    # ... session checks ...
    tenant = get_tenant_data(st.session_state.tenant_id)
    
    logo_to_show = tenant.get("logo_url")
    brand_color = tenant.get("theme_color", "#2B3F87")

    with st.sidebar:
        if logo_to_show:
            st.image(logo_to_show, use_container_width=True)
        else:
            # Fallback to a rocket emoji or generic text if no logo exists
            st.markdown(f"<h2 style='text-align:center;'>🚀</h2>", unsafe_allow_html=True)

        st.markdown(f"<h3 style='text-align:center; color:{brand_color};'>{tenant['company_name']}</h3>", unsafe_allow_html=True)
        
        # ... rest of your sidebar code (option_menu, etc.) ...
        selected = option_menu(
            None, ["Dashboard", "Portfolio", "Treasury", "Admin", "Settings"],
            icons=["grid", "people", "wallet", "shield", "gear"],
            menu_icon="cast", default_index=0,
            styles={"nav-link-selected": {"background-color": brand_color}}
        )
        st.write("---")
        if st.button("Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()

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
    st.title("🚀 LendFlow Africa")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["🔐 Login", "🏢 Register"])
        with tab1:
            email = st.text_input("Email")
            if st.button("Login", type="primary", use_container_width=True):
                res = conn.table("profiles").select("tenant_id").eq("email", email).execute()
                if res.data:
                    st.session_state.logged_in = True
                    st.session_state.tenant_id = res.data[0]["tenant_id"]
                    st.rerun()
                else: st.error("Invalid credentials.")
        with tab2:
            with st.form("reg"):
                biz = st.text_input("Business Name")
                em = st.text_input("Admin Email")
                if st.form_submit_button("Register"):
                    t = conn.table("tenants").insert({"company_name": biz}).execute()
                    conn.table("profiles").insert({"tenant_id": t.data[0]["id"], "email": em}).execute()
                    st.success("Done! Please login.")

# --- 8. APP ENTRY ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in:
    main_interface()
else:
    login_screen()
