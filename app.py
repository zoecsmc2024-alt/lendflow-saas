import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import datetime

# --- 1. CONFIG & SAAS THEME ENGINE ---
st.set_page_config(page_title="Peak-Lenders Africa", layout="wide", page_icon="🌍")

if 'theme_color' not in st.session_state:
    st.session_state.theme_color = "#1E3A8A"

def apply_custom_theme(color):
    st.session_state.theme_color = color
    st.markdown(f"""
        <style>
        [data-testid="stSidebar"] {{ background-color: {color} !important; }}
        [data-testid="stSidebar"] *, [data-testid="stSidebarNav"] span {{ color: white !important; }}
        [data-testid="stWidgetLabel"] p {{ color: white !important; }}
        div[data-baseweb="select"] * {{ color: #1E3A8A !important; }}
        ul[data-testid="stSelectboxVirtualList"] * {{ color: #1E3A8A !important; }}
        .stSelectbox label p {{ color: white !important; }}
        div[data-testid="stMetric"] {{
            background-color: white; padding: 15px; border-radius: 10px;
            border-left: 5px solid {color}; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        h1, h2, h3 {{ color: {color}; }}
        </style>
    """, unsafe_allow_html=True)

# --- 2. SUPABASE CONNECTION ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 3. MATH & ACCOUNTING HELPERS ---
def calculate_uganda_payroll(basic):
    nssf_5 = float(basic) * 0.05
    taxable = float(basic) - nssf_5
    paye = 0
    if taxable > 410000: paye = (taxable - 410000) * 0.3 + 25000
    elif taxable > 335000: paye = (taxable - 335000) * 0.2 + 10000
    elif taxable > 235000: paye = (taxable - 235000) * 0.1
    return nssf_5, paye, (float(basic) - nssf_5 - paye)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

def generate_loan_pdf(company, client_name, loan_data):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    # --- HEADER ---
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 800, f"{company['name']}")

    c.setFont("Helvetica", 10)
    c.drawString(50, 785, "OFFICIAL LOAN AGREEMENT")

    # --- CLIENT INFO ---
    c.drawString(50, 750, f"Borrower: {client_name}")
    c.drawString(50, 735, f"Date: {datetime.now().strftime('%Y-%m-%d')}")

    # --- LOAN DETAILS ---
    c.drawString(50, 700, f"Principal: {loan_data['principal_amount']:,.0f} UGX")
    c.drawString(50, 685, f"Interest Rate: {loan_data['interest_rate']}%")
    c.drawString(50, 670, f"Duration: {loan_data['duration_months']} months")
    c.drawString(50, 655, f"Total Repayable: {loan_data['total_repayable']:,.0f} UGX")
    c.drawString(50, 640, f"Monthly Installment: {loan_data['monthly_installment']:,.0f} UGX")

    # --- TERMS ---
    c.drawString(50, 600, "Terms & Conditions:")
    c.setFont("Helvetica", 9)
    c.drawString(50, 585, "- The borrower agrees to repay the loan as scheduled.")
    c.drawString(50, 570, "- Late payments may attract penalties.")
    c.drawString(50, 555, "- The lender reserves the right to recover collateral.")

    # --- SIGNATURE ---
    c.setFont("Helvetica", 10)
    c.drawString(50, 500, "_________________________")
    c.drawString(50, 485, "Authorized Signature")

    c.drawString(300, 500, "_________________________")
    c.drawString(300, 485, "Borrower Signature")

    c.save()
    buffer.seek(0)
    return buffer

def calculate_loan(principal, rate, months):
    interest = float(principal) * (float(rate)/100) * (float(months)/12)
    total = float(principal) + interest
    return round(total), round(total/months)

def get_data(table, company_id):
    try:
        return supabase.table(table).select("*").eq("company_id", company_id).execute().data
    except:
        return []

def get_dashboard_metrics(company_id):
    loans = get_data("loans", company_id)
    payments = get_data("transactions", company_id)
    expenses = get_data("expenses", company_id)
    return loans, payments, expenses

# --- 4. AUTH & SIDEBAR NAVIGATION ---
companies_res = supabase.table("companies").select("id, name, brand_color").execute()
company_list = {c['name']: c for c in companies_res.data}

with st.sidebar:
    st.title("🌍 Peak-Lenders Africa")
    st.write("---")
    active_company_name = st.selectbox("Log in as:", list(company_list.keys()))
    active_company = company_list[active_company_name]
    apply_custom_theme(active_company['brand_color'])
    st.success(f"Mode: {active_company['name']}")
    st.write("---")
    page = st.radio("Navigation Menu", ["📈 Overview", "👥 Clients", "💵 Loans", "💰 Payments", "🚨 Overdue", "🛡️ Collateral", "📂 Expenses", "📄 Payroll", "📄 Ledger", "🧾 Reports"])

# --- 5. THE SWITCHBOARD ---

