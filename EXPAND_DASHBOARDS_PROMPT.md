# Context: MF Dashboard — expanding with new dashboards from Excel

I have a Streamlit web app that visualises mutual fund portfolio data. I want to add new dashboard tabs based on additional data I track in an Excel file (attached). Please analyse the Excel and suggest what new dashboards make sense, then give me concrete implementation instructions.

---

## Current app architecture

**Stack:** Python · Streamlit · Highcharts (via `st.components.v1.html`) · Google Sheets (as the database) · gspread

**How charts work:**
- All charts live in a single `chart_template.html` file as Highcharts JS
- `app.py` builds a Python dict/list from a pandas DataFrame, serialises it to JSON, and injects it into the template via simple string replacement (e.g. `html.replace("JS_DATE_PERIODS_JSON", json.dumps(...))`)
- The whole template is rendered in one `st.components.v1.html(chart_html, height=680)` call — no iframes-within-iframes

**Google Sheet schema (tab: `mf_data`):**
```
name | y | z | color | date | spread_color
```
- `name` — fund name (string)
- `y` — a return/performance metric (float)
- `z` — AUM / size / weight (float)
- `color` — hex color for that fund
- `date` — snapshot date (YYYY-MM-DD)
- `spread_color` — optional separate hex color for the spread chart

**Existing tabs in `chart_template.html`:**
1. **Snapshot** — bubble/bar chart of all funds for a selected date, sorted by `y`
2. **Time series** — line chart for selected funds over time (y-axis = `y` value)
3. **Spread** — stacked area/bar chart showing each fund's % of total `z` over time

**Key files:**
- `app.py` — Streamlit UI, password gate, `build_chart_html()` function, sidebar data-entry
- `data_layer.py` — `load_data()` and `append_rows()` via gspread
- `chart_template.html` — all Highcharts HTML/JS
- `requirements.txt` — streamlit, pandas, gspread, google-auth, openpyxl

**Data flow:**
```
Google Sheet → data_layer.load_data() → pd.DataFrame → build_chart_html() → chart_template.html (string replace) → st.components.v1.html()
```

---

## What I need from you

**Step 1 — Analyse the Excel**
- Look at every sheet/tab in the attached Excel
- For each tab, describe: what data is there, what columns exist, what time period it covers, what it seems to be tracking
- Identify which tabs contain data that could become a dashboard chart

**Step 2 — Propose new dashboards**
For each proposed dashboard:
- Give it a tab name
- Describe what the chart shows and why it's useful
- State which Excel sheet(s) feed it
- Suggest the Highcharts chart type (line, bar, column, pie, scatter, area, etc.)
- List what new Google Sheet tab(s) or columns would be needed

**Step 3 — Data model**
- Propose a Google Sheet schema for each new data source (column names, types, example row)
- Flag if any existing `mf_data` columns are sufficient vs. needing a new sheet tab

**Step 4 — Implementation plan**
Give me a step-by-step plan covering:
1. Google Sheet changes (new tabs, columns)
2. `data_layer.py` changes (new `load_*` functions, new `append_*` functions)
3. `app.py` changes (new JSON-building logic in `build_chart_html`, new sidebar upload paths)
4. `chart_template.html` changes (new tab HTML + Highcharts JS blocks, new placeholder strings)
5. Any new `requirements.txt` dependencies

**Step 5 — Code**
Write the actual code for each change above. Be specific:
- Show full function bodies, not pseudocode
- For `chart_template.html` additions, write the complete Highcharts JS config for each new chart
- For `data_layer.py`, write the new load/append functions following the same pattern as existing ones
- For `app.py`, show where in `build_chart_html()` to add the new data-prep logic and what placeholder strings to use

---

## Constraints / preferences
- Keep the single-HTML approach — no new `st.components` calls if possible; add new tabs inside the existing `chart_template.html`
- Match the visual style of existing charts (same font, same toolbar, same color palette approach)
- New Google Sheet tabs should follow the same simple flat-table pattern as `mf_data`
- Deduplication logic in `append_rows` should be replicated for any new append functions
- The Streamlit sidebar upload flow should support Excel and CSV for any new data types

---

## Attached
- My Excel file with the additional data I want to visualise (see attachment)
