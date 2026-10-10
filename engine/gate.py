"""Confidence & compliance gate — the decision gate.

GREEN  : auto-filled, tick to accept
AMBER  : engineer review (converted units, fuzzy matches, derived-with-assumption)
RED    : clarify and block
"""
from __future__ import annotations

from typing import Dict, List

import config
from models import FieldValue, Issue


def gate_field(f: FieldValue, issues: List[Issue], thr: Dict[str, float]) -> str:
    if f.value is None:
        return "RED"
    if any(i.severity == "RED" and i.key == f.key for i in issues):
        return "RED"
    if (f.confidence >= thr.get("green", config.GATE_THRESHOLDS["green"])
            and f.method in ("extracted", "engineer_edit")
            and not f.needs_review):
        return "GREEN"
    return "AMBER"


def gate_fields(fields: Dict[str, FieldValue], issues: List[Issue],
                thr: Dict[str, float]) -> Dict[str, FieldValue]:
    for f in fields.values():
        f.status = gate_field(f, issues, thr)
    return fields


def lane_counts(fields: Dict[str, FieldValue], issues: List[Issue]) -> Dict[str, int]:
    counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for f in fields.values():
        counts[f.status] += 1
    for i in issues:
        if i.severity == "RED" and i.key not in fields:
            counts["RED"] += 1     # a missing required field has no FieldValue
    return counts


def open_reds(fields: Dict[str, FieldValue], issues: List[Issue]) -> List[Issue]:
    """RED issues that still block approval."""
    return [i for i in issues if i.severity == "RED"]
