import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import xlsxwriter
import plotly.express as px
from gspread.exceptions import SpreadsheetNotFound, APIError
import json from oauth2client.service_account import ServiceAccountCredentials
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

# Initialize session state for data
if 'df' not in st.session_state:
    sheet = get_google_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            if data:  # Check if data is not empty
                st.session_state.df = pd.DataFrame(data)
                expected_columns = ['amount', 'from', 'to', 'description', 'date', 'type']
                if all(col in st.session_state.df.columns for col in expected_columns):
                    st.session_state.df['date'] = pd.to_datetime(st.session_state.df['date'], errors='coerce')
                else:
                    st.error(f"Missing columns in Google Sheet. Expected: {expected_columns}, Found: {list(st.session_state.df.columns)}")
                    st.session_state.df = pd.DataFrame(columns=expected_columns)
            else:
                st.session_state.df = pd.DataFrame(columns=['amount', 'from', 'to', 'description', 'date', 'type'])
                st.warning("Google Sheet is empty. Initialized empty DataFrame.")
        except Exception as e:
            st.error(f"Error fetching data from Google Sheet: {str(e)}")
            st.session_state.df = pd.DataFrame(columns=['amount', 'from', 'to', 'description', 'date', 'type'])
    else:
        st.session_state.df = pd.DataFrame(columns=['amount', 'from', 'to', 'description', 'date', 'type'])
        st.error("Failed to connect to Google Sheet. Using empty DataFrame.")

# Rest of the app
st.title("Family Expense Tracker")
st.markdown("Track your family's expenses with ease!")

# Form for adding transactions
with st.form("transaction_form"):
    st.subheader("Add New Transaction")
    amount = st.number_input("Amount", min_value=0.0, format="%.2f")
    from_person = st.text_input("From", placeholder="e.g., Yash Bob")
    to_person = st.text_input("To", placeholder="e.g., Balar Kotak Mahindra")
    description = st.text_input("Description", placeholder="e.g., for new cloth")
    date = st.date_input("Date", value=datetime.today())
    type_transaction = st.selectbox("Type", ["income", "expense", "transfer"])
    submit_button = st.form_submit_button("Add Transaction")

    if submit_button:
        new_transaction = {
            "amount": amount,
            "from": from_person,
            "to": to_person,
            "description": description,
            "date": date.strftime("%Y-%m-%d"),
            "type": type_transaction
        }
        sheet = get_google_sheet()
        if sheet:
            try:
                sheet.append_row([new_transaction["amount"], new_transaction["from"], new_transaction["to"],
                                 new_transaction["description"], new_transaction["date"], new_transaction["type"]])
                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_transaction])], ignore_index=True)
                st.session_state.df['date'] = pd.to_datetime(st.session_state.df['date'], errors='coerce')
                st.success("Transaction added successfully!")
            except Exception as e:
                st.error(f"Error adding transaction to Google Sheet: {str(e)}")
        else:
            st.error("Failed to add transaction due to Google Sheet connection issue.")

# Search and filter section
st.subheader("Search Transactions")
with st.form("search_form"):
    col1, col2 = st.columns(2)
    with col1:
        search_term = st.text_input("Search by From, To, or Description")
    with col2:
        type_filter = st.selectbox("Filter by Type", ["All", "income", "expense", "transfer"])
    date_start = st.date_input("Start Date", value=None)
    date_end = st.date_input("End Date", value=None)
    search_button = st.form_submit_button("Search")

# Filtering logic
filtered_df = st.session_state.df
if search_button:
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

# Display filtered results
st.subheader("Transaction Results")
st.dataframe(filtered_df)

# Download as Excel
if not filtered_df.empty:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        filtered_df.to_excel(writer, index=False, sheet_name='Transactions')
    excel_data = output.getvalue()
    st.download_button(
        label="Download as Excel",
        data=excel_data,
        file_name="family_expenses.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Optional: Monthly summary
st.subheader("Monthly Summary")
if not filtered_df.empty:
    filtered_df['month'] = filtered_df['date'].dt.to_period('M')
    summary = filtered_df.groupby(['month', 'type'])['amount'].sum().unstack().fillna(0)
    st.write(summary)

# Optional: Pie chart
if not filtered_df.empty:
    st.subheader("Expense Breakdown")
    pie_data = filtered_df.groupby('type')['amount'].sum()
    st.plotly_chart(px.pie(values=pie_data.values, names=pie_data.index, title="Transaction Types"))
