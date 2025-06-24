import streamlit as st
import pandas as pd
import openpyxl
import xlrd
from io import BytesIO
import re
import math

# Helper Functions
def clean_header(header):
    if pd.isna(header):
        return ""
    return str(header).replace('*', '').strip()

def is_decorative_row(row):
    for cell in row:
        if pd.notna(cell):
            cell_str = str(cell).strip()
            if cell_str:
                if not re.match(r'^[\s\*\-\=\+\_\|]*$', cell_str):
                    return False
    return True

def find_header_row(df):
    potential_headers = ['date', 'narration', 'remarks', 'amount', 'balance', 'withdrawal', 'deposit', 'tran', 'chq', 'ref', 'closing', 'value']
    for idx, row in df.iterrows():
        if is_decorative_row(row):
            continue
        row_str = ' '.join([str(cell).lower() for cell in row if pd.notna(cell)])
        if re.match(r'^[\s\*\-\=\+\_\|]*$', row_str):
            continue
        if len(row_str.strip()) < 10:
            continue
        header_matches = sum(1 for header in potential_headers if header in row_str)
        if header_matches >= 2:
            return idx
    return None

def parse_concatenated_headers(header_string):
    if pd.isna(header_string):
        return []
    header_str = str(header_string)
    patterns = [
        r'(Date)', r'(Narration)', r'(Chq\./Ref\.No\.)', r'(Value Dt)',
        r'(Withdrawal Amt\.)', r'(Deposit Amt\.)', r'(Closing Balance)',
        r'(Transaction Date)', r'(Tran Id)', r'(Remarks)', r'(UTR Number)',
        r'(Instr\. Id)', r'(Withdrawals)', r'(Deposits)', r'(Balance)',
        r'(Amount)'
    ]
    headers = []
    temp_header_str = header_str
    for pattern in patterns:
        matches = list(re.finditer(pattern, temp_header_str, re.IGNORECASE))
        for match in matches:
            headers.append(match.group(0))
            temp_header_str = temp_header_str[:match.start()] + ' ' * len(match.group(0)) + temp_header_str[match.end():]
    headers = [clean_header(h) for h in headers if h.strip()]
    if not headers:
        split_headers = re.findall(r'[A-Z][a-z]*\.?/?[A-Z]*[a-z]*\.?', header_str)
        headers = [clean_header(h) for h in split_headers if h.strip()]
    if not headers and header_str.strip():
        return [clean_header(header_str)]
    return headers

def clean_dataframe(df):
    clean_rows_indices = []
    for idx, row in df.iterrows():
        if not is_decorative_row(row):
            clean_rows_indices.append(idx)
    df_clean = df.loc[clean_rows_indices].copy()
    df_clean = df_clean.dropna(how='all')
    df_clean = df_clean.dropna(axis=1, how='all')
    return df_clean

def standardize_columns(df):
    column_mapping = {
        'date': 'Date',
        'transaction date': 'Date',
        'trans date': 'Date',
        'narration': 'Description',
        'remarks': 'Description',
        'particulars': 'Description',
        'chq./ref.no.': 'Reference',
        'chq/ref no': 'Reference',
        'tran id': 'Transaction_ID',
        'transaction id': 'Transaction_ID',
        'withdrawal amt.': 'Withdrawal',
        'withdrawals': 'Withdrawal',
        'debit': 'Withdrawal',
        'deposit amt.': 'Deposit',
        'deposits': 'Deposit',
        'credit': 'Deposit',
        'amount': 'Amount',
        'closing balance': 'Balance',
        'balance': 'Balance',
        'running balance': 'Balance',
        'value dt': 'Value_Date',
        'utr number': 'UTR_Number',
        'instr. id': 'Instrument_ID',
        'instrument id': 'Instrument_ID'
    }
    new_columns = []
    for col in df.columns:
        clean_col = clean_header(col).lower()
        standardized = column_mapping.get(clean_col, clean_col.title().replace(' ', '_'))
        new_columns.append(standardized)
    df.columns = new_columns
    return df

def read_excel_file(file):
    file.seek(0)
    file_extension = file.name.lower().split('.')[-1]
    engines_to_try = ['openpyxl', 'xlrd'] if file_extension in ['xlsx', 'xls'] else ['openpyxl']
    for engine in engines_to_try:
        try:
            file.seek(0)
            temp_df = pd.read_excel(file, engine=engine, header=None, nrows=50)
            header_row_idx = find_header_row(temp_df)
            file.seek(0)
            if header_row_idx is not None:
                df = pd.read_excel(file, engine=engine, header=header_row_idx)
                if not df.columns.empty and len(df.columns) == 1 and len(str(df.columns[0])) > 20:
                    potential_concatenated_header = str(df.columns[0])
                    if any(keyword in potential_concatenated_header.lower() for keyword in ['date', 'narration', 'balance', 'amount']):
                        parsed_headers = parse_concatenated_headers(potential_concatenated_header)
                        if parsed_headers:
                            file.seek(0)
                            df_data_only = pd.read_excel(file, engine=engine, header=None, skiprows=header_row_idx + 1)
                            if len(parsed_headers) <= len(df_data_only.columns):
                                df_data_only.columns = parsed_headers + [f'Col_{i}' for i in range(len(parsed_headers), len(df_data_only.columns))]
                            else:
                                df_data_only.columns = parsed_headers[:len(df_data_only.columns)]
                            df = df_data_only
            else:
                file.seek(0)
                df = pd.read_excel(file, engine=engine)
            df = clean_dataframe(df)
            df.columns = [clean_header(col) for col in df.columns]
            df = standardize_columns(df)
            df = df.dropna(how='all')
            return df, None
        except Exception as e:
            continue
    return None, f"Could not read file with any available engine."

