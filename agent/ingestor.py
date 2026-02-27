"""
ingestor.py
-----------
Handles file ingestion from:
  - Streamlit UploadedFile objects (.xlsx, .xls, .csv, .pdf)
  - Public URLs (GitHub raw, S3, Dropbox, etc.)
  - Google Sheets share links (no API key required)

Internal error codes: Google Sheets / Excel / CSV / URL
PSP documentation:    Google Sheets / Excel / CSV / PDF / URL
"""

import re
import requests
import pdfplumber
import pandas as pd
from io import BytesIO


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

def is_google_sheets_url(url: str) -> bool:
    return "docs.google.com/spreadsheets" in url


def _extract_sheet_id(url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(
            "Could not extract spreadsheet ID from the Google Sheets URL. "
            "Make sure you paste the full sharing link."
        )
    return match.group(1)


def _extract_gid(url: str) -> str:
    match = re.search(r"gid=(\d+)", url)
    return match.group(1) if match else "0"


def fetch_google_sheet(url: str) -> str:
    """
    Fetch a Google Sheet as CSV text.
    Sheet must be shared as 'Anyone with the link can view'.
    No API key or OAuth needed.
    """
    sheet_id = _extract_sheet_id(url)
    gid = _extract_gid(url)
    export_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )
    headers = {"User-Agent": "ErrorCodeMappingAgent/1.0"}
    response = requests.get(export_url, headers=headers, timeout=60)

    if response.status_code in (401, 403):
        raise PermissionError(
            "Google Sheets access denied. "
            "Set sharing to 'Anyone with the link can view' and try again."
        )
    if response.status_code != 200:
        raise ConnectionError(
            f"Failed to fetch Google Sheet (HTTP {response.status_code}). "
            "Check that the link is correct and the sheet is publicly shared."
        )
    df = pd.read_csv(BytesIO(response.content))
    return df.to_csv(index=False)


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def _fetch_url(url: str) -> bytes:
    headers = {"User-Agent": "ErrorCodeMappingAgent/1.0"}
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.content


def _to_bytes(source) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        return _fetch_url(source)
    if hasattr(source, "read"):
        return source.read()
    raise TypeError(f"Unsupported source type: {type(source)}")


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_excel(raw: bytes) -> str:
    df = pd.read_excel(BytesIO(raw))
    return df.to_csv(index=False)


def _parse_csv_bytes(raw: bytes) -> str:
    df = pd.read_csv(BytesIO(raw))
    return df.to_csv(index=False)


def _parse_pdf(raw: bytes) -> str:
    text_parts = []
    with pdfplumber.open(BytesIO(raw)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"--- Page {i + 1} ---\n{page_text}")
    if not text_parts:
        raise ValueError(
            "PDF appears to be scanned/image-only. No text could be extracted."
        )
    return "\n\n".join(text_parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest(source, file_type: str) -> str:
    """
    Ingest a file and return its content as a string.

    Parameters
    ----------
    source      : Google Sheets URL str | public URL str | bytes | UploadedFile
    file_type   : 'google_sheets' | 'excel' | 'csv' | 'pdf'

    Returns
    -------
    str  — CSV text for spreadsheet types; plain text for PDF
    """
    file_type = file_type.lower().strip()

    if file_type == "google_sheets":
        if not isinstance(source, str):
            raise ValueError("Google Sheets source must be a URL string.")
        return fetch_google_sheet(source)

    raw = _to_bytes(source)

    if file_type in ("excel", "xlsx", "xls"):
        return _parse_excel(raw)
    elif file_type == "csv":
        return _parse_csv_bytes(raw)
    elif file_type == "pdf":
        return _parse_pdf(raw)
    else:
        raise ValueError(
            f"Unsupported file_type '{file_type}'. "
            "Choose from: 'google_sheets', 'excel', 'csv', 'pdf'."
        )


def detect_file_type(filename: str) -> str:
    """
    Infer file_type from a filename or URL.
    Automatically detects Google Sheets URLs.
    Returns: 'google_sheets' | 'excel' | 'csv' | 'pdf'
    """
    if is_google_sheets_url(filename):
        return "google_sheets"

    clean = filename.split("?")[0].lower()
    ext = clean.rsplit(".", 1)[-1]
    mapping = {
        "xlsx": "excel",
        "xls":  "excel",
        "csv":  "csv",
        "pdf":  "pdf",
    }
    if ext not in mapping:
        raise ValueError(
            f"Cannot detect file type from extension '.{ext}'. "
            "Supported: Google Sheets URL / .xlsx / .xls / .csv / .pdf"
        )
    return mapping[ext]
