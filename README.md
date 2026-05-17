# 🛰️ Space Supply Chain Risk Intelligence

A data pipeline and interactive dashboard that extracts, classifies, and visualizes supply chain risk signals from SEC 10-K filings for major space industry companies.

Built as part of a graduate research project at the University of Texas.

---

## 📌 Project Overview

Space companies rely on highly specialized suppliers, rare materials, and complex regulatory environments. This project automates the extraction of supply chain risk language from annual SEC filings and surfaces it through an interactive Streamlit dashboard — enabling structured comparison across companies and risk categories.

---

## 🗂️ Project Structure

```
space-supply-chain-risk/
│
├── edgar_risk_factors.py          # Phase 1 — Fetches 10-K filings from SEC EDGAR
├── build_risk_table.py            # Phase 2 — Keyword tagging & CSV builder
├── validate_risk_table.py         # Phase 2b — LLM context validation via Claude API
├── supply_chain_dashboard.py      # Phase 3 — Streamlit dashboard
│
├── master_risk_table_validated.csv  # Clean, validated risk signal dataset
│
├── risk_factors/                  # Raw extracted Risk Factors text (one .txt per company)
│   ├── RKLB_risk_factors.txt
│   ├── LMT_risk_factors.txt
│   ├── ... (one file per company)
│   └── _manifest.json             # Run summary metadata
│
└── README.md
```

---

## 🏢 Companies Covered

| Company | Ticker | Segment |
|---|---|---|
| Rocket Lab USA | RKLB | Small launch / spacecraft |
| Intuitive Machines | LUNR | Lunar logistics |
| Redwire Corporation | RDW | Space infrastructure |
| Virgin Galactic | SPCE | Commercial spaceflight |
| Planet Labs | PL | Earth observation |
| Spire Global | SPIR | Satellite data & analytics |
| Momentus | MNTS | In-space transportation |
| Lockheed Martin | LMT | Defense & space prime |
| Northrop Grumman | NOC | Defense & space prime |
| L3Harris Technologies | LHX | Defense electronics |
| Boeing | BA | Defense & space prime |
| Raytheon Technologies | RTX | Defense & space prime |

All filings are the most recent 10-K available on SEC EDGAR as of FY2025.

---

## ⚙️ Pipeline Overview

### Phase 1 — Data Collection (`edgar_risk_factors.py`)
- Connects to SEC EDGAR's public API (no account needed)
- Resolves company tickers to CIK numbers
- Downloads the most recent 10-K filing for each company
- Handles modern iXBRL-formatted filings
- Extracts the **Risk Factors** section (Item 1A) as plain text
- Saves one `.txt` file per company with metadata header

### Phase 2 — Risk Tagging (`build_risk_table.py`)
- Reads the extracted Risk Factors text files
- Applies a keyword taxonomy across **6 risk categories** and ~90 keyword patterns:
  - Supplier Concentration
  - Geopolitical Risk
  - Export Control & Regulatory
  - Material & Component Shortage
  - Manufacturing & Production Risk
  - Technology & Cyber Risk
- Scores each match by severity (1–5) based on keyword frequency and amplifier/dampener words
- Outputs `master_risk_table.csv` with one row per keyword hit

### Phase 2b — LLM Validation (`validate_risk_table.py`)
- Sends each evidence sentence to Claude (Anthropic API) for context-aware validation
- Filters out false positives such as:
  - Named entity misfires (`war` → "Australian War Memorial")
  - Capability listings ("we offer cybersecurity products...")
  - Mitigated/resolved risks ("we have implemented controls...")
  - Incidental country mentions in competitive context
  - Definitional boilerplate (defining what ITAR is)
- Outputs `master_risk_table_validated.csv` and a rejected rows file for audit

### Phase 3 — Dashboard (`supply_chain_dashboard.py`)
Interactive Streamlit app with 5 views and a global filter sidebar.

---

## 📊 Dashboard Views

| Tab | Description |
|---|---|
| 🔥 Risk Heatmap | Company × Risk Category matrix, colored by avg severity |
| 🌐 Geopolitical Risk | Keyword frequency, subcategory breakdown, severity distribution |
| 🔗 Single-Source Analysis | Supplier concentration signals by company and subcategory |
| 📅 Disruption Timeline | Risk signal volume by filing date, groupable by category/company |
| 🔎 Evidence Explorer | Searchable, filterable table of all validated sentences with CSV export |

---

## 🚀 How to Run

### Prerequisites
```bash
pip install requests beautifulsoup4 lxml streamlit plotly pandas matplotlib
```

### Step 1 — Collect 10-K filings
```bash
python edgar_risk_factors.py
```
> Update the `User-Agent` in the script with your name and email before running (SEC requirement).

### Step 2 — Build the risk table
```bash
python build_risk_table.py
```

### Step 2b — Validate with LLM (optional but recommended)
```bash
# Set your Anthropic API key first
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # Windows PowerShell
export ANTHROPIC_API_KEY="sk-ant-..."   # Mac/Linux

python validate_risk_table.py
```

### Step 3 — Launch the dashboard
```bash
py -m streamlit run supply_chain_dashboard.py
```
Then open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 📁 Data Schema

`master_risk_table_validated.csv` — one row per validated risk signal:

| Column | Description |
|---|---|
| `company` | Company display name |
| `ticker` | Stock ticker |
| `filing_year` | Fiscal year of the 10-K |
| `filing_date` | Full filing date |
| `risk_category` | Top-level risk bucket |
| `risk_subcategory` | Specific risk type |
| `keyword_matched` | Keyword pattern that triggered the row |
| `evidence_sentence` | Sentence from the 10-K containing the keyword |
| `keyword_count` | Frequency of keyword in the full filing |
| `severity_score` | Auto-estimated 1–5 severity score |
| `severity_rationale` | Explanation of the score |
| `llm_validated` | Whether Claude confirmed this as a genuine risk |
| `llm_confidence` | Claude's confidence level (high/medium/low) |
| `rejection_reason` | Why a row was flagged as a false positive (if applicable) |
| `source_file` | Source `.txt` filename |
| `analyst_notes` | Blank column for manual annotation |

---

## 🔑 API & Data Sources

- **SEC EDGAR** — Free public API, no account required. [docs.sec.gov](https://www.sec.gov/developer)
- **Anthropic Claude API** — Used for LLM validation. Requires API key from [console.anthropic.com](https://console.anthropic.com). Cost for this dataset: ~$0.20.

---

## 📝 Notes

- SEC EDGAR requires a descriptive `User-Agent` header (your name + email). Update this in `edgar_risk_factors.py` before running.
- The dashboard expects `master_risk_table_validated.csv` to be in the same folder as `supply_chain_dashboard.py`. If not found, it will prompt you to upload the file.
- All filing data is sourced directly from public SEC EDGAR records and is in the public domain.

---

## 👤 Author

Sebastian Palacino  
Graduate Student, University of Texas  
Supply Chain Management Research Project — 2025