def search_in_dataframe(df, keyword):
    if df.empty:
        return pd.DataFrame()
    keyword_lower = keyword.lower()
    mask = df.astype(str).apply(lambda x: x.str.lower().str.contains(keyword_lower, na=False)).any(axis=1)
    result = df[mask].copy()
    if 'Date' in result.columns:
        result['Date'] = pd.to_datetime(result['Date'], errors='coerce')
        result = result.sort_values(by='Date')
        result['Date'] = result['Date'].dt.strftime('%Y-%m-%d')
    return result

def main():
    st.set_page_config(page_title="Bank Statement Search", layout="wide", initial_sidebar_state="collapsed")
    st.title("\U0001F3E6 Bank Statement Analyzer & Search")
    st.markdown("Easily upload your Excel bank statements, extract key transactions, and search for specific entries.")
    st.markdown("---")
    st.header("\U0001F4E4 Upload Your Bank Statements")
    with st.container(border=True):
        uploaded_files = st.file_uploader("Choose Excel files", type=['xlsx', 'xls'], accept_multiple_files=True)
        st.caption("Supported formats: .xlsx, .xls")
    if uploaded_files:
        all_data = []
        file_info = []
        st.subheader("Processing Files...")
        progress_bar = st.progress(0)
        for i, file in enumerate(uploaded_files):
            with st.spinner(f"Processing '{file.name}'..."):
                df, error = read_excel_file(file)
                if error:
                    st.error(f"❌ Error reading **{file.name}**: {error}")
                    continue
                if df is not None and not df.empty:
                    df['Source_File'] = file.name
                    all_data.append(df)
                    file_info.append({
                        'File': file.name,
                        'Rows': len(df),
                        'Columns': list(df.columns)
                    })
                    st.success(f"✅ Successfully processed **{file.name}** - {len(df)} transactions found.")
                else:
                    st.warning(f"⚠️ No valid transaction data found in **{file.name}**.")
            progress_bar.progress((i + 1) / len(uploaded_files))
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True, sort=False)
            st.markdown("---")
            st.header("\U0001F4CA Overview of Uploaded Data")
            with st.container(border=True):
                st.subheader("📁 File Information Summary")
                for info in file_info:
                    with st.expander(f"📄 **{info['File']}** ({info['Rows']} transactions)"):
                        st.write("**:blue[Columns Detected:]**")
                        st.write(", ".join(info['Columns']))
            st.header("🔍 Search Transactions")
            with st.form(key='search_form', border=True):
                col1, col2 = st.columns([0.7, 0.3])
                with col1:
                    search_keyword = st.text_input("Enter keyword to search", placeholder="e.g., SALARY, ATM, UPI...")
                with col2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    search_submitted = st.form_submit_button("Search", type="primary", use_container_width=True)
            if search_submitted:
                with st.spinner("Searching..."):
                    results_df = search_in_dataframe(combined_df, search_keyword)
                if not results_df.empty:
                    st.subheader(f"✨ Search Results: {len(results_df)} transactions found for '{search_keyword}'")
                    st.dataframe(results_df, use_container_width=True, hide_index=True)
                    csv = results_df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Results (CSV)", data=csv, file_name=f"search_results_{search_keyword}.csv", mime="text/csv", use_container_width=True)
                else:
                    st.info(f"😕 No transactions found containing '{search_keyword}'. Try a different keyword.")
            elif search_keyword:
                st.info("💡 Press 'Search' to see results for your keyword.")
            st.header("📋 Full Transaction Data Preview")
            rows_per_page = 20
            total_rows = len(combined_df)
            total_pages = math.ceil(total_rows / rows_per_page)
            if 'current_page_full_data' not in st.session_state:
                st.session_state.current_page_full_data = 0
            col_prev, col_info, col_next = st.columns([0.15, 0.7, 0.15])
            with col_prev:
                if st.button("⬅️ Previous Page", disabled=(st.session_state.current_page_full_data == 0)):
                    st.session_state.current_page_full_data -= 1
                    st.rerun()
            with col_info:
                start_row = st.session_state.current_page_full_data * rows_per_page
                end_row = min(start_row + rows_per_page, total_rows)
                st.info(f"Showing rows {start_row + 1} to {end_row} of {total_rows} (Page {st.session_state.current_page_full_data + 1}/{total_pages})")
            with col_next:
                if st.button("Next Page ➡️", disabled=(st.session_state.current_page_full_data >= total_pages - 1)):
                    st.session_state.current_page_full_data += 1
                    st.rerun()
            st.dataframe(
                combined_df.iloc[start_row:end_row],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.error("❗ No valid data could be extracted from the uploaded files.")
    else:
        st.info("👆 Please upload your Excel bank statement files above to get started.")

if __name__ == "__main__":
    main()
