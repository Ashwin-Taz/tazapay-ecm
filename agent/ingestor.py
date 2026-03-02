"""
ingestor.py — Error Code Mapping Agent
Supports: Google Sheets / Webpage URLs / Excel / CSV / PDF
"""

import re
import requests
import pdfplumber
import pandas as pd
from io import BytesIO


def is_google_sheets_url(url: str) -> bool:
    return "docs.google.com/spreadsheets" in url


def fetch_google_sheet(url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError("Could not extract spreadsheet ID. Paste the full sharing link.")
    sheet_id = match.group(1)
    gid_match = re.search(r"gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else "0"
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    r = requests.get(export_url, headers={"User-Agent": "ErrorCodeMappingAgent/1.0"}, timeout=60)
    if r.status_code in (401, 403):
        raise PermissionError("Google Sheets access denied. Set sharing to 'Anyone with the link can view'.")
    r.raise_for_status()
    return pd.read_csv(BytesIO(r.content)).to_csv(index=False)


def is_web_page_url(url: str) -> bool:
    if not url.startswith("http") or is_google_sheets_url(url):
        return False
    last_seg = url.split("?")[0].lower().split("/")[-1]
    ext = last_seg.rsplit(".", 1)[-1] if "." in last_seg else ""
    return ext not in {"xlsx", "xls", "csv", "pdf", "json", "txt", "xml"}


def fetch_webpage_as_text(url: str) -> str:
    from html.parser import HTMLParser
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ErrorCodeMappingAgent/1.0)"}, timeout=60)
    r.raise_for_status()
    if "application/pdf" in r.headers.get("content-type", ""):
        return _parse_pdf(r.content)

    class _Extractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts, self._skip = [], False
        def handle_starttag(self, tag, attrs):
            if tag in ("script","style","nav","footer","head"): self._skip = True
        def handle_endtag(self, tag):
            if tag in ("script","style","nav","footer","head"): self._skip = False
            if tag in ("p","li","tr","h1","h2","h3","h4","div","td","th","br"): self.parts.append("\n")
        def handle_data(self, data):
            if not self._skip and data.strip(): self.parts.append(data.strip())

    p = _Extractor()
    p.feed(r.text)
    text = " ".join(p.parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    if len(text.strip()) < 100:
        raise ValueError(
            "Page appears empty after parsing — it may require login or be JS-rendered. "
            "Try downloading as PDF and uploading instead."
        )
    return f"[Source: {url}]\n\n{text.strip()}"


def _to_bytes(source) -> bytes:
    if isinstance(source, bytes): return source
    if isinstance(source, str):
        r = requests.get(source, headers={"User-Agent": "ErrorCodeMappingAgent/1.0"}, timeout=60)
        r.raise_for_status()
        return r.content
    if hasattr(source, "read"): return source.read()
    raise TypeError(f"Unsupported source type: {type(source)}")

def _parse_excel(raw): return pd.read_excel(BytesIO(raw)).to_csv(index=False)
def _parse_csv(raw):   return pd.read_csv(BytesIO(raw)).to_csv(index=False)
def _parse_pdf(raw):
    parts = []
    with pdfplumber.open(BytesIO(raw)) as pdf:
        for i, page in enumerate(pdf.pages):
            t = page.extract_text()
            if t: parts.append(f"--- Page {i+1} ---\n{t}")
    if not parts:
        raise ValueError("PDF appears scanned/image-only — no text could be extracted.")
    return "\n\n".join(parts)


def ingest(source, file_type: str) -> str:
    ft = file_type.lower().strip()
    if ft == "google_sheets": return fetch_google_sheet(source)
    if ft == "webpage":       return fetch_webpage_as_text(source)
    raw = _to_bytes(source)
    if ft in ("excel","xlsx","xls"): return _parse_excel(raw)
    if ft == "csv":                  return _parse_csv(raw)
    if ft == "pdf":                  return _parse_pdf(raw)
    raise ValueError(f"Unsupported file_type '{ft}'.")


def detect_file_type(filename: str) -> str:
    if is_google_sheets_url(filename): return "google_sheets"
    if filename.startswith("http") and is_web_page_url(filename): return "webpage"
    last_seg = filename.split("?")[0].lower().split("/")[-1]
    ext = last_seg.rsplit(".", 1)[-1] if "." in last_seg else ""
    mapping = {"xlsx":"excel","xls":"excel","csv":"csv","pdf":"pdf"}
    if ext not in mapping:
        raise ValueError(
            f"Cannot detect file type from '.{ext}'. "
            "Supported: Google Sheets URL / webpage URL / .xlsx / .xls / .csv / .pdf"
        )
    return mapping[ext]
