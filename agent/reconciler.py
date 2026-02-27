"""
reconciler.py
-------------
Sends ingested content to Claude and returns the raw CSV response.
Includes a second investigation pass for 'Needs investigation' rows.
"""

import os
import io
import csv
import pandas as pd
from io import StringIO
import anthropic


def _load_system_prompt() -> str:
    prompt_path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", "system_prompt.txt"
    )
    with open(os.path.abspath(prompt_path), "r", encoding="utf-8") as f:
        return f.read()


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Add it in your Render dashboard or .env file."
        )
    return anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# Phase 1 — Main mapping run
# ---------------------------------------------------------------------------

def run_reconciliation(
    internal_errors_text: str,
    psp_documentation_text: str,
    domain_context: str = "",
    model: str = "claude-opus-4-6",
    max_tokens: int = 8096,
) -> str:
    """
    Run the 4-phase error code mapping via Claude.

    Parameters
    ----------
    internal_errors_text   : CSV string of internal error codes
    psp_documentation_text : Plain text extracted from PSP source
    domain_context         : Optional freetext domain hints from the user
    model                  : Claude model string
    max_tokens             : Maximum response tokens

    Returns
    -------
    str — Raw Claude response (CSV string)
    """
    client = _get_client()
    system_prompt = _load_system_prompt()

    domain_block = ""
    if domain_context.strip():
        domain_block = f"""
## DOMAIN CONTEXT PROVIDED BY OPERATOR
{domain_context.strip()}

Use this context to improve mapping accuracy, especially for ambiguous codes.
---
"""

    user_message = f"""Here are the two inputs for error code mapping:
{domain_block}
## INTERNAL ERROR CODES:
{internal_errors_text}

---

## PSP ERROR DOCUMENTATION:
{psp_documentation_text}

---

Please run all 4 phases (Forward Mapping, Reverse Mapping, Closest Partial Matching, \
Deduplicate and Consolidate) and produce the final consolidated CSV exactly as specified.

IMPORTANT: PSP-only rows (direction=PSP-only) are expected and required. \
Do NOT leave PSP infrastructure codes unmapped — assign them as PSP-only \
with internal_error_code left blank. A result with 0 PSP-only rows is likely incomplete.

Return ONLY the raw CSV. No markdown, no code fences, no commentary. Start with the header row."""

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text


# ---------------------------------------------------------------------------
# Phase 2 — Investigation pass for 'Needs investigation' rows
# ---------------------------------------------------------------------------

def run_investigation_pass(
    needs_investigation_csv: str,
    psp_documentation_text: str,
    domain_context: str = "",
    model: str = "claude-opus-4-6",
    max_tokens: int = 4096,
) -> str:
    """
    Second focused pass on rows marked 'Needs investigation'.
    Instructs Claude to try harder with lowered confidence threshold.

    Returns
    -------
    str — Raw Claude response with updated rows (CSV string)
    """
    client = _get_client()

    domain_block = ""
    if domain_context.strip():
        domain_block = f"\n## DOMAIN CONTEXT:\n{domain_context.strip()}\n"

    user_message = f"""You are a senior payments error code mapping expert.

The following internal error codes were previously marked as 'Needs investigation' \
because no confident PSP match was found. Please try harder this time.

INSTRUCTIONS:
- Re-examine each code carefully against the PSP documentation
- Consider partial domain overlap, similar merchant actions, or generic PSP catch-all codes
- Accept confidence as low as 50 for 'Closest partial' matches
- If still no match, keep unknown_subtype = 'Needs investigation' but add more detail to reasoning_summary
- Do NOT invent PSP codes
- Return ALL rows (matched and still-unmatched), updated
- Return ONLY raw CSV with the same 13 columns as the input. No markdown, no commentary.
{domain_block}
## UNMATCHED ROWS TO REINVESTIGATE:
{needs_investigation_csv}

---

## PSP ERROR DOCUMENTATION:
{psp_documentation_text}

---

Return ONLY the updated CSV rows (including the header row). Start immediately with the header."""

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text


# ---------------------------------------------------------------------------
# Merge helper — splice second-pass results back into main CSV
# ---------------------------------------------------------------------------

def merge_investigation_results(
    original_csv: str,
    investigation_csv: str,
) -> str:
    """
    Replace 'Needs investigation' rows in the original CSV with
    the updated rows from the investigation pass.

    Returns merged CSV string.
    """
    def _parse(text: str) -> pd.DataFrame:
        text = text.strip()
        for header in ["direction,internal_error_code", "direction,"]:
            idx = text.find(header)
            if idx != -1:
                text = text[idx:]
                break
        return pd.read_csv(
            StringIO(text),
            quoting=csv.QUOTE_MINIMAL,
            on_bad_lines="skip",
            dtype=str,
        )

    try:
        orig_df = _parse(original_csv)
        inv_df  = _parse(investigation_csv)
    except Exception as e:
        # If merge fails, return original untouched
        return original_csv

    # Normalise columns
    orig_df.columns = [c.strip() for c in orig_df.columns]
    inv_df.columns  = [c.strip() for c in inv_df.columns]

    # Remove original 'Needs investigation' rows
    mask_ni = (
        orig_df.get("unknown_subtype", pd.Series(dtype=str))
        .astype(str).str.strip() == "Needs investigation"
    )
    cleaned_df = orig_df[~mask_ni].copy()

    # Append updated investigation rows
    merged_df = pd.concat([cleaned_df, inv_df], ignore_index=True)

    # Re-sort: Forward first, then Reverse, then PSP-only
    direction_order = {"Forward": 0, "Reverse": 1, "PSP-only": 2}
    merged_df["_sort"] = merged_df.get("direction", pd.Series(dtype=str)).map(
        lambda x: direction_order.get(str(x).strip(), 3)
    )
    merged_df = merged_df.sort_values("_sort").drop(columns=["_sort"])

    # Return as CSV string
    return merged_df.to_csv(index=False)
