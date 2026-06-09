import streamlit as st
import pandas as pd
import json
import base64
from datetime import datetime
from data_layer import load_data, load_portfolio_growth

st.set_page_config(page_title="MF Dashboard", layout="wide", page_icon="📈")

# ── Password gate ────────────────────────────────────────────────────────────

def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.title("📈 MF Dashboard")
    with st.form("login_form"):
        pwd = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
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

@st.cache_data(ttl=300, show_spinner="Loading portfolio growth data…")
def get_portfolio_growth():
    return load_portfolio_growth()


# ── Build chart HTML ─────────────────────────────────────────────────────────

SPECIAL_BOTTOM_MFS = {
    "Mirae Asset Liquid", "Mirae Asset Cash Mgmt", "HSBC Cash", "UTI Liquid",
    "Axis Liquid Fund", "Bandhan Liquid Fund", "HDFC Liquid Fund (G)",
    "Kotak Liquid Fund Reg(G)", "Parag Parikh Liquid Fund Reg (G)",
}

def build_chart_html(df: pd.DataFrame, df_growth: pd.DataFrame) -> str:
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

    # Tab 4: Portfolio Growth
    growth_rows = []
    for _, row in df_growth.iterrows():
        growth_rows.append({
            "date":          row["date"].strftime("%Y-%m-%d"),
            "stocks":        float(row["stocks"]),
            "mfs":           float(row["mfs"]),
            "total":         float(row["total"]),
            "monthly_delta": float(row["monthly_delta"]),
        })
    js_portfolio_growth_json = json.dumps(growth_rows)

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
    html = html.replace("JS_PORTFOLIO_GROWTH_JSON", js_portfolio_growth_json)
    return html




# ── Main ─────────────────────────────────────────────────────────────────────

st.markdown("""
    <style>
        .block-container { padding-top: 3.5rem; padding-bottom: 0; }
    </style>
""", unsafe_allow_html=True)

df        = get_data()
df_growth = get_portfolio_growth()

if df.empty:
    st.warning("No data found in Google Sheet.")
    st.stop()

growth_range = (
    f" · Growth: {df_growth['date'].min().strftime('%b %Y')} – {df_growth['date'].max().strftime('%b %Y')}"
    if not df_growth.empty else ""
)

col1, col2 = st.columns([8, 1])
with col1:
    st.markdown(
        f"#### 📈 MF Dashboard &nbsp; <small style='color:gray;font-size:0.75rem'>"
        f"Loaded {len(df):,} rows · {df['date'].dt.strftime('%Y-%m-%d').nunique()} dates · "
        f"{df['name'].nunique()} funds · Last updated: {df['date'].max().strftime('%d %b %Y')}"
        f"{growth_range} · Refreshed: {datetime.now().strftime('%d %b %Y, %H:%M')}</small>",
        unsafe_allow_html=True,
    )
with col2:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

with st.spinner("Building charts…"):
    chart_html = build_chart_html(df, df_growth)

b64 = base64.b64encode(chart_html.encode("utf-8")).decode("utf-8")
data_uri = f"data:text/html;base64,{b64}"
st.iframe(data_uri, height=820)
