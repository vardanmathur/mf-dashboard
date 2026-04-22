import http.server
import socketserver
import webbrowser
import pandas as pd
from datetime import datetime
import json
import os

today = datetime.today()
formatted_date = today.strftime("%B %Y")
title_text = f"MF XIRRs, {formatted_date}"

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, "chart.html")
EXCEL_FILE = os.path.join(BASE_DIR, "mf_data_withdate.xlsx")

# Data loading/normalization
df = pd.read_excel(EXCEL_FILE, parse_dates=["date"])
df.columns = [col.strip().lower() for col in df.columns]

unique_dates = sorted(df["date"].dt.strftime("%Y-%m-%d").unique())
unique_mfs = sorted(df["name"].unique())

# Tab 1: Datewise variwide data
date_data_dict = {}
for date_str in unique_dates:
    dframe = df[df["date"].dt.strftime("%Y-%m-%d") == date_str].sort_values(by="y", ascending=False)
    data_list = []
    for _, row in dframe.iterrows():
        data_list.append({
            "name": str(row["name"]),
            "y": float(row["y"]),
            "z": float(row["z"]),
            "color": str(row["color"]),
        })
    date_data_dict[date_str] = data_list
js_date_periods_json = json.dumps(date_data_dict)

dropdown_options_html = "\n".join([
    f'<option value="{date_str}">{date_str}</option>' for date_str in unique_dates
])

# Tab 2: MF time series
mf_time_series_dict = {}
for mf in unique_mfs:
    dframe = df[df["name"] == mf].sort_values("date")
    records = []
    for _, row in dframe.iterrows():
        records.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "y": float(row["y"]),
            "z": float(row["z"]),
            "color": str(row["color"]),
        })
    mf_time_series_dict[mf] = records
js_mf_timeseries_json = json.dumps(mf_time_series_dict)

mf_dropdown_options_html = "\n".join([
    f'<option value="{mf}">{mf}</option>' for mf in unique_mfs
])

# Tab 3: MF spread over time (100% stacked by z)
df_spread = df.copy()
df_spread["date_str"] = df_spread["date"].dt.strftime("%Y-%m-%d")

if "spread_color" not in df_spread.columns:
    df_spread["spread_color"] = pd.NA

date_totals = df_spread.groupby("date_str")["z"].sum().rename("total_z")
df_spread = df_spread.merge(date_totals, left_on="date_str", right_index=True, how="left")
df_spread["total_z"] = df_spread["total_z"].replace(0, pd.NA)
df_spread["pct"] = (df_spread["z"] / df_spread["total_z"]) * 100

spread_dates = sorted(df_spread["date_str"].unique())
spread_date_index = {d: i for i, d in enumerate(spread_dates)}

latest_date_str = max(spread_dates)
latest_df = df_spread[df_spread["date_str"] == latest_date_str].copy()
current_holdings = latest_df[latest_df["z"] > 0][["name", "z"]].copy()
current_holdings.rename(columns={"z": "latest_z"}, inplace=True)

max_hist = (
    df_spread.groupby("name")["z"]
    .max()
    .reset_index()
    .rename(columns={"z": "max_z"})
)

SPECIAL_BOTTOM_MFS = {
    "Mirae Asset Liquid",
    "Mirae Asset Cash Mgmt",
    "HSBC Cash",
    "UTI Liquid",
    "Axis Liquid Fund",
    "Bandhan Liquid Fund",
    "HDFC Liquid Fund (G)",
    "Kotak Liquid Fund Reg(G)",
    "Parag Parikh Liquid Fund Reg (G)",
}

priority_df = max_hist.merge(current_holdings, on="name", how="left")
priority_df["is_current"] = priority_df["latest_z"].fillna(0) > 0
priority_df["latest_z"] = priority_df["latest_z"].fillna(0)
priority_df["is_current_int"] = priority_df["is_current"].astype(int)
priority_df["special_priority"] = priority_df["name"].apply(
    lambda n: 1 if n in SPECIAL_BOTTOM_MFS else 0
)
priority_df = priority_df.sort_values(
    by=["special_priority", "is_current_int", "latest_z", "max_z"],
    ascending=[True, False, False, False],
)
ordered_mfs_for_spread = list(priority_df["name"])

