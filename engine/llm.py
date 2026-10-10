"""Optional LLM helper — wording only.  NEVER calculates, picks or classifies.

OFF by default.  No key -> template fallback (full functionality offline).
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

import config


def llm_available() -> bool:
    return bool(config.LLM_ENABLED_DEFAULT and config.LLM_HAS_KEY)


def grounding_check(proposed: str, span: str) -> bool:
    """Rule 2: an LLM value is accepted only if its text appears in the source span."""
    if proposed is None:
        return False
    p = str(proposed).strip().lower()
    if not p:
        return False
    return p in str(span).lower()


def llm_extract(span: str) -> List[Dict]:
    """Strict-JSON extraction for messy text. Returns [] when unavailable."""
    if not llm_available():
        return []
    try:
        import anthropic
    except Exception:
        return []
    prompt = (
        "Extract process data sheet fields from the text below. Return ONLY JSON: "
        '[{"label": str, "value": str, "locator": "txt:lineN"}]. No commentary.\n\n' + span
    )
    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(model=config.LLM_MODEL, max_tokens=1200,
                                     messages=[{"role": "user", "content": prompt}])
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\[.*\]", txt, re.S)
        return json.loads(m.group(0)) if m else []
    except Exception:
        return []


TEMPLATES = {
    "conflict": ("Two different values were found for {key} on {file}: {a} and {b}. "
                 "Which one is correct?"),
    "missing": "{key} is not stated on {file}. Please provide the required value.",
    "unclear": "Vendor {vendor} offered '{offered}' for {key}; please confirm the exact value.",
    "deviation": "Offered {offered} does not meet the requirement {required} for {key} "
                 "(deviation, critical={critical}).",
    "low_match": "Label '{label}' was matched to {key} with {score}% confidence. "
                 "Is this mapping correct?",
}


def wording(kind: str, **kw) -> str:
    """Template wording, optionally rewritten by the LLM (never invented facts)."""
    base = TEMPLATES.get(kind, "").format(**kw)
    if not llm_available():
        return base
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=config.LLM_MODEL, max_tokens=300,
            messages=[{"role": "user", "content":
                       "Rewrite this engineering clarification question concisely and "
                       "professionally, keeping every number and unit exactly as written. "
                       f"Return only the question.\n\n{base}"}])
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        # grounding: keep only if every number from the original survived
        nums = set(re.findall(r"\d+\.?\d*", base))
        if txt and all(n in txt for n in nums):
            return txt
        return base
    except Exception:
        return base
