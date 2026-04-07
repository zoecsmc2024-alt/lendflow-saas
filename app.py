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
    st.title(f"📈 {active_company['name']} | Executive Overview")
    loans, payments, expenses = get_dashboard_metrics(active_company['id'])
    if not loans:
        st.info("Welcome! Start by registering a client and issuing your first loan.")
    else:
        total_balance = sum(float(l.get('balance_remaining',0)) for l in loans)
        total_collected = sum(float(p.get('amount_paid',0)) for p in payments)
        total_opex = sum(float(e.get('amount',0)) for e in expenses)
        c1, c2, c3 = st.columns(3)
        c1.metric("Active Portfolio", f"{total_balance:,.0f} UGX")
        c2.metric("Total Collections", f"{total_collected:,.0f} UGX")
        c3.metric("Net Cash Position", f"{(total_collected - total_opex):,.0f} UGX")
        
        st.write("---")
        col_left, col_right = st.columns(2)
        with col_left:
            st.plotly_chart(px.pie(pd.DataFrame(loans), names='loan_status', values='balance_remaining', hole=.5), use_container_width=True)
        with col_right:
            if expenses:
                st.plotly_chart(px.bar(pd.DataFrame(expenses), x='category', y='amount'), use_container_width=True)

elif page == "👥 Clients":
    st.title(f"👥 {active_company['name']} | Client Registry")
    tab1, tab2 = st.tabs(["➕ Register", "📋 Database"])
    with tab1:
        with st.form("client_form", clear_on_submit=True):
            f_name = st.text_input("Full Name")
            id_no = st.text_input("ID Number")
            phone = st.text_input("Phone Number")
            if st.form_submit_button("Securely Register"):
                supabase.table("clients").insert({"company_id": active_company['id'], "full_name": f_name, "id_number": id_no, "phone_number": phone}).execute()
                st.success("Registered!"); st.rerun()
    with tab2:
        clients = get_data("clients", active_company['id'])
        if clients: st.dataframe(pd.DataFrame(clients)[["full_name", "id_number", "phone_number"]], use_container_width=True)

elif page == "💵 Loans":
    st.title("💵 Loan Disbursement")
    clients = get_data("clients", active_company['id'])
    if not clients: st.warning("Register a client first."); st.stop()
    with st.form("loan_form"):
        c_map = {c['full_name']: c['id'] for c in clients}
        target = st.selectbox("Borrower", list(c_map.keys()))
        amt = st.number_input("Principal", min_value=10000)
        rate = st.number_input("Annual Interest %", value=15.0)
        dur = st.number_input("Months", value=6)
        if st.form_submit_button("Disburse Cash"):
            total, monthly = calculate_loan(amt, rate, dur)
            supabase.table("loans").insert({"company_id": active_company['id'], "client_id": c_map[target], "principal_amount": amt, "interest_rate": rate, "duration_months": dur, "total_repayable": total, "monthly_installment": monthly, "balance_remaining": total}).execute()
            st.success("Loan Disbursed!"); st.rerun()

elif page == "💰 Payments":
    st.title("💰 Repayment Entry")
    loans = supabase.table("loans").select("*, clients(full_name)").eq("company_id", active_company['id']).neq("loan_status", "Settled").execute().data
    if loans:
        with st.form("pay_form"):
            l_map = {f"{l['clients']['full_name']} (Bal: {l['balance_remaining']:,.0f})": l for l in loans}
            sel = st.selectbox("Select Loan", list(l_map.keys()))
            pay_amt = st.number_input("Amount Paid", min_value=1000)
            if st.form_submit_button("Post Payment"):
                loan = l_map[sel]
                new_bal = float(loan['balance_remaining']) - float(pay_amt)
                supabase.table("loans").update({"balance_remaining": max(new_bal,0), "loan_status": "Settled" if new_bal <= 0 else "Active"}).eq("id", loan['id']).execute()
                supabase.table("transactions").insert({"company_id": active_company['id'], "loan_id": loan['id'], "amount_paid": pay_amt, "payment_method": "Manual"}).execute()
                st.success("Payment Recorded!"); st.rerun()