mf_spread_series = []
for mf in ordered_mfs_for_spread:
    sub = df_spread[df_spread["name"] == mf].copy()
    if sub["pct"].notna().sum() == 0:
        continue
    sub = sub.sort_values("date")
    pts = []
    color = None
    for _, row in sub.iterrows():
        if pd.isna(row["pct"]):
            continue
        x_idx = spread_date_index[row["date_str"]]
        pts.append([x_idx, float(row["pct"])])
        if color is None:
            sc_val = row.get("spread_color")
            sc = "" if pd.isna(sc_val) else str(sc_val).strip()
            color = sc if sc else str(row["color"])
    if pts:
        mf_spread_series.append({"name": mf, "data": pts, "color": color})

mf_spread_series = mf_spread_series[::-1]

js_mf_spread_json = json.dumps(mf_spread_series)
js_mf_spread_categories = json.dumps(spread_dates)

# ── FIX: derive real default funds from the two largest current holdings
# (excludes liquid/cash funds so the trend chart is meaningful by default)
non_liquid = [
    mf for mf in
    df[df["date"] == df["date"].max()].sort_values("z", ascending=False)["name"].tolist()
    if mf not in SPECIAL_BOTTOM_MFS
]
default_funds_js = json.dumps(non_liquid[:2])   # e.g. ["HDFC flexicap", "PPFAS flexicap (Regular)"]


