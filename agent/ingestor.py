"""
ingestor.py
-----------
Handles file ingestion from:
  - Streamlit UploadedFile objects
  - Public URLs (GitHub raw, S3, Google Drive, Dropbox, etc.)

Supports: .xlsx, .xls, .csv  →  returns CSV string
          .pdf               →  returns extracted text string
"""

import requests
import pdfplumber
import pandas as pd
from io import BytesIO


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_url(url: str) -> bytes:
    """Download raw bytes from any public URL."""
    headers = {"User-Agent": "ReconciliationAgent/1.0"}
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.content


def _to_bytes(source) -> bytes:
    """
    Normalise source to bytes.
    Accepts: bytes | Streamlit UploadedFile | URL string
    """
    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        # Treat as URL
        return _fetch_url(source)
    # Streamlit UploadedFile (has .read())
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
        raise ValueError("PDF appears to be scanned/image-only. No text could be extracted.")
    return "\n\n".join(text_parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest(source, file_type: str) -> str:
    """
    Ingest a file and return its content as a string.

    Parameters
    ----------
    source : str | bytes | UploadedFile
        - str  → treated as a public URL
        - bytes → raw file bytes
        - UploadedFile → Streamlit upload widget object
    file_type : str
        One of: 'excel', 'csv', 'pdf'

    Returns
    -------
    str
        CSV text (for Excel/CSV) or plain text (for PDF)
    """
    raw = _to_bytes(source)

    file_type = file_type.lower().strip()
    if file_type in ("excel", "xlsx", "xls"):
        return _parse_excel(raw)
    elif file_type == "csv":
        return _parse_csv_bytes(raw)
    elif file_type == "pdf":
        return _parse_pdf(raw)
    else:
        raise ValueError(
            f"Unsupported file_type '{file_type}'. "
            "Choose from: 'excel', 'csv', 'pdf'."
        )


def detect_file_type(filename: str) -> str:
    """
    Infer file_type string from a filename or URL.

    Returns 'excel', 'csv', or 'pdf'.
    Raises ValueError for unsupported extensions.
    """
    # Strip query params from URLs
    clean = filename.split("?")[0].lower()
    ext = clean.rsplit(".", 1)[-1]

    mapping = {
        "xlsx": "excel",
        "xls": "excel",
        "csv": "csv",
        "pdf": "pdf",
    }
    if ext not in mapping:
        raise ValueError(
            f"Cannot detect file type from extension '.{ext}'. "
            "Supported: .xlsx, .xls, .csv, .pdf"
        )
    return mapping[ext]