if page == "📈 Overview":
    st.title(f"📈 {active_company['name']} | AI Executive Command Center")

    loans, payments, expenses = get_dashboard_metrics(active_company['id'])

    if not loans:
        st.info("Welcome! Start by registering a client and issuing your first loan.")
    else:
        # --- DATA PREP ---
        df_loans = pd.DataFrame(loans)
        df_payments = pd.DataFrame(payments)
        df_expenses = pd.DataFrame(expenses)

        # Clean numeric columns safely
        for col in ['balance_remaining', 'principal_amount', 'monthly_installment']:
            if col in df_loans:
                df_loans[col] = pd.to_numeric(df_loans[col], errors='coerce').fillna(0)

        if 'amount_paid' in df_payments:
            df_payments['amount_paid'] = pd.to_numeric(df_payments['amount_paid'], errors='coerce').fillna(0)

        if 'amount' in df_expenses:
            df_expenses['amount'] = pd.to_numeric(df_expenses['amount'], errors='coerce').fillna(0)

        # --- CORE METRICS ---
        total_balance = df_loans['balance_remaining'].sum()
        total_principal = df_loans['principal_amount'].sum() if 'principal_amount' in df_loans else 0
        total_collected = df_payments['amount_paid'].sum() if not df_payments.empty else 0
        total_opex = df_expenses['amount'].sum() if not df_expenses.empty else 0
        net_cash = total_collected - total_opex

        overdue_df = df_loans[df_loans['loan_status']=="Overdue"] if 'loan_status' in df_loans else pd.DataFrame()
        overdue_amount = overdue_df['balance_remaining'].sum() if not overdue_df.empty else 0

        active_loans = len(df_loans)
        recovery_rate = (total_collected / total_principal * 100) if total_principal > 0 else 0

        # --- 🔮 AI PREDICTIONS (SIMPLE BUT POWERFUL) ---
        predicted_default = df_loans[df_loans['balance_remaining'] > df_loans.get('monthly_installment',1)*3]
        default_risk_score = (len(predicted_default) / active_loans * 100) if active_loans else 0

        projected_revenue_30d = df_loans['monthly_installment'].sum() if 'monthly_installment' in df_loans else 0
        projected_profit_30d = projected_revenue_30d - (total_opex / 12)

        # --- 💎 EXECUTIVE KPI STRIP ---
        st.markdown("### 🏦 Executive Intelligence Layer")

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("💼 Portfolio", f"{total_balance:,.0f}")
        k2.metric("💰 Collected", f"{total_collected:,.0f}")
        k3.metric("📉 Expenses", f"{total_opex:,.0f}")
        k4.metric("🏦 Net Cash", f"{net_cash:,.0f}")
        k5.metric("📊 Recovery", f"{recovery_rate:.1f}%")
        k6.metric("🚨 Risk Score", f"{default_risk_score:.1f}%")

        st.write("---")

        # --- 🧠 PREDICTIVE METRICS ---
        p1, p2, p3 = st.columns(3)
        p1.metric("🔮 30D Revenue Forecast", f"{projected_revenue_30d:,.0f} UGX")
        p2.metric("📈 30D Profit Forecast", f"{projected_profit_30d:,.0f} UGX")
        p3.metric("⚠️ Overdue Exposure", f"{overdue_amount:,.0f} UGX")

        st.write("---")

        # --- 📊 VISUAL GRID ---
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("#### 📊 Portfolio Health")
            if not df_loans.empty:
                fig = px.pie(
                    df_loans,
                    names='loan_status',
                    values='balance_remaining',
                    hole=0.65,
                    color='loan_status',
                    color_discrete_map={
                        'Active': active_company['brand_color'],
                        'Overdue': '#FF4B4B',
                        'Settled': '#00C853'
                    }
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("#### 📉 Expense Engine")
            if not df_expenses.empty:
                exp_group = df_expenses.groupby('category')['amount'].sum().reset_index()
                fig = px.bar(exp_group, x='category', y='amount', color='amount')
                st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown("#### 📦 Loan Distribution")
            if 'principal_amount' in df_loans:
                fig = px.box(df_loans, y='principal_amount')
                st.plotly_chart(fig, use_container_width=True)

        # --- 📈 CASHFLOW TREND ---
        st.write("---")
        st.markdown("### 📈 Smart Cashflow Timeline")

        if not df_payments.empty and 'payment_date' in df_payments:
            df_payments['payment_date'] = pd.to_datetime(df_payments['payment_date'])
            trend = df_payments.groupby(df_payments['payment_date'].dt.date)['amount_paid'].sum().reset_index()

            fig = px.line(trend, x='payment_date', y='amount_paid', markers=True)
            st.plotly_chart(fig, use_container_width=True)

        # --- 🧠 AI INSIGHTS ENGINE ---
        st.write("---")
        st.markdown("### 🤖 AI Insights Engine")

        i1, i2 = st.columns(2)

        with i1:
            if default_risk_score > 40:
                st.error("🚨 High Default Risk Detected. Tighten credit policies immediately.")
            elif default_risk_score > 15:
                st.warning("⚠️ Moderate risk detected. Monitor borrowers closely.")
            else:
                st.success("✅ Portfolio risk is under control.")

        with i2:
            if projected_profit_30d < 0:
                st.error("📉 Negative projected profit. Reduce expenses urgently.")
            elif projected_profit_30d < projected_revenue_30d * 0.2:
                st.warning("⚠️ Profit margins are tightening.")
            else:
                st.success("💰 Strong projected profitability.")

        # --- 🏆 TOP CLIENTS ---
        st.write("---")
        st.markdown("### 🏆 Top Borrowers (Revenue Drivers)")

        if not df_loans.empty:
            # We filter for relevant columns only to avoid index errors
            cols_to_show = [c for c in ['full_name', 'principal_amount', 'balance_remaining'] if c in df_loans.columns]
            top_clients = df_loans.sort_values(by='principal_amount', ascending=False).head(5)
            st.dataframe(top_clients[cols_to_show], use_container_width=True)

        # --- 🧾 INVESTOR SUMMARY ---
        st.write("---")
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, {active_company['brand_color']}, #000000);
            padding: 30px;
            border-radius: 18px;
            color: white;
        ">
            <h2 style="color: white; margin-top: 0;">🚀 Investor Snapshot</h2>
            <p style="margin: 5px 0;"><b>Portfolio:</b> {total_balance:,.0f} UGX</p>
            <p style="margin: 5px 0;"><b>Monthly Revenue (Projected):</b> {projected_revenue_30d:,.0f} UGX</p>
            <p style="margin: 5px 0;"><b>Projected Profit:</b> {projected_profit_30d:,.0f} UGX</p>
            <p style="margin: 5px 0;"><b>Risk Score:</b> {default_risk_score:.1f}%</p>
            <p style="margin: 5px 0;"><b>Status:</b> {"🟢 SCALING" if projected_profit_30d > 0 else "🔴 NEEDS OPTIMIZATION"}</p>
        </div>
        """, unsafe_allow_html=True)



elif page == "👥 Clients":
    st.title(f"👥 {active_company['name']} | Client CRM System")

    # --- CSS FIX: FORCE MAIN PAGE LABELS TO BE VISIBLE ---
    st.markdown("""
        <style>
        /* This ensures labels on the main white background stay dark */
        [data-testid="stWidgetLabel"] p {
            color: #31333F !important;
        }
        /* This keeps sidebar labels white (overriding the above for sidebar only) */
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
            color: white !important;
        }
        </style>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["➕ Register", "📋 CRM Database"])

    # --- TAB 1: REGISTER ---
    with tab1:
        st.markdown("### 🛡️ Client Onboarding")

        with st.form("client_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            f_name = col1.text_input("Full Name / Business Name")
            id_no = col2.text_input("National ID / Passport No.")

            phone = col1.text_input("Phone Number")
            email = col2.text_input("Email Address")

            if st.form_submit_button("🔐 Register Client", use_container_width=True):
                if not f_name or not id_no:
                    st.error("⚠️ Name and ID are required.")
                else:
                    supabase.table("clients").insert({
                        "company_id": active_company['id'],
                        "full_name": f_name.strip(),
                        "id_number": id_no.strip(),
                        "phone_number": phone.strip(),
                        "email": email.strip()
                    }).execute()

                    st.success(f"✅ {f_name} registered successfully!")
                    st.rerun()

    # --- TAB 2: CRM DATABASE ---
    with tab2:
        st.markdown("### 📊 Client Intelligence Dashboard")

        clients = get_data("clients", active_company['id'])
        loans = get_data("loans", active_company['id'])
        payments = get_data("transactions", active_company['id'])

        if clients:
            df_clients = pd.DataFrame(clients)
            df_loans = pd.DataFrame(loans)
            df_payments = pd.DataFrame(payments)

            # --- SEARCH & FILTER ---
            col1, col2 = st.columns([2,1])
            search = col1.text_input("🔍 Search client")
            filter_type = col2.selectbox("Filter", ["All", "With Loans", "No Loans", "High Risk"])

            if search:
                df_clients = df_clients[df_clients['full_name'].str.contains(search, case=False, na=False)]

            # --- CLIENT METRICS ENGINE ---
            client_metrics = []

            for _, c in df_clients.iterrows():
                client_id = c['id']

                client_loans = df_loans[df_loans['client_id'] == client_id] if not df_loans.empty else pd.DataFrame()
                
                # Payment tracking logic
                if not client_loans.empty and not df_payments.empty:
                    client_payments = df_payments[df_payments['loan_id'].isin(client_loans['id'])]
                else:
                    client_payments = pd.DataFrame()

                total_loans = client_loans['principal_amount'].sum() if not client_loans.empty else 0
                balance = client_loans['balance_remaining'].sum() if not client_loans.empty else 0
                paid = client_payments['amount_paid'].sum() if not client_payments.empty else 0

                risk_flag = "✅ Good"
                if balance > 0 and paid < total_loans * 0.3:
                    risk_flag = "⚠️ Risky"

                client_metrics.append({
                    "id": client_id,
                    "Name": c['full_name'],
                    "Phone": c.get('phone_number', ''),
                    "Total Borrowed": total_loans,
                    "Total Paid": paid,
                    "Balance": balance,
                    "Score": paid - balance,
                    "Risk": risk_flag
                })

            df_crm = pd.DataFrame(client_metrics)

            # --- FILTER LOGIC ---
            if filter_type == "With Loans":
                df_crm = df_crm[df_crm["Total Borrowed"] > 0]
            elif filter_type == "No Loans":
                df_crm = df_crm[df_crm["Total Borrowed"] == 0]
            elif filter_type == "High Risk":
                df_crm = df_crm[df_crm["Risk"] != "✅ Good"]

            # --- KPI STRIP ---
            st.write("---")
            k1, k2, k3, k4 = st.columns(4)

            k1.metric("👥 Clients", len(df_crm))
            k2.metric("💰 Total Portfolio", f"{df_crm['Balance'].sum():,.0f} UGX")
            k3.metric("📥 Total Collected", f"{df_crm['Total Paid'].sum():,.0f} UGX")
            k4.metric("⚠️ Risk Clients", len(df_crm[df_crm["Risk"] != "✅ Good"]))

            st.write("---")

            # --- MAIN CRM TABLE ---
            st.dataframe(
                df_crm.sort_values("Score", ascending=False),
                use_container_width=True,
                hide_index=True
            )

            # --- CLIENT DEEP DIVE ---
            st.write("---")
            st.markdown("### 🔍 Client Deep Dive")

            client_names = {row["Name"]: row["id"] for _, row in df_crm.iterrows()}
            selected_client = st.selectbox("Select Client for Deep Dive", list(client_names.keys()))

            if selected_client:
                selected_id = client_names[selected_client]

                # Pull detailed history for specific client
                client_loans_det = df_loans[df_loans['client_id'] == selected_id] if not df_loans.empty else pd.DataFrame()
                
                if not client_loans_det.empty and not df_payments.empty:
                    client_payments_det = df_payments[df_payments['loan_id'].isin(client_loans_det['id'])]
                else:
                    client_payments_det = pd.DataFrame()

                col1, col2, col3 = st.columns(3)

                t_borrowed = client_loans_det['principal_amount'].sum() if not client_loans_det.empty else 0
                t_balance = client_loans_det['balance_remaining'].sum() if not client_loans_det.empty else 0
                t_paid = client_payments_det['amount_paid'].sum() if not client_payments_det.empty else 0

                col1.metric("💰 Borrowed", f"{t_borrowed:,.0f}")
                col2.metric("📥 Paid", f"{t_paid:,.0f}")
                col3.metric("📉 Balance", f"{t_balance:,.0f}")

                # --- MINI STATEMENT ---
                st.write("#### 📑 Recent Transactions")

                if not client_payments_det.empty:
                    st.dataframe(
                        client_payments_det.sort_values("payment_date", ascending=False)[
                            ["payment_date", "amount_paid", "payment_method"]
                        ],
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No transactions found for this borrower.")

                # --- RISK ALERT ---
                if t_balance > 0 and t_paid < t_borrowed * 0.3:
                    st.error("🚨 High Risk Client - Low repayment behavior detected.")
                elif t_borrowed > 0:
                    st.success("✅ Client is performing well.")

        else:
            st.info("No clients found in your database.")



elif page == "💵 Loans":
    st.title(f"💵 {active_company['name']} | Credit Engine")

    clients = get_data("clients", active_company['id'])
    loans = get_data("loans", active_company['id'])

    if not clients:
        st.warning("⚠️ Register a client first.")
        st.stop()

    df_loans = pd.DataFrame(loans) if loans else pd.DataFrame()

    # --- LOAN FORM ---
    st.markdown("### 🚀 Issue New Loan")

    with st.form("loan_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        # Client mapping
        c_map = {c['full_name']: c['id'] for c in clients}
        target = col1.selectbox("👤 Select Borrower", list(c_map.keys()))

        amt = col2.number_input("💰 Principal (UGX)", min_value=10000, step=50000)

        rate = col1.number_input("📈 Annual Interest %", min_value=1.0, value=15.0)
        dur = col2.number_input("⏳ Duration (Months)", min_value=1, value=6)

        # --- LIVE LOAN PREVIEW ---
        total, monthly = calculate_loan(amt, rate, dur)

        st.info(f"""
        💡 **Loan Summary**
        - Total Repayable: {total:,.0f} UGX  
        - Monthly Installment: {monthly:,.0f} UGX  
        """)

        # --- CLIENT EXPOSURE ---
        client_id = c_map[target]
        client_loans = df_loans[df_loans['client_id'] == client_id] if not df_loans.empty else pd.DataFrame()

        current_balance = client_loans['balance_remaining'].sum() if not client_loans.empty else 0
        total_after = current_balance + total

        st.write("---")
        c1, c2 = st.columns(2)
        c1.metric("📊 Current Exposure", f"{current_balance:,.0f} UGX")
        c2.metric("📈 After This Loan", f"{total_after:,.0f} UGX")

        # --- RISK WARNING ---
        st.write("---")

        risk_flag = "LOW"
        if current_balance > 0 and total_after > current_balance * 2:
            st.warning("⚠️ High Exposure: This client is doubling their debt.")
            risk_flag = "MEDIUM"

        if current_balance > 0 and total_after > 5000000:
            st.error("🚨 Risk Alert: Client exposure is very high.")
            risk_flag = "HIGH"

        # --- SUBMIT ---
        if st.form_submit_button("💳 Disburse Loan", use_container_width=True):
            if amt <= 0:
                st.error("⚠️ Amount must be greater than 0.")
            else:
                try:
                    # 1. Prepare the Data
                    loan_payload = {
                        "company_id": active_company['id'],
                        "client_id": client_id,
                        "principal_amount": amt,
                        "interest_rate": rate,
                        "duration_months": dur,
                        "total_repayable": total,
                        "monthly_installment": monthly,
                        "balance_remaining": total,
                        "loan_status": "Active"
                    }

                    # 2. Push to Supabase
                    supabase.table("loans").insert(loan_payload).execute()

                    st.success(f"✅ Loan of {amt:,.0f} UGX disbursed to {target}!")

                    # 3. Handle PDF Generation (Optional - if you have the helper defined)
                    if 'generate_loan_pdf' in globals():
                        pdf_file = generate_loan_pdf(
                            active_company,
                            target,
                            loan_payload
                        )
                        st.download_button(
                            label="📥 Download Loan Agreement",
                            data=pdf_file,
                            file_name=f"Agreement_{target}_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf"
                        )
                    
                    # Refresh to show data on dashboard
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ System Error: {str(e)}")

    # --- PORTFOLIO VIEW ---
    st.write("---")
    st.markdown("### 📊 Active Loan Portfolio")

    if not df_loans.empty:
        df_loans['principal_amount'] = pd.to_numeric(df_loans['principal_amount'], errors='coerce').fillna(0)
        df_loans['balance_remaining'] = pd.to_numeric(df_loans['balance_remaining'], errors='coerce').fillna(0)

        st.dataframe(
            df_loans[["client_id", "principal_amount", "balance_remaining", "loan_status"]],
            use_container_width=True,
            hide_index=True
        )

        # --- PORTFOLIO METRICS ---
        total_portfolio = df_loans['balance_remaining'].sum()
        avg_loan = df_loans['principal_amount'].mean()

        p1, p2 = st.columns(2)
        p1.metric("💼 Total Portfolio", f"{total_portfolio:,.0f} UGX")
        p2.metric("📌 Avg Loan Size", f"{avg_loan:,.0f} UGX")

    else:
        st.info("No loans issued yet.")


import streamlit as st
import supabase
from datetime import datetime

# Initialize Supabase client (ensure this is set up in your environment)
supabase = supabase.create_client('YOUR_SUPABASE_URL', 'YOUR_SUPABASE_KEY')

# Function to upload image to Supabase Storage and return the URL
def upload_image(file):
    storage = supabase.storage()
    bucket_name = 'collateral-photos'
    file_name = f"collateral_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.name}"
    
    # Upload the file to the Supabase bucket
    storage.from_(bucket_name).upload(file_name, file)
    
    # Get the public URL of the uploaded file
    file_url = storage.from_(bucket_name).get_public_url(file_name)['publicURL']
    return file_url

# Function to log actions to the audit log
def log_audit(action, item_name, old_value, new_value):
    audit_data = {
        "action": action,
        "item_name": item_name,
        "old_value": old_value,
        "new_value": new_value,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    supabase.table("audit_log").insert(audit_data).execute()

elif page == "🛡️ Collateral":
    st.title(f"🛡️ {active_company['name']} | Asset Security Registry")
    
    # 1. Fetch Active Loans to link collateral
    loans_res = supabase.table("loans").select("*, clients(full_name)").eq("company_id", active_company['id']).neq("loan_status", "Settled").execute()

    if not loans_res.data:
        st.info("No active loans require collateral logging at this time.")
    else:
        # Collateral Registration Form
        with st.expander("📝 Register New Collateral Item", expanded=True):
            with st.form("collateral_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                # Map loan description to ID
                loan_map = {f"{l['clients']['full_name']} (Loan: {l['principal_amount']:,.0f})": l['id'] for l in loans_res.data}
                selected_loan = col1.selectbox("Link to Loan", list(loan_map.keys()))
                
                item_name = col2.text_input("Item Name (e.g., Toyota Premio Logbook)")
                est_value = col1.number_input("Estimated Market Value (UGX)", min_value=0)
                
                # Photo URL (Supabase Storage in future)
                photo_file = col2.file_uploader("Upload Photo of Collateral", type=["jpg", "jpeg", "png"])

                notes = st.text_area("Condition Notes / Serial Numbers")

                if st.form_submit_button("🔒 Secure Asset"):
                    if not item_name or est_value <= 0:
                        st.warning("Please provide all required details (Item Name, Estimated Value).")
                    elif photo_file is None:
                        st.warning("Please upload a photo of the collateral.")
                    else:
                        target_loan_id = loan_map[selected_loan]
                        
                        # Upload image to Supabase Storage and get the public URL
                        photo_url = upload_image(photo_file)
                        
                        # Insert collateral item into the database
                        data = {
                            "loan_id": target_loan_id,
                            "item_name": item_name,
                            "estimated_value": est_value,
                            "condition_notes": notes,
                            "photo_url": photo_url
                        }
                        supabase.table("collateral").insert(data).execute()

                        # Log the action to the audit log
                        log_audit(
                            action="INSERT",
                            item_name=item_name,
                            old_value="N/A",
                            new_value=str(data)
                        )
                        
                        st.success(f"✅ {item_name} has been secured to the loan ledger.")
                        st.rerun()

        # --- COLLATERAL INVENTORY ---
        st.write("---")
        st.subheader("📦 Secured Assets Inventory")
        
        collat_res = supabase.table("collateral").select("*, loans(balance_remaining, clients(full_name))").execute()
        
        if collat_res.data:
            for c in collat_res.data:
                # Math: Coverage Ratio (Is the asset worth more than the debt?)
                debt = float(c['loans']['balance_remaining'])
                value = float(c['estimated_value'])
                coverage = (value / debt * 100) if debt > 0 else 100
                
                with st.container():
                    c1, c2, c3 = st.columns([2, 1, 1])
                    
                    # Asset Information Display
                    c1.markdown(f"**{c['item_name']}**\nOwned by: {c['loans']['clients']['full_name']}")
                    c2.write(f"Value: **{value:,.0f} UGX**")
                    
                    # Color-coded coverage indicator with detailed explanation
                    if coverage < 100:
                        c3.warning(f"⚠️ Coverage: {coverage:.0f}%\nAsset value is less than remaining debt.")
                    else:
                        c3.success(f"✅ Coverage: {coverage:.0f}%\nAsset is adequately covered.")
                    
                    st.caption(f"Notes: {c['condition_notes']}")
                    if c['photo_url']:
                        st.image(c['photo_url'], caption="Photo Reference", use_column_width=True)
                    
                    # Update or Delete Button Logic
                    update_btn = st.button("Update", key=c['id'])
                    delete_btn = st.button("Delete", key=f"delete_{c['id']}")

                    if update_btn:
                        # Update logic (can be improved with a dedicated update form)
                        new_value = st.text_input(f"New Value for {c['item_name']}", value=str(c['estimated_value']))
                        if st.button("Save Update"):
                            # Log the update action
                            log_audit(
                                action="UPDATE",
                                item_name=c['item_name'],
                                old_value=str(c['estimated_value']),
                                new_value=new_value
                            )
                            supabase.table("collateral").update({"estimated_value": new_value}).eq("id", c['id']).execute()
                            st.success("Collateral item updated successfully.")
                            st.rerun()
                        
                    if delete_btn:
                        # Delete logic
                        log_audit(
                            action="DELETE",
                            item_name=c['item_name'],
                            old_value=str(c['estimated_value']),
                            new_value="N/A"
                        )
                        supabase.table("collateral").delete().eq("id", c['id']).execute()
                        st.success(f"Collateral item {c['item_name']} deleted successfully.")
                        st.rerun()

                    st.write("---")
        else:
            st.info("No collateral items found for active loans.")
elif page == "💰 Payments":
    st.title(f"💰 {active_company['name']} | Collections Engine")

    # --- FETCH ACTIVE LOANS ---
    loans = supabase.table("loans") \
        .select("*, clients(full_name)") \
        .eq("company_id", active_company['id']) \
        .neq("loan_status", "Settled") \
        .execute().data

    if loans:
        df_loans = pd.DataFrame(loans)

        st.markdown("### 📥 Record Client Payment")

        with st.form("pay_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            # --- LOAN SELECTOR ---
            l_map = {
                f"{l['clients']['full_name']} (Bal: {float(l['balance_remaining']):,.0f})": l
                for l in loans
            }

            sel = col1.selectbox("👤 Select Loan", list(l_map.keys()))

            loan = l_map[sel]
            current_balance = float(loan['balance_remaining'])

            pay_amt = col2.number_input("💵 Amount Paid (UGX)", min_value=1000, step=1000)

            # --- PAYMENT METHOD ---
            method = col1.selectbox("💳 Payment Method", ["Cash", "Mobile Money", "Bank Transfer", "Cheque"])
            ref = col2.text_input("🔖 Reference (Optional)")

            # --- LIVE PREVIEW ---
            new_balance = current_balance - pay_amt

            st.write("---")
            p1, p2 = st.columns(2)
            p1.metric("📊 Current Balance", f"{current_balance:,.0f} UGX")
            p2.metric("📉 New Balance", f"{max(new_balance,0):,.0f} UGX")

            # --- WARNINGS ---
            if pay_amt > current_balance:
                st.warning("⚠️ Overpayment detected. Excess will be ignored.")

            if pay_amt < current_balance * 0.1:
                st.info("💡 Small payment detected. Consider encouraging larger installments.")

            # --- SUBMIT ---
            if st.form_submit_button("✅ Post Payment", use_container_width=True):

                if pay_amt <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    try:
                        final_payment = min(pay_amt, current_balance)
                        new_balance = current_balance - final_payment

                        # --- UPDATE LOAN ---
                        supabase.table("loans").update({
                            "balance_remaining": max(new_balance, 0),
                            "loan_status": "Settled" if new_balance <= 0 else "Active"
                        }).eq("id", loan['id']).execute()

                        # --- RECORD TRANSACTION ---
                        supabase.table("transactions").insert({
                            "company_id": active_company['id'],
                            "loan_id": loan['id'],
                            "amount_paid": final_payment,
                            "payment_method": method,
                            "transaction_ref": ref
                        }).execute()

                        st.success(f"✅ Payment of {final_payment:,.0f} UGX recorded!")

                        # --- RECEIPT DOWNLOAD ---
                        receipt = f"""
                        PAYMENT RECEIPT
                        -------------------------
                        Client: {loan['clients']['full_name']}
                        Amount Paid: {final_payment:,.0f} UGX
                        Method: {method}
                        Reference: {ref}
                        New Balance: {max(new_balance,0):,.0f} UGX
                        Date: {datetime.now().strftime('%Y-%m-%d')}
                        """

                        st.download_button(
                            label="📥 Download Receipt",
                            data=receipt,
                            file_name="payment_receipt.txt",
                            mime="text/plain",
                            use_container_width=True
                        )

                        st.rerun()

                    except Exception as e:
                        st.error("❌ Failed to post payment.")

        # --- RECENT PAYMENTS ---
        st.write("---")
        st.markdown("### 📜 Recent Transactions")

        trans = supabase.table("transactions") \
            .select("*, loans(clients(full_name))") \
            .eq("company_id", active_company['id']) \
            .order("id", desc=True) \
            .limit(10) \
            .execute().data

        if trans:
            df_trans = pd.DataFrame([{
                "Client": t['loans']['clients']['full_name'],
                "Amount": t['amount_paid'],
                "Method": t['payment_method'],
                "Ref": t.get('transaction_ref', ''),
            } for t in trans])

            st.dataframe(
                df_trans.style.format({"Amount": "{:,.0f} UGX"}),
                use_container_width=True,
                hide_index=True
            )

    else:
        st.info("🎉 All loans are settled. No active repayments needed.")
st.title(f"🚨 {active_company['name']} | Overdue Tracker")

# Fetch active, non-settled loans
overdue = supabase.table("loans").select("*, clients(full_name)").eq("company_id", active_company['id']).neq("loan_status", "Settled").execute().data

if not overdue:
    st.info("No overdue loans at the moment.")
else:
    total_overdue = sum(float(l['balance_remaining']) for l in overdue)
    st.metric("Total Overdue Portfolio", f"{total_overdue:,.0f} UGX")

    for l in overdue:
        c1, c2, c3 = st.columns([3,1,1])
        c1.write(f"**{l['clients']['full_name']}** - Remaining: {float(l['balance_remaining']):,.0f} UGX")
        
        # Apply penalty button
        if c2.button("Apply 10% Penalty", key=f"penalty_{l['id']}"):
            penalty = float(l['monthly_installment']) * 0.1
            new_balance = float(l['balance_remaining']) + penalty
            supabase.table("loans").update({
                "balance_remaining": new_balance,
                "loan_status": "Overdue"
            }).eq("id", l['id']).execute()
            st.warning(f"Penalty of {penalty:,.0f} UGX applied!")
            st.rerun()
        
        # Rollover logic button
        if c3.button("Rollover Loan", key=f"rollover_{l['id']}"):
            new_principal = float(l['balance_remaining'])
            new_duration = int(l['duration_months'])  # optional: keep same or allow input
            new_total, new_monthly = calculate_loan(new_principal, float(l['interest_rate']), new_duration)
            supabase.table("loans").update({
                "principal_amount": new_principal,
                "total_repayable": new_total,
                "monthly_installment": new_monthly,
                "balance_remaining": new_total,
                "loan_status": "Active"
            }).eq("id", l['id']).execute()
            st.success(f"Loan rolled over! New total: {new_total:,.0f} UGX, Monthly: {new_monthly:,.0f} UGX")
            st.rerun()
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

st.title(f"📄 {active_company['name']} | Payroll Engine")

# Fetch staff
staff = get_data("clients", active_company['id'])
if not staff:
    st.warning("No staff registered yet. Please add staff to process payroll.")
    st.stop()

# Form to process payroll
with st.form("payroll_form"):
    target_staff = st.selectbox("Select Staff Member", [s['full_name'] for s in staff])
    st.subheader("Salary Details 💼")
    basic = st.number_input("Basic Salary (UGX)", min_value=100_000, step=10_000, format="%d")

    # Payroll calculations
    nssf, paye, net = calculate_uganda_payroll(basic)

    # Display metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("NSSF Contribution", f"{nssf:,.0f} UGX")
    col2.metric("PAYE Deduction", f"{paye:,.0f} UGX")
    col3.metric("Net Pay", f"{net:,.0f} UGX")
    st.markdown("---")

    if st.form_submit_button("Process Salary"):
        # Post to expenses
        supabase.table("expenses").insert({
            "company_id": active_company['id'],
            "category": "Salaries",
            "description": f"Salary for {target_staff}",
            "amount": basic
        }).execute()

        st.success(f"✅ Payroll posted for {target_staff}! Net Pay: {net:,.0f} UGX")
        st.balloons()

        # Generate payroll PDF
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, f"{active_company['name']} - Payroll Slip")
        c.setFont("Helvetica", 12)
        c.drawString(50, 770, f"Staff: {target_staff}")
        c.drawString(50, 750, f"Basic Salary: {basic:,.0f} UGX")
        c.drawString(50, 730, f"NSSF Contribution: {nssf:,.0f} UGX")
        c.drawString(50, 710, f"PAYE Deduction: {paye:,.0f} UGX")
        c.drawString(50, 690, f"Net Pay: {net:,.0f} UGX")
        c.drawString(50, 660, "Thank you for your service!")
        c.showPage()
        c.save()
        buffer.seek(0)
        st.download_button(
            label="📄 Download Payroll Slip (PDF)",
            data=buffer,
            file_name=f"{target_staff}_payroll.pdf",
            mime="application/pdf"
        )

        st.rerun()

# Monthly payroll ledger
st.subheader("📊 Monthly Payroll Ledger")
ledger = supabase.table("expenses").select("*").eq("company_id", active_company['id']).eq("category", "Salaries").execute().data
if ledger:
    df_ledger = pd.DataFrame(ledger)
    df_ledger['Amount (UGX)'] = df_ledger['amount'].apply(lambda x: f"{x:,.0f}")
    st.dataframe(df_ledger[['description', 'Amount (UGX)']], use_container_width=True)
else:
    st.info("No payroll entries found for this month.")

st.title(f"📂 {active_company['name']} | Expense Tracker")

# Expense Input Form
with st.form("exp_form"):
    st.subheader("Log New Expense 💸")
    col1, col2 = st.columns([2,3])
    with col1:
        cat = st.selectbox("Category", ["Rent", "Taxes", "Marketing", "Petty Cash", "Utilities", "Salaries", "Miscellaneous"])
    with col2:
        desc = st.text_input("Description / Notes")
    amt = st.number_input("Amount (UGX)", min_value=1000, step=1000, format="%d")

    if st.form_submit_button("Record Outflow"):
        supabase.table("expenses").insert({
            "company_id": active_company['id'],
            "category": cat,
            "description": desc,
            "amount": amt
        }).execute()
        st.success(f"✅ Expense of {amt:,.0f} UGX recorded under {cat}")
        st.rerun()

st.markdown("---")

# Fetch and display expenses
expenses = get_data("expenses", active_company['id'])
if expenses:
    df_exp = pd.DataFrame(expenses)
    df_exp['Amount (UGX)'] = df_exp['amount'].apply(lambda x: f"{x:,.0f}")
    st.subheader("📊 Expense Ledger")
    st.dataframe(df_exp[['category', 'description', 'Amount (UGX)']], use_container_width=True)

    # Analytics: Category-wise spend
    st.subheader("📈 Category-wise Spend")
    import plotly.express as px
    cat_df = df_exp.groupby('category')['amount'].sum().reset_index()
    fig = px.bar(cat_df, x='category', y='amount', text='amount', color='category',
                 color_discrete_sequence=px.colors.qualitative.Pastel, title="Total Spend by Category")
    fig.update_layout(yaxis_title="Amount (UGX)", xaxis_title="Category", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No expenses logged yet. Start by recording an outflow above.")



import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
from io import BytesIO
import datetime

# Helper function to generate PDF
def generate_pdf(client_name, total_borrowed, total_paid, current_balance, history_df, company_name="Your Company"):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Title
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(200, 10, f"{company_name} - Client Statement", ln=True, align='C')
    pdf.ln(10)
    
    # Client Info
    pdf.set_font('Arial', '', 12)
    pdf.cell(200, 10, f"Client: {client_name}", ln=True)
    pdf.cell(200, 10, f"Date: {datetime.datetime.now().strftime('%B %d, %Y')}", ln=True)
    pdf.ln(10)
    
    # Financial Summary
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(200, 10, "📊 Financial Summary", ln=True)
    pdf.set_font('Arial', '', 12)
    pdf.cell(200, 10, f"Total Borrowed: {total_borrowed:,.0f} UGX", ln=True)
    pdf.cell(200, 10, f"Total Repaid: {total_paid:,.0f} UGX", ln=True)
    pdf.cell(200, 10, f"Outstanding Debt: {current_balance:,.0f} UGX", ln=True)
    pdf.ln(10)
    
    # Transaction History Table
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 10, "Date", border=1)
    pdf.cell(50, 10, "Transaction Type", border=1)
    pdf.cell(40, 10, "Debit (UGX)", border=1)
    pdf.cell(40, 10, "Credit (UGX)", border=1)
    pdf.cell(30, 10, "Reference", border=1)
    pdf.ln()
    
    pdf.set_font('Arial', '', 10)
    for _, row in history_df.iterrows():
        pdf.cell(40, 10, str(row['Date']), border=1)
        pdf.cell(50, 10, row['Type'], border=1)
        pdf.cell(40, 10, f"{row['Debit']:.0f}", border=1)
        pdf.cell(40, 10, f"{row['Credit']:.0f}", border=1)
        pdf.cell(30, 10, row['Ref'], border=1)
        pdf.ln()
    
    # Save to BytesIO
    pdf_output = BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    
    return pdf_output

# Streamlit page logic
if page == "📄 Ledger":
    st.title(f"📄 {active_company['name']} | Client Statements")
    
    # 1. Select the Client
    clients_res = supabase.table("clients").select("id, full_name").eq("company_id", active_company['id']).execute()
    
    if not clients_res.data:
        st.info("No clients registered yet.")
    else:
        client_map = {c['full_name']: c['id'] for c in clients_res.data}
        target_name = st.selectbox("Search Client for Statement", list(client_map.keys()))
        target_id = client_map[target_name]

        # 2. Fetch History
        loans, payments = get_client_statement(target_id)

        if not loans:
            st.warning("This client has no loan history.")
        else:
            st.write(f"### 📊 Financial Summary: {target_name}")
            
            # --- OVERVIEW METRICS ---
            total_borrowed = sum(float(l['principal_amount']) for l in loans)
            current_balance = sum(float(l['balance_remaining']) for l in loans)
            total_paid = sum(float(p['amount_paid']) for p in payments)

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Principal Taken", f"{total_borrowed:,.0f} UGX")
            c2.metric("Total Repaid to Date", f"{total_paid:,.0f} UGX", delta=f"{total_paid/total_borrowed*100:.1f}% Recovery")
            c3.metric("Outstanding Debt", f"{current_balance:,.0f} UGX", delta_color="inverse")

            # --- THE TRANSACTION TIMELINE ---
            st.write("---")
            st.subheader("📑 Chronological Statement of Account")
            
            # Combine Loans and Payments into one list for the "Trend"
            history = []
            for l in loans:
                history.append({"Date": l['disbursement_date'], "Type": "LOAN DISBURSED", "Debit": l['total_repayable'], "Credit": 0, "Ref": "System Gen"})
            for p in payments:
                history.append({"Date": p['payment_date'][:10], "Type": "PAYMENT RECEIVED", "Debit": 0, "Credit": p['amount_paid'], "Ref": p['transaction_ref']})
            
            df_history = pd.DataFrame(history).sort_values(by="Date")
            
            # Format the table for the "Luxe" feel
            st.dataframe(df_history.style.format({
                "Debit": "{:,.0f}", "Credit": "{:,.0f}"
            }).set_properties(**{'background-color': '#ffffff', 'color': '#000000'}), use_container_width=True, hide_index=True)

            # --- DOWNLOADABLE PDF/CSV LOGIC ---
            csv = df_history.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Download {target_name}'s Statement (CSV)",
                data=csv,
                file_name=f"{target_name}_Statement.csv",
                mime='text/csv',
                use_container_width=True
            )
            
            # Button to generate and download PDF statement
            if st.button(f"📥 Download {target_name}'s Statement (PDF)"):
                pdf_output = generate_pdf(target_name, total_borrowed, total_paid, current_balance, df_history)
                st.download_button(
                    label=f"Download PDF Statement for {target_name}",
                    data=pdf_output,
                    file_name=f"{target_name}_Statement.pdf",
                    mime="application/pdf"
                )

            # --- CHARTS ---
            st.write("---")
            st.subheader("📊 Loan and Payment Trends")
            
            # Pie chart of loan statuses
            loan_statuses = pd.DataFrame(loans)
            loan_status_pie = px.pie(loan_statuses, names='loan_status', values='balance_remaining', hole=0.3, title="Loan Status Distribution")
            st.plotly_chart(loan_status_pie, use_container_width=True)
            
            # Bar chart of payments over time
            payments_df = pd.DataFrame(payments)
            payments_df['payment_date'] = pd.to_datetime(payments_df['payment_date'])
            payments_bar = px.bar(payments_df, x='payment_date', y='amount_paid', title="Payments Over Time")
            st.plotly_chart(payments_bar, use_container_width=True)


elif page == "🧾 Reports":
    st.title("🧾 P&L and Balance Sheet")
    
    # Fetching metrics
    loans, payments, expenses = get_dashboard_metrics(active_company['id'])
    
    # Revenue: Total Interest Revenue
    rev = sum((float(l['total_repayable']) - float(l['principal_amount'])) for l in loans)
    
    # Operating Expenses
    opex = sum(float(e['amount']) for e in expenses)
    
    # Net Profit Calculation
    net_profit = rev - opex
    
    # --- Enhanced Layout with Cards for Key Metrics ---
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Interest Revenue", f"{rev:,.0f} UGX")
    with c2:
        st.metric("Total Operating Expenses", f"{opex:,.0f} UGX")
    with c3:
        st.metric("Net Profit", f"{net_profit:,.0f} UGX", delta=f"{'+' if net_profit >= 0 else ''}{net_profit:,.0f} UGX")

    # --- Profit and Loss Statement ---
    st.subheader("📊 Profit & Loss Statement")
    
    st.write(f"**Total Interest Revenue**: {rev:,.0f} UGX")
    st.write(f"**Total Operating Expenses**: {opex:,.0f} UGX")
    
    # --- Net Profit Visualization ---
    st.write(f"---")
    if net_profit >= 0:
        st.success(f"**Net Profit**: {net_profit:,.0f} UGX")
    else:
        st.error(f"**Net Loss**: {abs(net_profit):,.0f} UGX")
    
    # --- Additional Visualization for Better Insight ---
    # Bar chart to visualize income vs expenses
    df_report = pd.DataFrame({
        'Category': ['Interest Revenue', 'Operating Expenses', 'Net Profit'],
        'Amount': [rev, opex, net_profit]
    })
    
    st.bar_chart(df_report.set_index('Category')['Amount'])
    
    # --- Option for Downloading Report ---
    report_data = f"Interest Revenue: {rev:,.0f} UGX\nOperating Expenses: {opex:,.0f} UGX\nNet Profit: {net_profit:,.0f} UGX"
    st.download_button(
        label="📥 Download P&L Report",
        data=report_data,
        file_name=f"{active_company['name']}_PnL_Report.txt",
        mime="text/plain",
        use_container_width=True
    )

