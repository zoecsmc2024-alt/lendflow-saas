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

        /* Style the radio button labels specifically */
        [data-testid="stWidgetLabel"] p {{
            color: white !important;
        }}

        /* Make the "Switch Business Portal" text white */
        .stSelectbox label p {{
            color: white !important;
        }

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

# --- 5. SIDEBAR & AUTH SIMULATION ---
companies = supabase.table("companies").select("*").execute().data
with st.sidebar:
    st.title("🌍 Peak-Lenders")
    if companies:
        company_names = {c['name']: c for c in companies}
        active_name = st.selectbox("Switch Business Portal", list(company_names.keys()))
        active_company = company_names[active_name]
        apply_custom_theme(active_company['brand_color'])
    else:
        st.error("No companies found. Use SuperAdmin to onboard.")
        st.stop()
    
    page = st.radio("Navigation", ["📈 Overview", "👥 Clients", "💵 Loans", "💰 Payments", "🚨 Overdue", "🛡️ Collateral", "📂 Expenses", "📄 Payroll", "📄 Ledger", "🧾 Reports"])

# --- 6. PAGE LOGIC: DASHBOARD ---
if page == "📈 Overview":
    st.title(f"📈 {active_company['name']} Dashboard")
    loans = get_data("loans", active_company['id'])
    payments = get_data("transactions", active_company['id'])
    
    c1, c2, c3 = st.columns(3)
    total_out = sum(float(l['balance_remaining']) for l in loans) if loans else 0
    total_in = sum(float(p['amount_paid']) for p in payments) if payments else 0
    
    c1.metric("Portfolio at Risk", f"{total_out:,.0f} UGX")
    c2.metric("Total Recovered", f"{total_in:,.0f} UGX")
    c3.metric("Active Clients", len(loans) if loans else 0)
    
    if loans:
        df_loans = pd.DataFrame(loans)
        st.plotly_chart(px.pie(df_loans, names='loan_status', values='balance_remaining', hole=.4, color_discrete_sequence=[active_company['brand_color'], '#D32F2F', '#2E7D32']), use_container_width=True)

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
    st.title("💵 Credit Engine")
    clients = get_data("clients", active_company['id'])
    if not clients: st.warning("Register a client first."); st.stop()
    
    with st.form("loan_form"):
        c_map = {c['full_name']: c['id'] for c in clients}
        target = st.selectbox("Select Borrower", list(c_map.keys()))
        p = st.number_input("Principal", min_value=10000)
        r = st.number_input("Annual Interest %", value=15.0)
        m = st.number_input("Months", value=6)
        if st.form_submit_button("Disburse Loan"):
            total, monthly = calculate_loan(p, r, m)
            supabase.table("loans").insert({"company_id": active_company['id'], "client_id": c_map[target], "principal_amount": p, "interest_rate": r, "duration_months": m, "total_repayable": total, "monthly_installment": monthly, "balance_remaining": total}).execute()
            st.success("Loan Disbursed!"); st.rerun()

# --- 9. PAGE LOGIC: PAYMENTS ---
elif page == "💰 Payments":
    st.title("💰 Collection Ledger")
    loans = supabase.table("loans").select("*, clients(full_name)").eq("company_id", active_company['id']).neq("loan_status", "Settled").execute().data
    if loans:
        with st.form("pay_form"):
            l_map = {f"{l['clients']['full_name']} (Bal: {l['balance_remaining']:,.0f})": l for l in loans}
            sel = st.selectbox("Select Loan", list(l_map.keys()))
            amt = st.number_input("Amount Paid", min_value=1000)
            if st.form_submit_button("Post Payment"):
                loan = l_map[sel]
                new_bal = float(loan['balance_remaining']) - float(amt)
                supabase.table("loans").update({"balance_remaining": new_bal, "loan_status": "Settled" if new_bal <= 0 else "Active"}).eq("id", loan['id']).execute()
                supabase.table("transactions").insert({"company_id": active_company['id'], "loan_id": loan['id'], "amount_paid": amt, "payment_method": "Manual"}).execute()
                st.rerun()

# --- 10. PAGE LOGIC: LEDGER ---
elif page == "📄 Ledger":
    st.title("📄 Client Statements")
    clients = get_data("clients", active_company['id'])
    target = st.selectbox("Select Client", [c['full_name'] for c in clients])
    cid = [c['id'] for c in clients if c['full_name'] == target][0]
    
    l_data = supabase.table("loans").select("*").eq("client_id", cid).execute().data
    p_data = supabase.table("transactions").select("*, loans(client_id)").eq("loans.client_id", cid).execute().data
    
    st.write(f"### Statement for {target}")
    hist = [{"Date": x['disbursement_date'], "Action": "Loan", "Debit": x['total_repayable'], "Credit": 0} for x in l_data]
    hist += [{"Date": x['payment_date'][:10], "Action": "Payment", "Debit": 0, "Credit": x['amount_paid']} for x in p_data]
    st.table(pd.DataFrame(hist).sort_values("Date"))

# --- (Other pages like Overdue, Payroll, Expenses follow the same pattern) ---
