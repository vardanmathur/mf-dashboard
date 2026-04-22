# MF Dashboard — Streamlit Web App

Password-protected Streamlit app that replicates `mekkocharts_v5.py` as a hosted web dashboard.

---

## Repo structure

```
mf-dashboard/
├── app.py                   ← main Streamlit app
├── data_layer.py            ← Google Sheets read/write
├── chart_template.html      ← Highcharts HTML (extracted from mekkocharts_v5)
├── requirements.txt
├── .gitignore
└── .streamlit/
    └── secrets.toml         ← passwords + GCP creds (NOT in git)
```

---

## One-time setup (do this once, ~20 mins)

### Step 1 — Create the Google Sheet

1. Create a new Google Sheet
2. Rename the first tab to exactly: `mf_data`
3. Add these headers in row 1 (exact case):
   ```
   name | y | z | color | date | spread_color
   ```
4. Copy all your data from `mf_data_withdate.xlsx` into the sheet
   - `date` column should be formatted as `YYYY-MM-DD` (plain text or date, both work)
5. Copy the sheet URL — you'll need it for secrets.toml


### Step 2 — Create a GCP Service Account

1. Go to https://console.cloud.google.com
2. Create a new project (or use an existing one)
3. Enable these two APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
   - Name: `mf-dashboard-reader` (anything)
   - Role: not required at project level
5. Click the service account → **Keys → Add Key → Create new key → JSON**
6. Download the JSON file — you'll paste its contents into `secrets.toml`


### Step 3 — Share the sheet with the service account

1. Open the JSON key file — copy the `client_email` value (looks like `xxx@xxx.iam.gserviceaccount.com`)
2. Open your Google Sheet → Share → paste that email → give **Editor** access
   - Editor is needed so the app can append rows


### Step 4 — Fill in secrets.toml

Edit `.streamlit/secrets.toml`:

```toml
[app]
password = "pick_a_strong_password"

[google_sheets]
url = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"

[gcp_service_account]
type = "service_account"
project_id = "..."
# paste all fields from the downloaded JSON key file
```

**Never commit this file.** It's in `.gitignore`.


### Step 5 — Deploy to Streamlit Community Cloud

1. Push the repo to GitHub (secrets.toml is gitignored, so it won't be included)
2. Go to https://share.streamlit.io → **New app**
3. Connect your GitHub repo, set main file to `app.py`
4. Before clicking Deploy: go to **Advanced settings → Secrets**
5. Paste the full contents of your `secrets.toml` there
6. Deploy

That's it. The app will be live at `https://your-app-name.streamlit.app`.
Since it's behind a password gate, the URL alone won't get anyone in.


---

## Adding data

Three ways, all from the sidebar inside the app:

| Method | When to use |
|--------|-------------|
| Upload Excel | Your monthly update is already in `.xlsx` format |
| Upload CSV | Exported from another tool |
| Paste CSV | Quick one-off additions — just type/paste a few rows |

All three deduplicate on `(name, date)` before writing, so re-uploading an old file won't create duplicate rows.

**CSV format for pasting:**
```
name,y,z,color,date,spread_color
HDFC flexicap,14.2,15.4,#EFAC85,2026-04-10,#EFAC85
PPFAS flexicap (Regular),13.1,14.3,#6D9EEB,2026-04-10,#6D9EEB
```


---

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Make sure `.streamlit/secrets.toml` is filled in before running locally.


---

## Refreshing data

The app caches data for 5 minutes (`ttl=300`). After adding data:
- Hit the **🔄 Refresh data** button in the top right, or
- Wait 5 minutes and it auto-refreshes


---

## Notes

- The Highcharts charts are identical to `mekkocharts_v5.py` — same tabs, same logic, same colors
- The password gate is session-based (cookie persists until browser closes)
- For stronger auth (multi-user, audit log), consider upgrading to Streamlit's built-in auth via `st.login()` available in Streamlit ≥ 1.40
