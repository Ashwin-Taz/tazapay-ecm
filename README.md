# 💳 Payments Reconciliation Agent

An AI agent that performs **bidirectional error code mapping** between your internal payment platform and PSP (Payment Service Provider) documentation.

Built with **Claude** (Anthropic) + **Streamlit**, deployable to **Render** in minutes.

---

## What It Does

1. **Ingests** your internal error codes (Excel/CSV) and PSP documentation (PDF) — via file upload or public URL
2. **Runs a 4-phase reasoning process** using Claude:
   - Phase 1: Forward mapping (Internal → PSP)
   - Phase 2: Reverse mapping (PSP → Internal)
   - Phase 3: Closest partial matching for gaps
   - Phase 4: Deduplication and consolidation
3. **Outputs** a validated, downloadable CSV with confidence scores, mapping types, evidence excerpts, and recommended merchant actions

---

## Project Structure

```
reconciliation-agent/
├── app.py                  # Streamlit UI
├── agent/
│   ├── __init__.py
│   ├── ingestor.py         # File + URL ingestion (Excel, CSV, PDF)
│   ├── reconciler.py       # Claude API call
│   └── validator.py        # CSV post-processing + quality checklist
├── prompts/
│   └── system_prompt.txt   # Full reconciliation system prompt
├── requirements.txt
├── render.yaml             # One-click Render deployment config
├── .env.example            # Environment variable template
└── .gitignore
```

---

## Quick Start (Local)

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/reconciliation-agent.git
cd reconciliation-agent
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
# Edit .env and add your Anthropic API key
```

### 3. Run

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501)

---

## Deploy to Render

### Option A — Auto-deploy via render.yaml (recommended)

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New** → **Web Service**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` — build + start commands are pre-filled
5. In **Environment** tab → add `ANTHROPIC_API_KEY` = your key
6. Click **Deploy**

Your app will be live at `https://reconciliation-agent.onrender.com` in ~3 minutes.

### Option B — Manual setup on Render

| Setting | Value |
|---------|-------|
| Runtime | Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true` |
| Environment variable | `ANTHROPIC_API_KEY` = your key |

---

## Supported Input Sources

| Source | Format | Works? |
|--------|--------|--------|
| File upload | `.xlsx`, `.xls`, `.csv`, `.pdf` | ✅ |
| GitHub raw URL | `https://raw.githubusercontent.com/...` | ✅ |
| S3 / Azure Blob (public) | Direct object URL | ✅ |
| Google Drive (public) | Link with `export=download` | ✅ |
| Dropbox | Link ending in `?dl=1` | ✅ |
| Any direct file URL | `.xlsx`, `.csv`, `.pdf` | ✅ |

---

## Output CSV Columns

| Column | Description |
|--------|-------------|
| `direction` | Forward / Reverse / PSP-only |
| `internal_error_code` | Your platform error code |
| `internal_error_message` | Your platform error description |
| `failure_domain` | issuer / bank / network / validation / timeout / fraud / compliance / system / configuration |
| `expected_action` | retry / fix input / contact bank / block transaction / investigate / no action |
| `psp_error_code` | PSP error code |
| `psp_error_message` | PSP error description |
| `mapping_type` | Exact / Probable / One-to-many / Closest partial |
| `confidence` | 0–100 |
| `unknown_subtype` | No PSP equivalent / No internal equivalent / Needs investigation |
| `reasoning_summary` | 2-sentence mapping rationale |
| `evidence_psp` | Direct excerpt from PSP documentation |
| `recommended_merchant_action` | Actionable guidance |

---

## Confidence Levels

| Range | Meaning |
|-------|---------|
| 95–100 | Explicit identical meaning |
| 85–94 | Strong semantic alignment |
| 70–84 | Minor ambiguity; safe for automated routing |
| 50–69 | Closest partial; requires human review |
| 0 | Unmapped |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ Yes | Your Anthropic API key from [console.anthropic.com](https://console.anthropic.com) |

---

## Tech Stack

- [Claude](https://anthropic.com) — AI reasoning engine
- [Streamlit](https://streamlit.io) — Web UI
- [pdfplumber](https://github.com/jsvine/pdfplumber) — PDF text extraction
- [pandas](https://pandas.pydata.org) + [openpyxl](https://openpyxl.readthedocs.io) — Excel/CSV parsing
- [Render](https://render.com) — Cloud hosting

---

## Notes

- Use `claude-opus-4-6` (default) for best mapping quality; switch to `claude-sonnet-4-6` in settings for faster/cheaper runs
- For very large PSP PDFs (100+ pages), consider splitting the PDF before uploading
- The validation layer runs automatically and flags any quality issues before you download
