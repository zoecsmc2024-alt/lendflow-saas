import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import datetime

# --- 1. CONFIG & SAAS THEME ENGINE ---
st.set_page_config(page_title="Peak-Lenders Africa", layout="wide", page_icon="🌍")

if 'theme_color' not in st.session_state:
    st.session_state.theme_color = "#1E3A8A" # Peak-Lenders Blue

def apply_custom_theme(color):
    st.markdown(f"""
        <style>
        /* Sidebar background */
        [data-testid="stSidebar"] {{
            background-color: {color} !important;
        }}
        
        /* Make ALL sidebar text white */
        [data-testid="stSidebar"] *, [data-testid="stSidebarNav"] span {{
            color: white !important;
        }}

        /* Label above the box stays white */
        [data-testid="stWidgetLabel"] p {{
            color: white !important;
        }}

        /* The text INSIDE the white selection box should be DARK */
        div[data-baseweb="select"] * {{
            color: #1E3A8A !important; /* This makes the company name readable */
        }}
        
        /* Ensure the dropdown options are also readable */
        ul[data-testid="stSelectboxVirtualList"] * {{
            color: #1E3A8A !important;
        }}

        /* Make the "Switch Business Portal" text white */
        .stSelectbox label p {{
            color: white !important;
        }}

        /* Metric cards on the main dashboard */
        div[data-testid="stMetric"] {{
            background-color: white;
            padding: 15px;
            border-radius: 10px;
            border-left: 5px solid {color};
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        /* Dashboard titles */
        h1, h2, h3 {{
            color: {color};
        }}
        </style>
    """, unsafe_allow_html=True)
# --- 2. SUPABASE CONNECTION ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

# --- 3. MATH & ACCOUNTING HELPERS ---
def calculate_uganda_payroll(basic):
    nssf_5 = float(basic) * 0.05
    taxable = float(basic) - nssf_5
    paye = 0
    if taxable > 410000: paye = (taxable - 410000) * 0.3 + 25000
    elif taxable > 335000: paye = (taxable - 335000) * 0.2 + 10000
    elif taxable > 235000: paye = (taxable - 235000) * 0.1
    return nssf_5, paye, (float(basic) - nssf_5 - paye)

def calculate_loan(principal, rate, months):
    interest = float(principal) * (float(rate)/100) * (float(months)/12)
    total = float(principal) + interest
    return round(total), round(total/months)

# --- 4. DATA FETCHING (TENANT ISOLATED) ---
def get_data(table, company_id):
    return supabase.table(table).select("*").eq("company_id", company_id).execute().data

# --- 1. SETTINGS & AUTH (The Brain) ---
companies_res = supabase.table("companies").select("id, name, brand_color").execute()
company_list = {c['name']: c for c in companies_res.data}

with st.sidebar:
    st.title("🌍 Peak-Lenders Africa")
    st.write("---")
    
    # Selecting the Company/Tenant
    active_company_name = st.selectbox("Log in as:", list(company_list.keys()))
    active_company = company_list[active_company_name]
    
    # Applying branding immediately
    apply_custom_theme(active_company['brand_color'])
    
    st.success(f"Mode: {active_company['name']}")
    st.write("---")
    
    # GLOBAL NAVIGATION (Always visible here!)
    page = st.radio("Navigation Menu", [
        "📈 Overview", 
        "👥 Clients", 
        "💵 Loans", 
        "💰 Payments", 
        "🚨 Overdue", 
        "🛡️ Collateral", 
        "📂 Expenses", 
        "📄 Payroll", 
        "📄 Ledger", 
        "🧾 Reports"
    ])

# --- 2. THE SWITCHBOARD (Only shows the selected page) ---

