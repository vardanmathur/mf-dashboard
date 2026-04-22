import streamlit as st
from google.oauth2.service_account import Credentials
import gspread

st.title("GSheets Connection Test")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Step 1: check secrets loaded
try:
    sa = st.secrets["gcp_service_account"]
    st.success(f"✅ Secrets loaded. client_email: {sa['client_email']}")
    st.success(f"✅ project_id: {sa['project_id']}")
    st.success(f"✅ private_key starts with: {sa['private_key'][:40]}")
except Exception as e:
    st.error(f"❌ Secrets load failed: {e}")
    st.stop()

# Step 2: build credentials
try:
    creds = Credentials.from_service_account_info(dict(sa), scopes=SCOPES)
    st.success("✅ Credentials object created")
except Exception as e:
    st.error(f"❌ Credentials failed: {e}")
    st.stop()

# Step 3: authorize gspread
try:
    gc = gspread.authorize(creds)
    st.success("✅ gspread authorized")
except Exception as e:
    st.error(f"❌ gspread authorize failed: {e}")
    st.stop()

# Step 4: open sheet
try:
    url = st.secrets["google_sheets"]["url"]
    sh = gc.open_by_url(url)
    st.success(f"✅ Sheet opened: {sh.title}")
except Exception as e:
    st.error(f"❌ Sheet open failed: {e}")
    st.stop()

# Step 5: open worksheet
try:
    ws = sh.worksheet("mf_data")
    st.success(f"✅ Worksheet 'mf_data' found")
    rows = ws.get_all_records()
    st.success(f"✅ Loaded {len(rows)} rows")
except Exception as e:
    st.error(f"❌ Worksheet failed: {e}")