elif page == "🚨 Overdue":
    st.title("🚨 Overdue Tracker")
    overdue = supabase.table("loans").select("*, clients(full_name)").eq("company_id", active_company['id']).neq("loan_status", "Settled").execute().data
    if overdue:
        for l in overdue:
            c1, c2 = st.columns([3,1])
            c1.write(f"**{l['clients']['full_name']}** - Remaining: {l['balance_remaining']:,.0f} UGX")
            if c2.button("Apply 10% Penalty", key=l['id']):
                penalty = float(l['monthly_installment']) * 0.1
                supabase.table("loans").update({"balance_remaining": float(l['balance_remaining']) + penalty, "loan_status": "Overdue"}).eq("id", l['id']).execute()
                st.warning(f"Penalty of {penalty:,.0f} applied!"); st.rerun()

elif page == "📄 Payroll":
    st.title("📄 Payroll Engine")
    staff = get_data("clients", active_company['id'])
    with st.form("payroll_form"):
        target_staff = st.selectbox("Select Staff", [s['full_name'] for s in staff])
        basic = st.number_input("Basic Salary", min_value=100000)
        nssf, paye, net = calculate_uganda_payroll(basic)
        st.write(f"**NSSF:** {nssf:,.0f} | **PAYE:** {paye:,.0f} | **NET:** {net:,.0f}")
        if st.form_submit_button("Process Salary"):
            supabase.table("expenses").insert({"company_id": active_company['id'], "category": "Salaries", "description": f"Salary for {target_staff}", "amount": basic}).execute()
            st.success("Payroll Posted to Expenses!"); st.rerun()

elif page == "📂 Expenses":
    st.title("📂 Expense Tracker")
    with st.form("exp_form"):
        cat = st.selectbox("Category", ["Rent", "Taxes", "Marketing", "Petty Cash", "Utilities"])
        desc = st.text_input("Description")
        amt = st.number_input("Amount", min_value=1000)
        if st.form_submit_button("Record Outflow"):
            supabase.table("expenses").insert({"company_id": active_company['id'], "category": cat, "description": desc, "amount": amt}).execute()
            st.success("Expense Logged!"); st.rerun()

elif page == "📄 Ledger":
    st.title("📄 Master Client Ledger")
    clients = get_data("clients", active_company['id'])
    target = st.selectbox("Select Client", [c['full_name'] for c in clients])
    cid = [c['id'] for c in clients if c['full_name'] == target][0]
    l_data = supabase.table("loans").select("*").eq("client_id", cid).execute().data
    p_data = supabase.table("transactions").select("*, loans(client_id)").eq("loans.client_id", cid).execute().data
    hist = [{"Date": x['disbursement_date'], "Type": "Loan", "Debit": x['total_repayable'], "Credit": 0} for x in l_data]
    hist += [{"Date": x['payment_date'][:10], "Type": "Payment", "Debit": 0, "Credit": x['amount_paid']} for x in p_data]
    st.table(pd.DataFrame(hist).sort_values("Date"))

elif page == "🧾 Reports":
    st.title("🧾 P&L and Balance Sheet")
    loans, payments, expenses = get_dashboard_metrics(active_company['id'])
    rev = sum((float(l['total_repayable']) - float(l['principal_amount'])) for l in loans)
    opex = sum(float(e['amount']) for e in expenses)
    st.subheader("Profit & Loss Statement")
    st.write(f"Total Interest Revenue: **{rev:,.0f} UGX**")
    st.write(f"Total Operating Expenses: **{opex:,.0f} UGX**")
    st.write(f"---")
    st.write(f"Net Profit: **{(rev - opex):,.0f} UGX**")

elif page == "🛡️ Collateral":
    st.title("🛡️ Collateral Registry")
    st.info("Module linked to loan security.")
