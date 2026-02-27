"""
validator.py
------------
Post-processes Claude's response and runs the quality checklist
programmatically before the user sees the result.
"""

import re
import pandas as pd
from io import StringIO


REQUIRED_COLUMNS = [
    "direction",
    "internal_error_code",
    "internal_error_message",
    "failure_domain",
    "expected_action",
    "psp_error_code",
    "psp_error_message",
    "mapping_type",
    "confidence",
    "unknown_subtype",
    "reasoning_summary",
    "evidence_psp",
    "recommended_merchant_action",
]

VALID_DIRECTIONS = {"Forward", "Reverse", "PSP-only"}
VALID_MAPPING_TYPES = {"Exact", "Probable", "One-to-many", "Closest partial"}
VALID_FAILURE_DOMAINS = {
    "issuer", "bank", "network", "validation",
    "timeout", "fraud", "compliance", "system", "configuration",
}
VALID_UNKNOWN_SUBTYPES = {
    "No PSP equivalent", "No internal equivalent", "Needs investigation",
}


# ---------------------------------------------------------------------------
# CSV extraction
# ---------------------------------------------------------------------------

def extract_csv_from_response(response: str) -> str:
    """
    Strip any markdown code fences Claude may have added despite instructions.
    Returns clean CSV string.
    """
    # Try ```csv ... ``` block
    match = re.search(r"```(?:csv)?\s*\n(.*?)```", response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Try to find the header row as the starting point
    header = "direction,"
    idx = response.find(header)
    if idx != -1:
        return response[idx:].strip()

    # Fall back to returning the whole response stripped
    return response.strip()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_csv(csv_string: str) -> dict:
    """
    Run quality checklist against the parsed CSV.

    Returns
    -------
    dict with keys:
        valid       : bool
        issues      : list[str]   — list of validation problems found
        warnings    : list[str]   — non-blocking observations
        df          : pd.DataFrame | None
        stats       : dict        — summary counts
    """
    issues = []
    warnings = []
    df = None
    stats = {}

    # --- Parse ---
    try:
        df = pd.read_csv(StringIO(csv_string))
        # Normalise column names (strip whitespace)
        df.columns = [c.strip() for c in df.columns]
    except Exception as e:
        return {
            "valid": False,
            "issues": [f"CSV failed to parse: {e}"],
            "warnings": [],
            "df": None,
            "stats": {},
        }

    # --- Column presence ---
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        issues.append(f"Missing required columns: {missing_cols}")

    # Abort deeper checks if columns are missing
    if issues:
        return {"valid": False, "issues": issues, "warnings": warnings, "df": df, "stats": stats}

    # --- Coerce types ---
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce").fillna(0).astype(int)

    # --- Direction values ---
    invalid_dir = df[~df["direction"].isin(VALID_DIRECTIONS)]
    if len(invalid_dir):
        issues.append(
            f"{len(invalid_dir)} rows have invalid 'direction' values: "
            f"{invalid_dir['direction'].unique().tolist()}"
        )

    # --- Duplicate pairs ---
    dup_mask = df.duplicated(subset=["internal_error_code", "psp_error_code"], keep=False)
    dupes = df[dup_mask]
    if len(dupes):
        issues.append(
            f"{len(dupes)} duplicate (internal_error_code + psp_error_code) pairs found."
        )

    # --- Exact mappings must have confidence >= 90 ---
    exact_rows = df[df["mapping_type"] == "Exact"]
    low_exact = exact_rows[exact_rows["confidence"] < 90]
    if len(low_exact):
        issues.append(
            f"{len(low_exact)} 'Exact' mapping rows have confidence < 90: "
            f"{low_exact['internal_error_code'].tolist()}"
        )

    # --- Closest partial must be 50–69 ---
    partial_rows = df[df["mapping_type"] == "Closest partial"]
    bad_partial = partial_rows[
        (partial_rows["confidence"] < 50) | (partial_rows["confidence"] > 69)
    ]
    if len(bad_partial):
        warnings.append(
            f"{len(bad_partial)} 'Closest partial' rows have confidence outside 50–69."
        )

    # --- Unmapped rows must have unknown_subtype ---
    unmapped = df[df["mapping_type"].isna() | (df["mapping_type"] == "")]
    missing_subtype = unmapped[
        unmapped["unknown_subtype"].isna() | (unmapped["unknown_subtype"] == "")
    ]
    if len(missing_subtype):
        issues.append(
            f"{len(missing_subtype)} unmapped rows are missing 'unknown_subtype'."
        )

    # --- recommended_merchant_action always populated ---
    empty_action = df[
        df["recommended_merchant_action"].isna() |
        (df["recommended_merchant_action"].astype(str).str.strip() == "")
    ]
    if len(empty_action):
        issues.append(
            f"{len(empty_action)} rows are missing 'recommended_merchant_action'."
        )

    # --- Stats ---
    stats = {
        "total_rows": len(df),
        "forward": int((df["direction"] == "Forward").sum()),
        "reverse": int((df["direction"] == "Reverse").sum()),
        "psp_only": int((df["direction"] == "PSP-only").sum()),
        "exact": int((df["mapping_type"] == "Exact").sum()),
        "probable": int((df["mapping_type"] == "Probable").sum()),
        "one_to_many": int((df["mapping_type"] == "One-to-many").sum()),
        "closest_partial": int((df["mapping_type"] == "Closest partial").sum()),
        "unmapped": int(unmapped.shape[0]),
        "avg_confidence": round(
            df[df["confidence"] > 0]["confidence"].mean(), 1
        ) if (df["confidence"] > 0).any() else 0,
    }

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "df": df,
        "stats": stats,
    }
