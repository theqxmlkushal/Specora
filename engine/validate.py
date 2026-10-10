"""Missing / conflict / rule checks.  No silent defaults, ever."""
from __future__ import annotations

from typing import Dict, List, Optional

import config
from engine.extract import Candidate, Extraction
from models import FieldValue, Issue

QUESTION = {
    "MISSING": "is not stated on the Process Data Sheet. Please confirm the required value "
               "with the process engineer before the MDS can be approved.",
    "CONFLICT": "is stated differently in two places on the same sheet. Please confirm which "
                "value is correct with the process engineer.",
    "UNIT_AMBIGUOUS": "is given without an unambiguous unit. Please confirm the unit and "
                      "gauge/absolute convention with the process engineer.",
    "RULE_VIOLATION": "fails a design rule check. Please confirm with the process engineer.",
}


def _close(a: float, b: float, tol: float = 0.01) -> bool:
    if a == b:
        return True
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom <= tol


def validate(ext: Extraction, rules: dict) -> List[Issue]:
    issues: List[Issue] = ext.issues          # normalize-stage issues, in place
    required = rules.get("required_fields", config.REQUIRED_FIELDS)
    cands: Dict[str, List[Candidate]] = ext.candidates

    # 1) missing required fields (never defaulted)
    for key in required:
        if key not in cands:
            issues.append(Issue(
                code="MISSING", key=key, severity="RED",
                message=f"'{key}' is missing from {ext.doc.source_file}.",
                question=f"'{_label(key)}' {QUESTION['MISSING']}"))

    # 2) conflicts across sources of the same key
    for key, cs in cands.items():
        if len(cs) < 2:
            continue
        vals = [c.value for c in cs if c.value is not None]
        if not vals:
            continue
        conflict = False
        if all(isinstance(v, (int, float)) for v in vals):
            conflict = any(not _close(float(vals[0]), float(v)) for v in vals[1:])
        else:
            conflict = any(str(v).strip().lower() != str(vals[0]).strip().lower() for v in vals[1:])
        if conflict:
            detail = "; ".join(f"{_fmt(c.value)} {c.unit or ''} @ {c.locator}" for c in cs)
            issues.append(Issue(
                code="CONFLICT", key=key, severity="RED",
                message=f"Conflicting values for '{_label(key)}': {detail}",
                question=f"'{_label(key)}' {QUESTION['CONFLICT']} "
                         f"(sources: {', '.join(c.locator for c in cs)}).",
                locators=[c.locator for c in cs]))

    conflicted = {i.key for i in issues if i.code == "CONFLICT"}
    f = ext.fields

    # 3) rule checks (design must exceed operating; sane ranges)
    op, dp = f.get("operating_pressure"), f.get("design_pressure")
    if op and dp and op.value is not None and dp.value is not None \
            and "design_pressure" not in conflicted and "operating_pressure" not in conflicted:
        if float(dp.value) < float(op.value):
            issues.append(Issue(
                code="RULE_VIOLATION", key="design_pressure", severity="RED",
                message=(f"Stated design pressure {_fmt(dp.value)} MPa(g) is below operating "
                         f"pressure {_fmt(op.value)} MPa(g) ({dp.prov.locator})."),
                question="Design pressure is lower than operating pressure — please confirm the "
                         "correct design pressure with the process engineer.",
                locators=[dp.prov.locator]))
    ot, dt = f.get("operating_temperature"), f.get("design_temperature")
    if ot and dt and ot.value is not None and dt.value is not None \
            and "design_temperature" not in conflicted:
        if float(dt.value) < float(ot.value):
            issues.append(Issue(
                code="RULE_VIOLATION", key="design_temperature", severity="RED",
                message=(f"Stated design temperature {_fmt(dt.value)} degC is below operating "
                         f"temperature {_fmt(ot.value)} degC ({dt.prov.locator})."),
                question="Design temperature is lower than operating temperature — please confirm "
                         "with the process engineer.",
                locators=[dt.prov.locator]))

    ranges = {"operating_pressure": (0.0, 100.0, "MPa(g)"),
              "design_pressure": (0.0, 100.0, "MPa(g)"),
              "operating_temperature": (-150.0, 600.0, "degC"),
              "inside_diameter": (1.0, 20000.0, "mm"),
              "tan_to_tan_length": (1.0, 80000.0, "mm")}
    for key, (lo, hi, unit) in ranges.items():
        fld = f.get(key)
        if not fld or not isinstance(fld.value, (int, float)):
            continue
        if not (lo <= float(fld.value) <= hi):
            issues.append(Issue(
                code="RULE_VIOLATION", key=key, severity="RED",
                message=f"{_label(key)} = {_fmt(fld.value)} {unit} is outside the sanity range "
                        f"[{lo}, {hi}] {unit} ({fld.prov.locator}).",
                question=f"Please sanity-check '{_label(key)}' with the process engineer.",
                locators=[fld.prov.locator]))
    return issues


def _label(key: str) -> str:
    return key.replace("_", " ")


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)
