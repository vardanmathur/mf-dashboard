"""
data_layer.py — Google Sheets read/write via gspread.

Sheet structure (one tab called "mf_data"):
  Columns: name | y | z | color | date | spread_color
  date stored as YYYY-MM-DD strings in the sheet.
"""

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]
SHEET_TAB = "mf_data"
EXPECTED_COLS = ["name", "y", "z", "color", "date", "spread_color"]


@st.cache_resource
def get_gsheet_client():
    """Cached gspread client — one connection for the whole session."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def _get_worksheet():
    gc = get_gsheet_client()
    sheet_url = st.secrets["google_sheets"]["url"]
    sh = gc.open_by_url(sheet_url)
    return sh.worksheet(SHEET_TAB)


def load_data() -> pd.DataFrame:
    """Load all rows from the Google Sheet into a DataFrame."""
    ws = _get_worksheet()
    records = ws.get_all_records(expected_headers=EXPECTED_COLS)
    if not records:
        return pd.DataFrame(columns=EXPECTED_COLS)
    df = pd.DataFrame(records)
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], dayfirst=False, errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df["z"] = pd.to_numeric(df["z"], errors="coerce")
    df = df.dropna(subset=["date", "y", "z"])
    return df.reset_index(drop=True)


def append_rows(new_df: pd.DataFrame) -> int:
    """
    Append rows to the Google Sheet.
    Deduplicates on (name, date) — will not write rows that already exist.
    Returns the number of rows actually written.
    """
    ws = _get_worksheet()

    # Load existing (name, date) pairs to deduplicate
    existing_raw = ws.get_all_records(expected_headers=EXPECTED_COLS)
    existing_keys = set()
    for row in existing_raw:
        existing_keys.add((str(row["name"]).strip(), str(row["date"]).strip()))

    rows_to_write = []
    new_df = new_df.copy()
    new_df["date"] = pd.to_datetime(new_df["date"]).dt.strftime("%Y-%m-%d")

    for _, row in new_df.iterrows():
        key = (str(row["name"]).strip(), str(row["date"]).strip())
        if key in existing_keys:
            continue
        rows_to_write.append([
            str(row["name"]),
            float(row["y"]),
            float(row["z"]),
            str(row["color"]),
            str(row["date"]),
            str(row.get("spread_color", row["color"])),
        ])

    if rows_to_write:
        ws.append_rows(rows_to_write, value_input_option="USER_ENTERED")

    return len(rows_to_write)