if page == "📈 Overview":
    st.title(f"📈 {active_company['name']} | Executive Overview")
    
    # Fetch Data
    loans, payments, expenses = get_dashboard_metrics(active_company['id'])
    
    if not loans:
        st.info("Welcome! Start by registering a client and issuing your first loan.")
    else:
        # Dashboard Math
        total_balance = sum(float(l['balance_remaining']) for l in loans)
        total_collected = sum(float(p['amount_paid']) for p in payments)
        total_opex = sum(float(e['amount']) for e in expenses)
        net_cash = total_collected - total_opex

        # Metrics Row
        c1, c2, c3 = st.columns(3)
        c1.metric("Active Portfolio (PAR)", f"{total_balance:,.0f} UGX")
        c2.metric("Total Collections", f"{total_collected:,.0f} UGX")
        c3.metric("Net Cash Position", f"{net_cash:,.0f} UGX")

        # Visuals
        st.write("---")
        col_left, col_right = st.columns(2)
        with col_left:
            fig_status = px.pie(pd.DataFrame(loans), names='loan_status', values='balance_remaining', hole=.5,
                                color_discrete_map={'Active': active_company['brand_color'], 'Overdue': '#D32F2F'})
            st.plotly_chart(fig_status, use_container_width=True)
        with col_right:
            if expenses:
                st.plotly_chart(px.bar(pd.DataFrame(expenses), x='category', y='amount'), use_container_width=True)

elif page == "👥 Clients":
    st.title(f"👥 {active_company['name']} | Client Registry")
    
    tab1, tab2 = st.tabs(["➕ Register New Client", "📋 Active Client Database"])

    with tab1:
        with st.form("client_onboarding", clear_on_submit=True):
            col1, col2 = st.columns(2)
            f_name = col1.text_input("Full Name / Business Name")
            id_no = col2.text_input("National ID / Passport No.")
            phone = col1.text_input("Phone Number")
            email = col2.text_input("Email Address")
            
            if st.form_submit_button("🛡️ Securely Register Client"):
                if f_name and id_no:
                    client_data = {
                        "company_id": active_company['id'],
                        "full_name": f_name,
                        "id_number": id_no,
                        "phone_number": phone,
                        "email": email
                    }
                    supabase.table("clients").insert(client_data).execute()
                    st.success(f"✅ {f_name} added!")
                    st.rerun()

    with tab2:
        clients_res = supabase.table("clients").select("*").eq("company_id", active_company['id']).execute()
        if clients_res.data:
            st.dataframe(pd.DataFrame(clients_res.data)[["full_name", "id_number", "phone_number"]], use_container_width=True)
        else:
            st.info("No clients found.")



# --- 7. PAGE LOGIC: CLIENTS ---
elif page == "👥 Clients":
    st.title("👥 Client Registry")
    with st.expander("Register New Borrower"):
        with st.form("client_reg"):
            name = st.text_input("Full Name")
            nid = st.text_input("National ID")
            phone = st.text_input("Phone")
            if st.form_submit_button("Save Client"):
                supabase.table("clients").insert({"company_id": active_company['id'], "full_name": name, "id_number": nid, "phone_number": phone}).execute()
                st.rerun()
    clients = get_data("clients", active_company['id'])
    if clients: st.table(pd.DataFrame(clients)[["full_name", "id_number", "phone_number"]])

