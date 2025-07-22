import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import xlsxwriter
import plotly.express as px
from gspread.exceptions import SpreadsheetNotFound, APIError
import json 
from oauth2client.service_account import ServiceAccountCredentials
# Google Sheets setup
SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]
CREDS_FILE = "credentials.json"  # Ensure this file is in your project directory
SHEET_NAME = "FamilyExpenses"

def get_google_sheet():
    try:
        

        creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)

        client = gspread.authorize(creds)
        SHEET_ID="1KdQKgqlOkknTgWCVenFL6TZqdPcLwwOLP7Azx-fh9L4"
        sheet = client.open_by_key(SHEET_ID).sheet1
        return sheet
    except SpreadsheetNotFound:
        st.error(f"Spreadsheet '{SHEET_NAME}' not found. Please ensure the sheet exists and is shared with the Service Account.")
        return None
    except APIError as e:
        st.error(f"Google API error: {str(e)}")
        return None
    except Exception as e:
        st.error(f"Unexpected error accessing Google Sheet: {str(e)}")
        return None

# Load data
def load_data():
    sheet = get_google_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            if data:
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                return df
            else:
                st.warning("Google Sheet is empty. Initialized empty DataFrame.")
        except Exception as e:
            st.error(f"Error loading data: {str(e)}")
    return pd.DataFrame(columns=['amount', 'from', 'to', 'description', 'date', 'type'])

# Initialize session state for data
if 'df' not in st.session_state:
    st.session_state.df = load_data()

# Initialize session state for form inputs
if 'from_person' not in st.session_state:
    st.session_state.from_person = ""
if 'to_person' not in st.session_state:
    st.session_state.to_person = ""

# Title
st.title("🌟 Family Expense Tracker")

# Add transaction
st.subheader("Add New Transaction")

# Get unique members from DataFrame
member_list = list(set(st.session_state.df['from'].tolist() + st.session_state.df['to'].tolist()))
members = sorted([m for m in member_list if m])

# From person selection
from_select = st.selectbox("From", members + ["Other"], key="from_select")
if from_select == "Other":
    st.session_state.from_person = st.text_input("Enter new 'From' name", key="from_input")
else:
    st.session_state.from_person = from_select

# To person selection
to_select = st.selectbox("To", members + ["Other"], key="to_select")
if to_select == "Other":
    st.session_state.to_person = st.text_input("Enter new 'To' name", key="to_input")
else:
    st.session_state.to_person = to_select

# Transaction form
with st.form("transaction_form"):
    amount = st.number_input("Amount", min_value=0.00, format="%.2f")
    type_transaction = st.selectbox("Type", ["income", "expense", "transfer"])
    description = st.text_input("Description", placeholder="e.g., new clothes")
    date = st.date_input("Date", value=datetime.today())
    submit = st.form_submit_button("Add Transaction")

    if submit:
        if not all([amount, st.session_state.from_person, st.session_state.to_person, description, date, type_transaction]):
            st.warning("Please fill all fields.")
        else:
            transaction = {
                "amount": amount,
                "from": st.session_state.from_person,
                "to": st.session_state.to_person,
                "description": description,
                "date": date.strftime("%Y-%m-%d"),
                "type": type_transaction
            }
            sheet = get_google_sheet()
            if sheet:
                try:
                    sheet.append_row([
                        transaction["amount"],
                        transaction["from"],
                        transaction["to"],
                        transaction["description"],
                        transaction["date"],
                        transaction["type"]
                    ])
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([transaction])], ignore_index=True)
                    st.session_state.df['date'] = pd.to_datetime(st.session_state.df['date'], errors='coerce')
                    st.success("Transaction added successfully!")
                    # Clear form inputs
                    st.session_state.from_person = ""
                    st.session_state.to_person = ""
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add transaction: {str(e)}")
            else:
                st.error("Google Sheet not available.")

# Search & filter
st.subheader("Search Transactions")
with st.form("search_form"):
    search_term = st.text_input("Search by Name or Description")
    type_filter = st.selectbox("Transaction Type", ["All", "income", "expense", "transfer"])
    col1, col2 = st.columns(2)
    with col1:
        date_start = st.date_input("Start Date", value=None, max_value=datetime.today())
    with col2:
        date_end = st.date_input("End Date", value=None, max_value=datetime.today())
    search_btn = st.form_submit_button("Search")

