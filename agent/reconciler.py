"""
reconciler.py
-------------
Sends ingested content to Claude and returns the raw CSV response.
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
    Run the 4-phase error code mapping via Claude.

    Parameters
    ----------
    internal_errors_text   : CSV string of internal error codes
    psp_documentation_text : Plain text extracted from PSP source
    model                  : Claude model string
    max_tokens             : Maximum response tokens

    Returns
    -------
    str — Raw Claude response (CSV string)
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Add it in your Render dashboard or .env file."
        )

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    user_message = f"""Here are the two inputs for error code mapping:

## INTERNAL ERROR CODES:
{internal_errors_text}

---

## PSP ERROR DOCUMENTATION:
{psp_documentation_text}

---

Please run all 4 phases (Forward Mapping, Reverse Mapping, Closest Partial Matching, \
Deduplicate and Consolidate) and produce the final consolidated CSV exactly as specified.

Return ONLY the raw CSV. No markdown, no code fences, no commentary. Start with the header row."""

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text
