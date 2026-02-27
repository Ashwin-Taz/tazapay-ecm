"""
reconciler.py
-------------
Sends ingested file content to Claude and returns the raw CSV response.
"""

import os
import anthropic


def _load_system_prompt() -> str:
    prompt_path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", "system_prompt.txt"
    )
    with open(os.path.abspath(prompt_path), "r", encoding="utf-8") as f:
        return f.read()


def run_reconciliation(
    internal_errors_text: str,
    psp_documentation_text: str,
    model: str = "claude-opus-4-6",
    max_tokens: int = 8096,
) -> str:
    """
    Run the 4-phase reconciliation via Claude.

    Parameters
    ----------
    internal_errors_text : str
        CSV string of internal error codes (from Excel/CSV ingestion).
    psp_documentation_text : str
        Plain text extracted from the PSP PDF.
    model : str
        Claude model to use. Defaults to claude-opus-4-6 for best reasoning.
    max_tokens : int
        Maximum tokens for the response.

    Returns
    -------
    str
        Raw response from Claude (should be a CSV string).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Add it in your Render dashboard or .env file."
        )

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    user_message = f"""Here are the two inputs for reconciliation:

## INTERNAL ERROR CODES (from Excel/CSV):
{internal_errors_text}

---

## PSP ERROR DOCUMENTATION (from PDF):
{psp_documentation_text}

---

Please run all 4 phases (Forward Mapping, Reverse Mapping, Closest Partial Matching, Deduplicate and Consolidate) and produce the final consolidated CSV exactly as specified in your instructions.

Return ONLY the raw CSV. No markdown, no code fences, no commentary. Start with the header row."""

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text
