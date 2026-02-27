# 🔁 Error Code Mapping Agent

An AI agent that performs **bidirectional error code mapping** between your internal payment platform and PSP (Payment Service Provider) documentation.

Built with **Claude** (Anthropic) + **Streamlit**, deployable to **Render** in minutes.

---

## What It Does

1. **Ingests** your internal error codes via Google Sheets, Excel/CSV upload, or public URL — and PSP documentation via PDF upload or URL
2. **Runs a 4-phase reasoning process** using Claude:
   - Phase 1: Forward mapping (Internal → PSP)
   - Phase 2: Reverse mapping (PSP → Internal)
   - Phase 3: Closest partial matching for gaps
   - Phase 4: Deduplication and consolidation
3. **Outputs** a validated, downloadable CSV with confidence scores, mapping types, evidence excerpts, and recommended merchant actions

---

## Project Structure

```
error-code-mapping-agent/
├── app.py                  # Streamlit UI
├── agent/
│   ├── __init__.py
│   ├── ingestor.py         # File + URL + Google Sheets ingestion
│   ├── reconciler.py       # Claude API call
│   └── validator.py        # CSV post-processing + quality checklist
├── prompts/
│   └── system_prompt.txt   # Full mapping system prompt
├── requirements.txt
├── render.yaml             # One-click Render deployment config
├── .env.example
└── .gitignore
```

---

## Quick Start (Local)

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
streamlit run app.py
```

---

## Deploy to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. In **Environment** tab → add `ANTHROPIC_API_KEY`
5. Build command: `pip install -r requirements.txt`
6. Start command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
7. Click **Deploy**

---

## Supported Input Sources — Internal Error Codes

| Source | How to use |
|--------|-----------|
| **Google Sheets** | Share sheet as "Anyone with link can view" → paste link |
| File upload | `.xlsx`, `.xls`, `.csv` |
| GitHub raw URL | `https://raw.githubusercontent.com/...` |
| Any public URL | Direct link to `.xlsx`, `.csv` |

## PSP Documentation

| Source | How to use |
|--------|-----------|
| File upload | `.pdf` |
| Any public URL | Direct link to `.pdf` |

---

## Using Google Sheets

1. Open your Google Sheet
2. Click **File → Share → Share with others**
3. Change access to **"Anyone with the link"** → **Viewer**
4. Click **Copy link**
5. Paste the link into the app

No API key or OAuth required — the agent uses Google's public CSV export endpoint.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ Yes | From [console.anthropic.com](https://console.anthropic.com) |

---

## Tech Stack

- [Claude](https://anthropic.com) — AI reasoning engine
- [Streamlit](https://streamlit.io) — Web UI
- [pdfplumber](https://github.com/jsvine/pdfplumber) — PDF text extraction
- [pandas](https://pandas.pydata.org) + [openpyxl](https://openpyxl.readthedocs.io) — Excel/CSV parsing
- [Render](https://render.com) — Cloud hosting
