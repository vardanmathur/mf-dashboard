import streamlit as st
import pandas as pd
import json
import io
from datetime import datetime
from data_layer import load_data, append_rows, get_gsheet_client

st.set_page_config(page_title="MF Dashboard", layout="wide", page_icon="📈")

# ── Password gate ────────────────────────────────────────────────────────────

def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.title("📈 MF Dashboard")
    pwd = st.text_input("Password", type="password", key="pwd_input")
    if st.button("Login"):
        if pwd == st.secrets["app"]["password"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    return False

if not check_password():
    st.stop()


# ── Data loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner="Loading data from Google Sheets…")
def get_data():
    return load_data()


# ── Build chart HTML ─────────────────────────────────────────────────────────

SPECIAL_BOTTOM_MFS = {
    "Mirae Asset Liquid", "Mirae Asset Cash Mgmt", "HSBC Cash", "UTI Liquid",
    "Axis Liquid Fund", "Bandhan Liquid Fund", "HDFC Liquid Fund (G)",
    "Kotak Liquid Fund Reg(G)", "Parag Parikh Liquid Fund Reg (G)",
}

def build_chart_html(df: pd.DataFrame) -> str:
    unique_dates = sorted(df["date"].dt.strftime("%Y-%m-%d").unique())
    unique_mfs   = sorted(df["name"].unique())

    # Tab 1
    date_data_dict = {}
    for date_str in unique_dates:
        dframe = df[df["date"].dt.strftime("%Y-%m-%d") == date_str].sort_values("y", ascending=False)
        date_data_dict[date_str] = [
            {"name": str(r["name"]), "y": float(r["y"]), "z": float(r["z"]), "color": str(r["color"])}
            for _, r in dframe.iterrows()
        ]

    # Tab 2
    mf_ts = {}
    for mf in unique_mfs:
        dframe = df[df["name"] == mf].sort_values("date")
        mf_ts[mf] = [
            {"date": r["date"].strftime("%Y-%m-%d"), "y": float(r["y"]),
             "z": float(r["z"]), "color": str(r["color"])}
            for _, r in dframe.iterrows()
        ]

    # Tab 3
    df_s = df.copy()
    df_s["date_str"] = df_s["date"].dt.strftime("%Y-%m-%d")
    if "spread_color" not in df_s.columns:
        df_s["spread_color"] = pd.NA
    dt = df_s.groupby("date_str")["z"].sum().rename("total_z")
    df_s = df_s.merge(dt, left_on="date_str", right_index=True, how="left")
    df_s["total_z"] = df_s["total_z"].replace(0, pd.NA)
    df_s["pct"] = (df_s["z"] / df_s["total_z"]) * 100
    spread_dates = sorted(df_s["date_str"].unique())
    spread_date_index = {d: i for i, d in enumerate(spread_dates)}
    latest_date_str = max(spread_dates)
    current_holdings = df_s[df_s["date_str"] == latest_date_str][df_s["z"] > 0][["name","z"]].rename(columns={"z":"latest_z"})
    max_hist = df_s.groupby("name")["z"].max().reset_index().rename(columns={"z":"max_z"})
    pdf = max_hist.merge(current_holdings, on="name", how="left")
    pdf["is_current"]     = pdf["latest_z"].fillna(0) > 0
    pdf["latest_z"]       = pdf["latest_z"].fillna(0)
    pdf["is_current_int"] = pdf["is_current"].astype(int)
    pdf["special_priority"] = pdf["name"].apply(lambda n: 1 if n in SPECIAL_BOTTOM_MFS else 0)
    pdf = pdf.sort_values(["special_priority","is_current_int","latest_z","max_z"], ascending=[True,False,False,False])
    mf_spread_series = []
    for mf in list(pdf["name"]):
        sub = df_s[df_s["name"] == mf].sort_values("date")
        if sub["pct"].notna().sum() == 0:
            continue
        pts, color = [], None
        for _, row in sub.iterrows():
            if pd.isna(row["pct"]): continue
            pts.append([spread_date_index[row["date_str"]], float(row["pct"])])
            if color is None:
                sc = "" if pd.isna(row.get("spread_color")) else str(row["spread_color"]).strip()
                color = sc or str(row["color"])
        if pts:
            mf_spread_series.append({"name": mf, "data": pts, "color": color})
    mf_spread_series = mf_spread_series[::-1]

    # Default funds for Tab 2
    non_liquid = [m for m in df[df["date"] == df["date"].max()].sort_values("z", ascending=False)["name"].tolist()
                  if m not in SPECIAL_BOTTOM_MFS]
    default_funds_js = json.dumps(non_liquid[:2])

    # Build dropdown HTML
    dropdown_options_html    = "\n".join([f'<option value="{d}">{d}</option>' for d in unique_dates])
    mf_dropdown_options_html = "\n".join([f'<option value="{mf}">{mf}</option>' for mf in unique_mfs])

    # Read template and inject
    with open("chart_template.html", "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("MF_DROPDOWN_OPTIONS_HTML", mf_dropdown_options_html)
    html = html.replace("DROPDOWN_OPTIONS_HTML",    dropdown_options_html)
    html = html.replace("JS_DATE_PERIODS_JSON",     json.dumps(date_data_dict))
    html = html.replace("JS_MF_TIMESERIES_JSON",    json.dumps(mf_ts))
    html = html.replace("JS_MF_SPREAD_JSON",        json.dumps(mf_spread_series))
    html = html.replace("JS_MF_SPREAD_CATEGORIES",  json.dumps(spread_dates))
    html = html.replace("DEFAULT_FUNDS_JS",         default_funds_js)
    return html


# ── Sidebar: add data ─────────────────────────────────────────────────────────

REQUIRED_COLS = ["name", "y", "z", "color", "date", "spread_color"]

def sidebar_add_data():
    st.sidebar.header("➕ Add Data")

    method = st.sidebar.radio("Method", ["Upload file (Excel/CSV)", "Paste CSV text"], label_visibility="collapsed")

    new_df = None

    if method == "Upload file (Excel/CSV)":
        f = st.sidebar.file_uploader("Excel or CSV file", type=["xlsx","xls","csv"])
        if f:
            try:
                new_df = pd.read_excel(f, parse_dates=["date"]) if f.name.endswith(("xlsx","xls")) \
                         else pd.read_csv(f, parse_dates=["date"])
            except Exception as e:
                st.sidebar.error(f"Parse error: {e}")

    else:  # paste
        st.sidebar.caption("Paste CSV with columns: name, y, z, color, date, spread_color")
        pasted = st.sidebar.text_area("CSV text", height=200, placeholder="name,y,z,color,date,spread_color\nHDFC flexicap,14.2,15.4,#EFAC85,2026-04-10,#EFAC85")
        if pasted.strip():
            try:
                new_df = pd.read_csv(io.StringIO(pasted), parse_dates=["date"])
            except Exception as e:
                st.sidebar.error(f"Parse error: {e}")

    if new_df is not None:
        new_df.columns = [c.strip().lower() for c in new_df.columns]
        missing = [c for c in ["name","y","z","date"] if c not in new_df.columns]
        if missing:
            st.sidebar.error(f"Missing columns: {missing}")
            return
        # Fill optional cols
        for col in ["color","spread_color"]:
            if col not in new_df.columns:
                new_df[col] = "#CCCCCC"

        st.sidebar.dataframe(new_df[REQUIRED_COLS].head(10), use_container_width=True)
        st.sidebar.caption(f"{len(new_df)} rows to append")

        if st.sidebar.button("✅ Append to Google Sheet", type="primary"):
            with st.spinner("Appending…"):
                try:
                    n = append_rows(new_df[REQUIRED_COLS])
                    st.sidebar.success(f"Appended {n} rows!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Failed: {e}")


# ── Main ─────────────────────────────────────────────────────────────────────

st.title("📈 MF Dashboard")

col1, col2 = st.columns([6, 1])
with col2:
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()

sidebar_add_data()

df = get_data()

if df.empty:
    st.warning("No data found in Google Sheet. Add data using the sidebar.")
    st.stop()

st.caption(f"Loaded {len(df):,} rows · {df['date'].dt.strftime('%Y-%m-%d').nunique()} dates · {df['name'].nunique()} funds · Last updated: {df['date'].max().strftime('%d %b %Y')}")

with st.spinner("Building charts…"):
    chart_html = build_chart_html(df)

# Render the Highcharts dashboard — height sized to fit 3 tabs + controls
st.components.v1.html(chart_html, height=900, scrolling=False)