# ─────────────────────────────────────────────
#  HTML TEMPLATE
#  Rules:
#   - Pure JS/CSS single-brace blocks stay as-is (they won't be touched by replace())
#   - Highcharts config objects use {{ }} so the final replace("{{","{") gives valid JS
#   - Data placeholders are unique ALLCAPS tokens replaced explicitly at the end
# ─────────────────────────────────────────────
html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>MF Dashboard</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/choices.js/public/assets/styles/choices.min.css" />
    <script src="https://cdn.jsdelivr.net/npm/choices.js/public/assets/scripts/choices.min.js"></script>

    <!--
        FIX 1: Load standard highcharts.js for Tabs 1 & 3 (variwide / area charts).
        highstock.js is loaded AFTER so Highcharts.stockChart() is also available for Tab 2.
        Both modules share the same Highcharts namespace; loading stock after core is the
        recommended pattern when you need both chart() and stockChart() on one page.
    -->
    <script src="https://cdn.jsdelivr.net/npm/highcharts/highcharts.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highcharts/modules/variwide.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highcharts/modules/stock.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highcharts/modules/exporting.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highcharts/modules/export-data.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highcharts/modules/accessibility.js"></script>
    <style>
        body { font-family: Verdana, sans-serif; background-color: #f7f9fc; }
        .choices__list--dropdown .choices__item[aria-disabled="true"] {
            font-weight: 700; background: #f0f0f0; cursor: default;
        }
        .choices__list--dropdown .choices__item--group {
            font-weight: 700; background: #f0f0f0; cursor: default; pointer-events: none;
        }
        .tablink {
            font-size: 18px; padding: 8px 25px; cursor: pointer;
            border: 2px solid #aaa; outline: none; color: #222; margin-right: 5px;
            border-radius: 7px 7px 0 0; background: #e3f2fd;
        }
        .tablink.active, .tablink:hover { font-weight: bold; border-bottom: 2px solid #1976d2; }
        #chartTab.tabcontent  { background: #e3f2fd; }
        #mfTab.tabcontent     { background: #fffde7; }
        #spreadTab.tabcontent { background: #e8f5e9; }
        .tabcontent { display: none; border: 1px solid #ccc; border-top: none; padding: 0 0 25px 0; }
        #container, #mfChart, #mfSpreadChart { height: 700px; width: 1500px; }
        .controls { margin: 10px 0 24px 0; }
        .highcharts-description { margin: 0.3rem 10px; }
        select[multiple] { min-width: 350px; height: 2.5em; font-size: 15px; }
    </style>
</head>
<body>

<div>
    <button class="tablink" onclick="openTab(event,'chartTab')" id="defaultTab">Bar Chart by Date</button>
    <button class="tablink" onclick="openTab(event,'mfTab')">XIRR Trend for MF</button>
    <button class="tablink" onclick="openTab(event,'spreadTab')">MF Spread (100% Stacked)</button>
</div>

<!-- TAB 1 -->
<div id="chartTab" class="tabcontent">
    <div class="controls">
        <label for="dateSelect" style="font-size:18px;">Select date:</label>
        <select id="dateSelect" style="font-size:16px;">
            DROPDOWN_OPTIONS_HTML
        </select>
        <label for="yTruncate" style="font-size:18px; margin-left:40px;">Maximum XIRR (%):</label>
        <input type="number" id="yTruncate" style="font-size:16px;width:90px;" value="80"/>
        <span style="font-size:15px; color:#888;">(Bars above this % will be truncated)</span>
        <label style="font-size:16px; margin-left:40px;">
            <input type="checkbox" id="sortByY" checked />
            Sort bars by XIRR (%) [uncheck for MF Value (Bar Width)]
        </label>
    </div>
    <figure class="highcharts-figure">
        <div id="container"></div>
        <p class="highcharts-description">
            Variwide chart: Y-axis = XIRR%, bar width = MF portfolio value.
        </p>
    </figure>
</div>

<!-- TAB 2 -->
<div id="mfTab" class="tabcontent">
    <div style="margin:10px 0;">
        <label for="mfSelect" style="font-size:18px;">Select Mutual Fund(s):</label>
        <select id="mfSelect" multiple style="font-size:16px; width:500px">
            MF_DROPDOWN_OPTIONS_HTML
        </select>
        <span style="font-size:10px; color:#999;">(Hold Ctrl/Cmd to multi-select)</span>
    </div>
    <div id="mfChart"></div>
</div>

<!-- TAB 3 -->
<div id="spreadTab" class="tabcontent">
    <div style="margin:10px 0 5px 10px; font-size:18px;">
        MF spread over time (each column = 100% of portfolio; colors = funds)
    </div>
    <div style="margin:10px 0 10px 10px;">
        <label for="spreadDateSelect" style="font-size:16px;">Select dates to display:</label>
        <select id="spreadDateSelect" multiple style="font-size:14px; width:400px;"></select>
        <span style="font-size:10px; color:#999;">(Hold Ctrl/Cmd to multi-select)</span>
        <button id="spreadResetBtn"     style="margin-left:10px; font-size:12px; padding:4px 8px;">Reset selection</button>
        <button id="spreadSelectAllBtn" style="margin-left:6px;  font-size:12px; padding:4px 8px;">Select all</button>
        <button id="spreadSelectTwoBtn" style="margin-left:6px;  font-size:12px; padding:4px 8px;">Select 2 per year</button>
    </div>
    <div id="mfSpreadChart"></div>
</div>


<script>
// ── Injected data ──────────────────────────────────────────────────────────
const rawChartDataDates  = JS_DATE_PERIODS_JSON;
const mfTimeSeriesData   = JS_MF_TIMESERIES_JSON;
const mfSpreadSeries     = JS_MF_SPREAD_JSON;
const mfSpreadCategories = JS_MF_SPREAD_CATEGORIES;
// ──────────────────────────────────────────────────────────────────────────


// ── Tab switching ──────────────────────────────────────────────────────────
function openTab(evt, tabName) {
    Array.from(document.getElementsByClassName("tabcontent")).forEach(t => t.style.display = "none");
    Array.from(document.getElementsByClassName("tablink")).forEach(t => t.classList.remove("active"));
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.classList.add("active");

    // FIX 2: Highcharts renders into a 0-size container when the tab is hidden.
    // Reflowing after the tab becomes visible fixes blank charts on first open.
    if (tabName === "chartTab"  && window._barChart)    window._barChart.reflow();
    if (tabName === "mfTab"     && window._mfChart)     window._mfChart.reflow();
    if (tabName === "spreadTab" && window._spreadChart) window._spreadChart.reflow();
}


// ── DOMContentLoaded ───────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {

    // --- Tab 1 init ---
    // Select latest date by default
    const dateSelect = document.getElementById("dateSelect");
    dateSelect.selectedIndex = dateSelect.options.length - 1;
    drawBarChart();
    dateSelect.addEventListener("change", drawBarChart);
    document.getElementById("yTruncate").addEventListener("input", drawBarChart);
    document.getElementById("sortByY").addEventListener("change", drawBarChart);

    // --- Tab 2 init ---
    window.mfChoices = new Choices(document.getElementById("mfSelect"), {
        removeItemButton: true,
        searchEnabled: true,
        shouldSort: false,
        placeholder: true,
        placeholderValue: "Select Mutual Funds"
    });

    // FIX 3: use real fund names derived from latest date data, not hardcoded strings
    const initialFunds = DEFAULT_FUNDS_JS;
    window.mfChoices.setChoiceByValue(initialFunds);

    const initialSelected = Array.from(document.getElementById("mfSelect").selectedOptions).map(o => o.value);
    if (initialSelected.length > 0) drawMFChart(initialSelected);

    document.getElementById("mfSelect").addEventListener("change", function () {
        const sel = Array.from(this.selectedOptions).map(o => o.value);
        if (sel.length > 0) drawMFChart(sel);
    });

    // --- Tab 3 init ---
    const spreadDateSelect = document.getElementById("spreadDateSelect");

    // Build year-grouped choices list
    const yearMap = {};
    mfSpreadCategories.forEach((d, idx) => {
        const y = d.slice(0, 4);
        if (!yearMap[y]) yearMap[y] = [];
        yearMap[y].push({ date: d, idx: idx });
    });

    const choicesData = [];
    Object.keys(yearMap).sort((a, b) => b - a).forEach(year => {
        choicesData.push({ value: `__year_${year}`, label: year, disabled: true });
        yearMap[year].forEach(item => {
            choicesData.push({ value: String(item.idx), label: item.date });
        });
    });

    window.spreadDateChoices = new Choices(spreadDateSelect, {
        removeItemButton: true,
        searchEnabled: true,
        shouldSort: false,
        placeholder: true,
        placeholderValue: "Select dates (default: 2 per year)"
    });
    window.spreadDateChoices.setChoices(choicesData, "value", "label", true);

    function applySelection(values) {
        const vals = (values || []).map(v => String(v));
        for (let i = 0; i < spreadDateSelect.options.length; i++) {
            spreadDateSelect.options[i].selected = false;
        }
        vals.forEach(v => {
            const opt = spreadDateSelect.querySelector(`option[value="${v}"]`);
            if (opt) opt.selected = true;
        });
        try { window.spreadDateChoices.removeActiveItems(); } catch (e) {}
        if (vals.length > 0) {
            try { window.spreadDateChoices.setChoiceByValue(vals); } catch (e) {}
        }
        spreadDateSelect.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function pickTwoPerYear(map) {
        const out = [];
        Object.keys(map).sort((a, b) => b - a).forEach(year => {
            const items = (map[year] || []).slice();
            if (!items.length) return;
            const latest = items[items.length - 1];
            out.push(String(latest.idx));
            if (items.length > 1) {
                const midTs = Math.floor(
                    (new Date(items[0].date).getTime() + new Date(latest.date).getTime()) / 2
                );
                let mid = null, minDiff = Infinity;
                items.forEach(it => {
                    const diff = Math.abs(new Date(it.date).getTime() - midTs);
                    if (diff < minDiff && it.idx !== latest.idx) { minDiff = diff; mid = it; }
                });
                if (mid) out.push(String(mid.idx));
            }
        });
        return out;
    }

    const initialSpread = pickTwoPerYear(yearMap);
    applySelection(initialSpread);
    drawMFSpreadChart(initialSpread.map(v => parseInt(v, 10)));

    document.getElementById("spreadResetBtn").addEventListener("click", () => {
        applySelection([]); drawMFSpreadChart([]);
    });
    document.getElementById("spreadSelectAllBtn").addEventListener("click", () => {
        const all = mfSpreadCategories.map((_, i) => String(i));
        applySelection(all); drawMFSpreadChart(all.map(v => parseInt(v, 10)));
    });
    document.getElementById("spreadSelectTwoBtn").addEventListener("click", () => {
        const two = pickTwoPerYear(yearMap);
        applySelection(two); drawMFSpreadChart(two.map(v => parseInt(v, 10)));
    });
    spreadDateSelect.addEventListener("change", function () {
        const sel = Array.from(this.selectedOptions).map(o => parseInt(o.value, 10));
        drawMFSpreadChart(sel);
    });

    // Open Tab 1 last so it's visible and renders at full size immediately
    document.getElementById("defaultTab").click();
});


// ── Tab 1: Variwide chart ──────────────────────────────────────────────────
function getTruncatedDataForDate(dateKey, yLimit) {
    return (rawChartDataDates[dateKey] || []).map(row => {
        const obj = { ...row };
        if (obj.y > yLimit) obj.y = yLimit;
        return obj;
    });
}
function getWeightedAvg(data) {
    let wy = 0, tz = 0;
    data.forEach(p => { wy += p.y * p.z; tz += p.z; });
    return tz > 0 ? wy / tz : 0;
}
function formatMonthYear(s) {
    const d = new Date(s);
    return ["January","February","March","April","May","June",
            "July","August","September","October","November","December"][d.getMonth()]
           + " " + d.getFullYear();
}
function getMinY(data) {
    if (!data.length) return 0;
    return Math.floor(Math.min(...data.map(p => p.y)) - 2);
}
function drawBarChart() {
    const selectedDate = document.getElementById("dateSelect").value;
    const yLimit = parseFloat(document.getElementById("yTruncate").value) || 80;
    const data = getTruncatedDataForDate(selectedDate, yLimit);
    const weightedAvg = getWeightedAvg(data);
    if (document.getElementById("sortByY").checked) {
        data.sort((a, b) => b.y - a.y);
    } else {
        data.sort((a, b) => b.z - a.z);
    }
    window._barChart = Highcharts.chart("container", {
        chart: { type: "variwide" },
        title: { text: "MF XIRRs, " + formatMonthYear(selectedDate) },
        xAxis: {
            type: "category", tickInterval: 1,
            labels: { autoRotation: [0, -45, -90], style: { fontSize: "13px", whiteSpace: "nowrap" }, step: 1, crop: false, reserveSpace: true }
        },
        yAxis: {
            min: getMinY(data),
            title: { text: "XIRR (%)", style: { fontSize: "20px" } },
            labels: { style: { fontSize: "15px" } },
            plotLines: [{
                color: "red", dashStyle: "dash", value: weightedAvg, width: 2,
                label: { text: "Wt Average: " + weightedAvg.toFixed(2) + "%", align: "right", style: { color: "red", fontWeight: "bold" } }
            }]
        },
        legend: { enabled: false },
        series: [{
            name: "MF XIRR", data: data, borderRadius: 3, colorByPoint: true,
            dataLabels: { enabled: true, format: "{point.y:.1f}%", style: { fontSize: "16px" } },
            tooltip: { valueDecimals: 1, pointFormat: "XIRR: <b>{point.y}%</b><br>Contrib: <b>{point.z}%</b>" }
        }]
    });
}


// ── Tab 2: XIRR trend (Stock chart) ───────────────────────────────────────
function buildMFSeries(selectedMfs) {
    return selectedMfs.map(mf => {
        const arr = mfTimeSeriesData[mf] || [];
        return {
            name: mf,
            data: arr.filter(o => o.y !== null && o.y !== undefined).map(o => ({ x: new Date(o.date).getTime(), y: o.y, name: o.date })),
            colorByPoint: false,
            color: arr[0] ? arr[0].color : undefined,
            marker: { enabled: true, symbol: "circle" }
        };
    });
}
function drawMFChart(selectedMfs) {
    const newTitle = "XIRR Trend: " + (selectedMfs.length > 1 ? selectedMfs.join(", ") : selectedMfs[0]);
    const newSeries = buildMFSeries(selectedMfs);

    // If chart already exists, update series in-place to preserve zoom/range
    if (window._mfChart) {
        const chart = window._mfChart;

        // Save current axis extremes so zoom is not reset
        const xAxis = chart.xAxis[0];
        const savedMin = xAxis.userMin !== undefined ? xAxis.userMin : xAxis.min;
        const savedMax = xAxis.userMax !== undefined ? xAxis.userMax : xAxis.max;

        // Remove old series (iterate in reverse to avoid index shifting)
        while (chart.series.length > 0) {
            chart.series[0].remove(false);
        }
        // Add new series
        newSeries.forEach(s => chart.addSeries(s, false));

        // Update title
        chart.setTitle({ text: newTitle }, null, false);

        // Restore zoom
        if (savedMin !== undefined && savedMax !== undefined) {
            xAxis.setExtremes(savedMin, savedMax, false);
        }

        chart.redraw();
        return;
    }

    // First render — create the chart fresh
    window._mfChart = Highcharts.stockChart("mfChart", {
        rangeSelector: { selected: 0 },
        navigator: { enabled: true },
        title: { text: newTitle },
        xAxis: { type: "datetime", title: { text: "Date" }, labels: { format: "{value:%Y-%m-%d}", rotation: -45 } },
        yAxis: { title: { text: "XIRR (%)" } },
        tooltip: { useHTML: true, valueDecimals: 2, headerFormat: "", pointFormat: "<b>{series.name}</b><br/>XIRR: <b>{point.y:.2f}%</b>" },
        series: newSeries
    });
}


// ── Tab 3: MF spread (100% stacked area) ──────────────────────────────────
function drawMFSpreadChart(selectedIndices) {
    selectedIndices = (selectedIndices || []).slice().sort((a, b) => a - b);
    const filteredCategories = selectedIndices.map(i => mfSpreadCategories[i]);
    const filteredSeries = mfSpreadSeries.map(s => {
        const filteredData = s.data
            .filter(pt => selectedIndices.indexOf(pt[0]) !== -1)
            .map(pt => [selectedIndices.indexOf(pt[0]), pt[1]]);
        return Object.assign({}, s, { data: filteredData });
    });
    window._spreadChart = Highcharts.chart("mfSpreadChart", {
        chart: { type: "area" },
        title: { text: "MF Spread Over Time (Portfolio % by MF)" },
        xAxis: {
            categories: filteredCategories,
            title: { text: "Date" },
            labels: { rotation: -45 }
        },
        yAxis: {
            min: 0, max: 100,
            title: { text: "Portfolio share (%)" },
            labels: { format: "{value}%" }
        },
        legend: { enabled: true },
        tooltip: {
            shared: false,
            formatter: function () {
                return "<b>" + filteredCategories[this.point.x] + "</b><br/>" +
                       '<span style="color:' + this.point.color + '">●</span> ' +
                       this.series.name + ": <b>" + Highcharts.numberFormat(this.point.y, 2) + "%</b>";
            }
        },
        plotOptions: {
            area: {
                stacking: "percent", lineWidth: 0, fillOpacity: 0.6,
                marker: { enabled: true, radius: 2 },
                reversedStacks: false
            },
            series: { animation: false }
        },
        series: filteredSeries
    });
}
</script>
</body>
</html>
"""

# Inject data — MF_DROPDOWN_OPTIONS_HTML must be replaced BEFORE DROPDOWN_OPTIONS_HTML
# because the former contains the latter as a substring; reversing the order causes dates
# to be injected into the MF select (the bug that showed dates instead of fund names).
html_content = html_content.replace("MF_DROPDOWN_OPTIONS_HTML", mf_dropdown_options_html)
html_content = html_content.replace("DROPDOWN_OPTIONS_HTML",    dropdown_options_html)
html_content = html_content.replace("JS_DATE_PERIODS_JSON",     js_date_periods_json)
html_content = html_content.replace("JS_MF_TIMESERIES_JSON",    js_mf_timeseries_json)
html_content = html_content.replace("JS_MF_SPREAD_JSON",        js_mf_spread_json)
html_content = html_content.replace("JS_MF_SPREAD_CATEGORIES",  js_mf_spread_categories)
html_content = html_content.replace("DEFAULT_FUNDS_JS",         default_funds_js)

with open(HTML_FILE, "w", encoding="utf-8") as f:
    f.write(html_content)
print(f"chart.html written ({len(html_content):,} bytes)")

Handler = http.server.SimpleHTTPRequestHandler
os.chdir(BASE_DIR)
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving at http://localhost:{PORT}")
    webbrowser.open(f"http://localhost:{PORT}/{os.path.basename(HTML_FILE)}")
    httpd.serve_forever()