filtered_df = st.session_state.df.copy()

if search_btn:
    if search_term:
        filtered_df = filtered_df[
            filtered_df['from'].str.contains(search_term, case=False, na=False) |
            filtered_df['to'].str.contains(search_term, case=False, na=False) |
            filtered_df['description'].str.contains(search_term, case=False, na=False)
        ]
    if type_filter != "All":
        filtered_df = filtered_df[filtered_df['type'] == type_filter]
    if date_start:
        filtered_df = filtered_df[filtered_df['date'] >= pd.to_datetime(date_start)]
    if date_end:
        filtered_df = filtered_df[filtered_df['date'] <= pd.to_datetime(date_end)]

st.subheader("Filtered Transactions")
filtered_df['date'] = pd.to_datetime(filtered_df['date']).dt.strftime('%d-%m-%Y')
st.dataframe(filtered_df)

if not filtered_df.empty:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        filtered_df.to_excel(writer, index=False)
    st.download_button(
        "Download Excel",
        data=output.getvalue(),
        file_name=f"transactions_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    )

# Monthly summary by person
st.subheader("📆 Monthly Summary by Person")
df = st.session_state.df.copy()
df['month'] = df['date'].dt.strftime('%m-%Y')


person_summary = []
people = pd.unique(df[['from', 'to']].values.ravel('K'))

for person in people:
    monthly = df.copy()
    monthly['net'] = 0
    monthly.loc[(monthly['type'] == 'income') & (monthly['from'] != person)& (monthly['to'] == person), 'net'] = monthly['amount']
    monthly.loc[(monthly['type'] == 'income') & (monthly['to'] != person)& (monthly['from'] == person), 'net'] = -monthly['amount']
    monthly.loc[(monthly['type'] == 'expense')& (monthly['from'] != person) & (monthly['from'] == person), 'net'] = -monthly['amount']
    monthly.loc[(monthly['type'] == 'expense')& (monthly['from'] != person) & (monthly['to'] == person), 'net'] = monthly['amount']
    monthly.loc[(monthly['type'] == 'transfer') & (monthly['from'] != person)& (monthly['to'] == person), 'net'] = monthly['amount']
    monthly.loc[(monthly['type'] == 'transfer') & (monthly['to'] != person)& (monthly['from'] == person), 'net'] = -monthly['amount']
    summary = monthly.groupby('month')['net'].sum().reset_index()
    summary['person'] = person
    person_summary.append(summary)

summary_df = pd.concat(person_summary)
summary_pivot = summary_df.pivot(index='month', columns='person', values='net').fillna(0)
st.dataframe(summary_pivot)

# Expense breakdown total balance
st.subheader("📊 Balance by Person")
people = sorted(pd.unique(df[['from', 'to']].values.ravel('K')))
balance_data = []
for person in people:
    income = df[(df['type'] == 'income') & (df['to'] == person)]['amount'].sum() + \
             df[(df['type'] == 'expense') & (df['to'] == person)]['amount'].sum()
    expense = df[(df['type'] == 'expense') & (df['from'] == person)]['amount'].sum() + \
              df[(df['type'] == 'income') & (df['from'] == person)]['amount'].sum()
    transferred_in = df[(df['type'] == 'transfer') & (df['to'] == person)]['amount'].sum()
    transferred_out = df[(df['type'] == 'transfer') & (df['from'] == person)]['amount'].sum()
    total = (income + transferred_in) - (expense + transferred_out)
    balance_data.append({
        'person': person,
        'income': income,
        'expense': expense,
        'transferred_in': transferred_in,
        'transferred_out': transferred_out,
        'total': total
    })

balance_df = pd.DataFrame(balance_data)
st.dataframe(balance_df[['person', 'income', 'expense', 'transferred_in', 'transferred_out', 'total']])

# Pie chart total
st.subheader("Overall Expense Breakdown")
type_sum = df.groupby('type')['amount'].sum()
st.plotly_chart(px.pie(values=type_sum.values, names=type_sum.index, title="Transaction Type Distribution"))
