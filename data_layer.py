"""
data_layer.py — Google Sheets read via gspread.

Sheet tabs:
  mf_data:          name | y | z | color | date | spread_color
  portfolio_growth: date | stocks | mfs | total | monthly_delta
  All dates stored as YYYY-MM-DD strings in the sheet.
"""

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]
MF_DATA_TAB           = "mf_data"
EXPECTED_COLS         = ["name", "y", "z", "color", "date", "spread_color"]
PORTFOLIO_GROWTH_TAB  = "portfolio_growth"
PORTFOLIO_GROWTH_COLS = ["date", "stocks", "mfs", "total", "monthly_delta"]
PORTFOLIO_XIRR_TAB    = "portfolio_xirr"
PORTFOLIO_XIRR_COLS   = ["date", "xirr_pct"]
FUND_XIRR_BOX_TAB     = "fund_xirr_box"
FUND_XIRR_BOX_COLS    = ["name", "min_xirr", "max_xirr", "current_xirr", "color"]


@st.cache_resource
def get_gsheet_client():
    """Cached gspread client — one connection for the whole session."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def _get_spreadsheet():
    gc = get_gsheet_client()
    return gc.open_by_url(st.secrets["google_sheets"]["url"])


def load_data() -> pd.DataFrame:
    """Load all rows from the mf_data sheet tab into a DataFrame."""
    ws = _get_spreadsheet().worksheet(MF_DATA_TAB)
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


def load_portfolio_growth() -> pd.DataFrame:
    # Requires Google Sheet tab "portfolio_growth" with headers: date | stocks | mfs | total | monthly_delta
    ws = _get_spreadsheet().worksheet(PORTFOLIO_GROWTH_TAB)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return pd.DataFrame(columns=PORTFOLIO_GROWTH_COLS)
    headers = [h.strip().lower() for h in values[0]]
    df = pd.DataFrame(values[1:], columns=headers)
    df = df[[c for c in PORTFOLIO_GROWTH_COLS if c in df.columns]]
    df["date"] = pd.to_datetime(df["date"], format="%b-%Y", errors="coerce")
    for col in ["stocks", "mfs", "total", "monthly_delta"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace("₹", "", regex=False).str.replace(",", "", regex=False).str.strip()
    df["stocks"]        = pd.to_numeric(df["stocks"],        errors="coerce").fillna(0)
    df["mfs"]           = pd.to_numeric(df["mfs"],           errors="coerce").fillna(0)
    df["total"]         = pd.to_numeric(df["total"],         errors="coerce")
    df["monthly_delta"] = pd.to_numeric(df["monthly_delta"], errors="coerce").fillna(0)
    df = df.dropna(subset=["date", "total"])
    df = df[df["total"] > 0]
    df = df.sort_values("date").reset_index(drop=True)
    return df


def load_portfolio_xirr() -> pd.DataFrame:
    # Requires Google Sheet tab "portfolio_xirr" with headers: date | xirr_pct
    ws = _get_spreadsheet().worksheet(PORTFOLIO_XIRR_TAB)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return pd.DataFrame(columns=PORTFOLIO_XIRR_COLS)
    headers = [h.strip().lower() for h in values[0]]
    df = pd.DataFrame(values[1:], columns=headers)
    df = df[[c for c in PORTFOLIO_XIRR_COLS if c in df.columns]]
    df["date"] = pd.to_datetime(df["date"], format="%d-%b-%y", errors="coerce")
    df["xirr_pct"] = df["xirr_pct"].astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False).str.strip()
    df["xirr_pct"] = pd.to_numeric(df["xirr_pct"], errors="coerce")
    df = df.dropna(subset=["date", "xirr_pct"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def load_fund_xirr_box() -> pd.DataFrame:
    # Requires Google Sheet tab "fund_xirr_box" with headers: name | min_xirr | max_xirr | current_xirr | color
    ws = _get_spreadsheet().worksheet(FUND_XIRR_BOX_TAB)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return pd.DataFrame(columns=FUND_XIRR_BOX_COLS)
    headers = [h.strip().lower() for h in values[0]]
    df = pd.DataFrame(values[1:], columns=headers)
    df = df[[c for c in FUND_XIRR_BOX_COLS if c in df.columns]]
    for col in ["min_xirr", "max_xirr", "current_xirr"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False).str.strip()
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["name", "current_xirr"])
    df = df.sort_values("current_xirr", ascending=False).reset_index(drop=True)
    return df