# --- 8. PAGE LOGIC: LOANS ---
elif page == "💵 Loans":
    st.title(f"💵 {active_company['name']} | Credit Engine")
    
    # 1. Fetch Active Clients for this Company
    clients_res = supabase.table("clients").select("id, full_name").eq("company_id", active_company['id']).execute()
    
    if not clients_res.data:
        st.warning("⚠️ No clients found. Please register a Borrower first.")
    else:
        # --- SECTION 1: ISSUE NEW LOAN ---
        with st.expander("🚀 Create New Loan Agreement", expanded=False):
            with st.form("loan_issue_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                # Select Client from the Database
                client_names = {c['full_name']: c['id'] for c in clients_res.data}
                selected_client = col1.selectbox("Select Borrower", list(client_names.keys()))
                
                principal = col2.number_input("Principal Amount (UGX)", min_value=1000, step=50000)
                
                rate = col1.number_input("Annual Interest Rate (%)", min_value=1.0, value=15.0)
                duration = col2.number_input("Duration (Months)", min_value=1, value=6)
                
                # Dynamic Math Preview
                total_repayable, installment = calculate_loan_totals(principal, rate, duration)
                
                st.info(f"💡 **Loan Summary:** Total Repayable: {total_repayable:,.0f} UGX | Monthly: {installment:,.0f} UGX")
                
                if st.form_submit_button("💳 Disburse Loan"):
                    loan_data = {
                        "company_id": active_company['id'],
                        "client_id": client_names[selected_client],
                        "principal_amount": principal,
                        "interest_rate": rate,
                        "duration_months": duration,
                        "total_repayable": total_repayable,
                        "monthly_installment": installment,
                        "balance_remaining": total_repayable,
                        "loan_status": "Active"
                    }
                    res = supabase.table("loans").insert(loan_data).execute()
                    if res.data:
                        st.success(f"✅ Loan successfully disbursed to {selected_client}!")
                        st.rerun()

        # --- SECTION 2: ACTIVE LOAN LEDGER ---
        st.write("---")
        st.subheader("📑 Active Loan Portfolio")
        
        # Fetch Loans with Client Names (The Relational "Join")
        loans_res = supabase.table("loans").select("*, clients(full_name)").eq("company_id", active_company['id']).execute()
        
        if loans_res.data:
            df_loans = pd.DataFrame([{
                "Borrower": l['clients']['full_name'],
                "Principal": l['principal_amount'],
                "Balance": l['balance_remaining'],
                "Monthly": l['monthly_installment'],
                "Status": l['loan_status']
            } for l in loans_res.data])
            
            st.dataframe(df_loans.style.format({
                "Principal": "{:,.0f}", "Balance": "{:,.0f}", "Monthly": "{:,.0f}"
            }), use_container_width=True, hide_index=True)
            
            # THE "CLEAR NUMBERS" TOTAL FOR THE BOSS
            total_portfolio = sum(l['balance_remaining'] for l in loans_res.data)
            st.markdown(f"""<div style="background-color:{active_company['brand_color']}; color:white; padding:15px; border-radius:10px; text-align:right;">
                <p style="margin:0;">TOTAL OUTSTANDING BALANCE (PORTFOLIO AT RISK)</p>
                <h2 style="margin:0; color:white;">{total_portfolio:,.0f} UGX</h2>
            </div>""", unsafe_allow_html=True)



elif page == "🛡️ Collateral":
    st.title(f"🛡️ {active_company['name']} | Asset Security Registry")
    
    # 1. Fetch Active Loans to link collateral
    loans_res = supabase.table("loans").select("*, clients(full_name)").eq("company_id", active_company['id']).neq("loan_status", "Settled").execute()

    if not loans_res.data:
        st.info("No active loans require collateral logging at this time.")
    else:
        with st.expander("📝 Register New Collateral Item"):
            with st.form("collateral_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                # Map loan description to ID
                loan_map = {f"{l['clients']['full_name']} (Loan: {l['principal_amount']:,.0f})": l['id'] for l in loans_res.data}
                selected_loan = col1.selectbox("Link to Loan", list(loan_map.keys()))
                
                item_name = col2.text_input("Item Name (e.g., Toyota Premio Logbook)")
                est_value = col1.number_input("Estimated Market Value (UGX)", min_value=0)
                
                # In the future, we will use Supabase Storage for this URL
                photo_url = col2.text_input("Photo Reference / Cloud Link")
                
                notes = st.text_area("Condition Notes / Serial Numbers")

                if st.form_submit_button("🔒 Secure Asset"):
                    target_loan_id = loan_map[selected_loan]
                    data = {
                        "loan_id": target_loan_id,
                        "item_name": item_name,
                        "estimated_value": est_value,
                        "condition_notes": notes,
                        "photo_url": photo_url
                    }
                    supabase.table("collateral").insert(data).execute()
                    st.success(f"✅ {item_name} has been locked to the loan ledger.")
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
                    c1.markdown(f"**{c['item_name']}**\nOwned by: {c['loans']['clients']['full_name']}")
                    c2.write(f"Value: **{value:,.0f} UGX**")
                    
                    # Color-coded coverage indicator
                    if coverage < 100:
                        c3.warning(f"⚠️ Coverage: {coverage:.0f}%")
                    else:
                        c3.success(f"✅ Coverage: {coverage:.0f}%")
                    
                    st.caption(f"Notes: {c['condition_notes']}")
                    st.write("---")

# --- 9. PAGE LOGIC: PAYMENTS ---
elif page == "💰 Payments":
    st.title(f"💰 {active_company['name']} | Payment Collections")
    
    # Fetch only Active Loans for this company
    active_loans = supabase.table("loans").select("*, clients(full_name)").eq("company_id", active_company['id']).neq("loan_status", "Settled").execute()

    if not active_loans.data:
        st.info("🎉 No active debts! All loans are currently settled.")
    else:
        with st.container():
            st.markdown(f"""<div style="border-left: 5px solid {active_company['brand_color']}; padding-left:15px;">
                <h4>📥 Record Client Repayment</h4></div>""", unsafe_allow_html=True)
            
            with st.form("payment_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                # Create a map of "Client Name (Balance)" to Loan ID
                loan_map = {f"{l['clients']['full_name']} (Bal: {l['balance_remaining']:,.0f})": l['id'] for l in active_loans.data}
                selected_loan_label = col1.selectbox("Select Active Loan", list(loan_map.keys()))
                
                amount = col2.number_input("Amount Paid (UGX)", min_value=500, step=1000)
                
                method = col1.selectbox("Payment Method", ["Cash", "Mobile Money", "Bank Transfer", "Cheque"])
                ref = col2.text_input("Transaction Reference (e.g., MM ID or Receipt No)")

                if st.form_submit_button("✅ Post Payment & Update Balance", use_container_width=True):
                    record_payment(loan_map[selected_loan_label], amount, method, ref)
                    st.success(f"✅ Payment of {amount:,.0f} posted. Balance updated!")
                    st.rerun()

        # --- RECENT TRANSACTIONS TABLE ---
        st.write("---")
        st.subheader("📜 Recent Collections Ledger")
        
        trans_res = supabase.table("transactions").select("*, loans(clients(full_name))").eq("company_id", active_company['id']).order("payment_date", desc=True).limit(10).execute()
        
        if trans_res.data:
            df_trans = pd.DataFrame([{
                "Date": t['payment_date'][:10],
                "Client": t['loans']['clients']['full_name'],
                "Amount": t['amount_paid'],
                "Method": t['payment_method'],
                "Ref": t['transaction_ref']
            } for t in trans_res.data])
            
            st.dataframe(df_trans.style.format({"Amount": "{:,.0f} UGX"}), use_container_width=True, hide_index=True)



elif page == "🚨 Overdue Tracker":
    st.title(f"🚨 {active_company['name']} | Risk Monitor")
    
    # Fetch Loans that are NOT settled
    overdue_res = supabase.table("loans").select("*, clients(full_name, phone_number)").eq("company_id", active_company['id']).neq("loan_status", "Settled").execute()
    
    if not overdue_res.data:
        st.success("✅ Clean Slate: No loans are currently flagged as at-risk.")
    else:
        st.subheader("🚩 Potentially Overdue Accounts")
        
        for l in overdue_res.data:
            with st.container():
                c1, c2, c3 = st.columns([2, 1, 1])
                
                c1.markdown(f"**{l['clients']['full_name']}** \n📞 {l['clients']['phone_number']}")
                c2.metric("Remaining Balance", f"{l['balance_remaining']:,.0f} UGX")
                
                # THE ROLLOVER TRIGGER
                if c3.button("🔄 Apply Rollover", key=f"roll_{l['id']}"):
                    penalty = apply_rollover(l['id'], l['monthly_installment'])
                    st.warning(f"Rollover Applied! {penalty:,.0f} UGX penalty added to {l['clients']['full_name']}.")
                    st.rerun()
                
                st.write("---")

        # --- RISK VISUALIZATION ---
        import pandas as pd
        df_risk = pd.DataFrame(overdue_res.data)
        st.write("### 📉 Portfolio Risk Concentration")
        
        # Simple chart showing which status has the most money tied up
        fig = px.pie(df_risk, values='balance_remaining', names='loan_status', 
                     color_discrete_map={'Active': '#2E7D32', 'Overdue': '#D32F2F'},
                     hole=.4)
        st.plotly_chart(fig, use_container_width=True)

# --- 10. PAGE LOGIC: LEDGER ---
elif page == "📄 Ledger":
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

elif page == "📂 Expenses":
    st.title(f"📂 {active_company['name']} | Operational Expenses")
    
    with st.expander("➕ Log New Business Expense"):
        with st.form("expense_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            cat = col1.selectbox("Category", ["Rent", "Salaries", "Taxes", "Marketing", "Legal", "Utilities"])
            amount = col2.number_input("Amount (UGX)", min_value=1000, step=5000)
            
            desc = st.text_input("Description (e.g., April Office Rent)")
            date = st.date_input("Transaction Date")
            
            if st.form_submit_button("📤 Record Expense"):
                data = {
                    "company_id": active_company['id'],
                    "category": cat,
                    "description": desc,
                    "amount": amount,
                    "expense_date": str(date)
                }
                supabase.table("expenses").insert(data).execute()
                st.success("Expense logged successfully!")
                st.rerun()

    # --- EXPENSE ANALYTICS ---
    st.write("---")
    exp_res = supabase.table("expenses").select("*").eq("company_id", active_company['id']).execute()
    
    if exp_res.data:
        df_exp = pd.DataFrame(exp_res.data)
        st.subheader("📊 Spending by Category")
        
        # Quick pie chart for the Boss to see where the money goes
        fig = px.pie(df_exp, values='amount', names='category', 
                     color_discrete_sequence=px.colors.sequential.RdBu)
        st.plotly_chart(fig, use_container_width=True)
        
        st.dataframe(df_exp[["expense_date", "category", "description", "amount"]].sort_values("expense_date", ascending=False), use_container_width=True, hide_index=True)



elif page == "💸 PettyCash":
    st.title(f"💸 {active_company['name']} | Petty Cash Voucher")
    
    # Logic: We track Petty Cash in the same expenses table but with a specific 'Petty' flag
    st.info("💡 Use this for small office expenditures that don't require a formal invoice.")
    
    with st.container():
        c1, c2 = st.columns([2,1])
        with c1:
            item = st.text_input("What was the money for?", placeholder="e.g., Office Tea & Sugar")
            p_amount = st.number_input("Amount Spent", min_value=500, step=500)
        with c2:
            st.write("### Cash Out")
            if st.button("💸 Confirm Voucher", use_container_width=True):
                if item and p_amount:
                    supabase.table("expenses").insert({
                        "company_id": active_company['id'],
                        "category": "Petty Cash",
                        "description": item,
                        "amount": p_amount
                    }).execute()
                    st.success("Cash Voucher Saved!")
                    st.rerun()

    st.write("---")
    st.subheader("📝 Today's Cash Movements")
    # Fetch only 'Petty Cash' category for today
    today = datetime.now().strftime("%Y-%m-%d")
    petty_res = supabase.table("expenses").select("*").eq("company_id", active_company['id']).eq("category", "Petty Cash").eq("expense_date", today).execute()
    
    if petty_res.data:
        st.table(pd.DataFrame(petty_res.data)[["description", "amount"]])
        total_today = sum(p['amount'] for p in petty_res.data)
        st.warning(f"Total Petty Cash Out Today: **{total_today:,.0f} UGX**")

elif page == "📄 Payroll":
    st.title(f"📄 {active_company['name']} | Payroll Engine")
    
    # 1. Fetch Employees for this company
    employees_res = supabase.table("clients").select("*").eq("company_id", active_company['id']).execute()
    
    if not employees_res.data:
        st.warning("⚠️ No employees found. Please add staff in the Client/Employee Registry first.")
    else:
        with st.container():
            st.markdown(f"""<div style="border-left: 5px solid {active_company['brand_color']}; padding-left:15px;">
                <h4>📅 Process Monthly Salaries</h4></div>""", unsafe_allow_html=True)
            
            with st.form("payroll_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                emp_names = {e['full_name']: e['id'] for e in employees_res.data}
                selected_emp = col1.selectbox("Select Staff Member", list(emp_names.keys()))
                
                month = col2.selectbox("Payroll Month", ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])
                basic_salary = col1.number_input("Basic Salary (UGX)", min_value=100000, step=50000)
                allowances = col2.number_input("Allowances/Bonus", min_value=0)

                # Live Math Preview
                nssf, paye, net = calculate_uganda_payroll(basic_salary + allowances)
                
                st.write("---")
                c1, c2, c3 = st.columns(3)
                c1.write(f"**NSSF (5%):**\n{nssf:,.0f}")
                c2.write(f"**PAYE Tax:**\n{paye:,.0f}")
                c3.write(f"**NET PAYOUT:**\n### {net:,.0f} UGX")

                if st.form_submit_button("🏦 Confirm & Post to Expenses", use_container_width=True):
                    # 1. Log to Expenses (So it reduces the company's net profit)
                    supabase.table("expenses").insert({
                        "company_id": active_company['id'],
                        "category": "Salaries",
                        "description": f"Salary for {selected_emp} - {month}",
                        "amount": basic_salary + allowances
                    }).execute()
                    
                    st.success(f"✅ Payroll processed for {selected_emp}! Disbursement recorded.")
                    st.rerun()

        # --- PAYROLL HISTORY ---
        st.write("---")
        st.subheader("📜 Salary Disbursement History")
        # Pull from the expenses table where category is 'Salaries'
        salary_logs = supabase.table("expenses").select("*").eq("company_id", active_company['id']).eq("category", "Salaries").execute()
        
        if salary_logs.data:
            df_pay = pd.DataFrame(salary_logs.data)
            st.dataframe(df_pay[["expense_date", "description", "amount"]], use_container_width=True, hide_index=True)

elif page == "📈 Reports":
    st.title(f"🧾 {active_company['name']} | Financial Statements")
    
    loans, payments, expenses = get_accounting_data(active_company['id'])
    
    report_type = st.segmented_control("Select Statement", ["Profit & Loss", "Balance Sheet", "Tax Summary"], default="Profit & Loss")

    # --- PROFIT & LOSS (P&L) ---
    if report_type == "Profit & Loss":
        st.subheader("📊 Income Statement (P&L)")
        st.caption("Period: Year-to-Date")
        
        # Revenue Calculation (Interest + Fees)
        interest_income = sum((float(l['total_repayable']) - float(l['principal_amount'])) for l in loans)
        other_income = 0 # Future fees
        total_revenue = interest_income + other_income
        
        # Expenses Calculation
        total_opex = sum(float(e['amount']) for e in expenses)
        net_profit = total_revenue - total_opex
        
        # The Luxe P&L Table
        pl_data = [
            {"Account": "TOTAL INTEREST REVENUE", "Amount": f"{total_revenue:,.0f} UGX"},
            {"Account": "LESS: OPERATING EXPENSES", "Amount": f"({total_opex:,.0f}) UGX"},
            {"Account": "NET OPERATING PROFIT", "Amount": f"**{net_profit:,.0f} UGX**"}
        ]
        st.table(pd.DataFrame(pl_data))
        
        if net_profit > 0:
            st.success(f"📈 Profit Margin: {(net_profit/total_revenue*100 if total_revenue > 0 else 0):.1f}%")
        else:
            st.error("📉 Warning: Operating at a Loss")

    # --- BALANCE SHEET ---
    elif report_type == "Balance Sheet":
        st.subheader("⚖️ Statement of Financial Position")
        
        # Assets: Cash + Outstanding Loans
        cash_collected = sum(float(p['amount_paid']) for p in payments)
        cash_spent = sum(float(e['amount']) for e in expenses)
        cash_at_hand = cash_collected - cash_spent
        
        portfolio_value = sum(float(l['balance_remaining']) for l in loans)
        total_assets = cash_at_hand + portfolio_value
        
        # Display as a formal Balance Sheet
        col_a, col_b = st.columns(2)
        with col_a:
            st.write("### ASSETS")
            st.write(f"Cash & Equivalents: **{cash_at_hand:,.0f}**")
            st.write(f"Net Loan Portfolio: **{portfolio_value:,.0f}**")
            st.markdown(f"--- \n **TOTAL ASSETS: {total_assets:,.0f} UGX**")
            
        with col_b:
            st.write("### EQUITY & LIABILITIES")
            st.write(f"Retained Earnings: **{total_assets:,.0f}**")
            st.write(f"External Liabilities: **0**")
            st.markdown(f"--- \n **TOTAL EQUITY: {total_assets:,.0f} UGX**")

    # --- DOWNLOAD SECTION ---
    st.write("---")
    csv_report = pd.DataFrame(loans).to_csv().encode('utf-8')
    st.download_button(
        label="📥 Download Certified Audit Report (CSV)",
        data=csv_report,
        file_name=f"{active_company['name']}_Financials.csv",
        mime='text/csv',
        use_container_width=True
    )
