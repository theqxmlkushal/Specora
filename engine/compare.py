"""Deterministic requirement comparator: vendor offer vs approved MDS.

Missing / Unclear / Deviating / Compliant — the LLM is never involved.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from engine.extract import Candidate
from engine.normalize import normalize_value
from models import MdsRow, ReqResult

VAGUE = {
    "tbc", "t.b.c", "to be confirmed", "as per standard", "per standard", "per code",
    "as required", "as required by code", "as specified", "as agreed", "by others",
    "n/a", "na", "-", "see standard", "per relevant standard", "as code",
}


def is_vague(text: str) -> bool:
    t = str(text or "").strip().lower()
    if not t:
        return False
    if t in VAGUE:
        return True
    return any(tok in t for tok in ("as per standard", "per code", "to be confirmed",
                                    "as required by code", "as per relevant"))


def _num(x) -> Optional[float]:
    if isinstance(x, (int, float)):
        return float(x)
    return None


def _disp(v, unit="") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        txt = f"{v:.4g}"
    else:
        txt = str(v)
    return f"{txt} {unit}".strip()


def required_value(req: dict, mds: Dict[str, MdsRow]) -> Tuple[object, str, str]:
    """-> (value, unit, display)"""
    if "value" in req and req.get("value") is not None and req["source"] in ("ENQUIRY", "MATERIAL_SPEC"):
        return req["value"], "", str(req["value"])
    row = mds.get(req["key"])
    if row is None:
        return None, "", "—"
    val = row.value
    if isinstance(val, bool):
        val = "Yes" if val else "No"
    return val, row.unit or "", _disp(val, row.unit or "")


def offered_value(key: str, cand: Optional[Candidate], answer: Optional[str]):
    """-> (value, unit, text)"""
    if answer:
        from engine.ingest import parse_value_unit, parse_value_unit_full
        a = str(answer)
        num, unit = parse_value_unit(a)
        if num is None:                       # free-text reply: find "12 bar(g)" anywhere
            m = re.search(r"[-+]?\d+(?:[.,]\d+)?\s*[A-Za-z°/%µ³²().]*", a)
            if m:
                num, unit = parse_value_unit(m.group(0))
            else:
                num, unit = None, ""
        val, u, _, _ = normalize_value(key, num if num is not None else a, unit, "reply")
        return val, u or "", a
    if cand is None:
        return None, "", ""
    val, unit, _, _ = normalize_value(key, cand.raw_value, cand.raw_unit, cand.locator)
    text = str(cand.raw_value) if not isinstance(cand.raw_value, (int, float)) else ""
    if isinstance(cand.raw_value, (int, float)):
        text = ""
    raw_txt = str(cand.raw_value if not isinstance(cand.raw_value, str) else cand.raw_value)
    return val, unit or "", (text or raw_txt)


def compare_one(req: dict, req_val, req_unit, req_disp: str, vendor: str,
                cand: Optional[Candidate], answer: Optional[str]) -> ReqResult:
    key, op = req["key"], req.get("op", "==")
    critical = bool(req.get("critical", False))
    base = dict(req_id=req["id"], vendor=vendor, critical=critical,
                category=req.get("category", "Documentation"), source=req.get("source", "MDS"),
                weight=int(req.get("weight", 1)), key=key, op=op)

    val, unit, text = offered_value(key, cand, answer)
    offered_disp = _disp(val if val is not None else (text or None), unit if val is not None else "")

    if (cand is None and not answer) or (not str(text or "").strip() and val is None):
        return ReqResult(**base, required=req_disp, offered="—", verdict="Missing",
                         explanation=f"'{key}' is not stated in the offer.",
                         question=f"{vendor}: please state '{key}' explicitly "
                                  f"(required: {req_disp}).",
                         raw_offered="")

    if is_vague(text):
        return ReqResult(**base, required=req_disp, offered=text, verdict="Unclear",
                         explanation=f"Offered '{text}' is not verifiable against {req_disp}.",
                         question=f"{vendor}: '{text}' cannot be verified — please confirm the "
                                  f"actual '{key}' value (required: {req_disp}).",
                         raw_offered=text)

    order = req.get("order")
    if order:
        oi = [str(x).strip().lower() for x in order]
        ro, oo = str(req_val).strip().lower(), str(val or text).strip().lower()
        if ro not in oi or oo not in oi:
            return ReqResult(**base, required=req_disp, offered=str(val or text), verdict="Unclear",
                             explanation=f"'{key}' value is not one of the graded levels {order}.",
                             question=f"{vendor}: please confirm which level of '{key}' is offered.",
                             raw_offered=str(text))
        ok = oi.index(oo) >= oi.index(ro)
        verdict = "Compliant" if ok else "Deviating"
        exp = (f"Offered '{oo}' >= required '{ro}' on the {key} grade order." if ok else
               f"Offered '{oo}' is below the required '{ro}' grade.")
        return ReqResult(**base, required=req_disp, offered=str(val or text), verdict=verdict,
                         explanation=exp, raw_offered=str(text))

    if op in (">=", "<=", "==", ">", "<"):
        rn, on = _num(req_val), _num(val)
        if rn is None or on is None:
            # text comparison
            r_txt, o_txt = str(req_val or "").strip().lower(), str(val or text).strip().lower()
            ok = (r_txt == o_txt) if op == "==" else False
            if op == "contains":
                ok = r_txt in o_txt
            verdict = "Compliant" if ok else "Deviating"
            exp = (f"Offered '{o_txt}' {'==' if op == '==' else op} required '{r_txt}'."
                   if ok else
                   f"Offered '{o_txt}' does not satisfy '{op} {r_txt}'.")
            if op == "contains" and not ok:
                exp = f"Offered '{o_txt}' does not contain '{r_txt}'."
            return ReqResult(**base, required=req_disp, offered=str(val or text),
                             verdict=verdict, explanation=exp, raw_offered=str(text))
        ok = {">=": on >= rn - 1e-9, "<=": on <= rn + 1e-9, "==": abs(on - rn) <= 1e-6 * max(1, abs(rn)),
              ">": on > rn, "<": on < rn}[op]
        verdict = "Compliant" if ok else "Deviating"
        if ok and op == ">=" and on > rn * 1.0001:
            pct = (on - rn) / rn * 100 if rn else 0
            exp = (f"{_disp(on, unit)} ≥ {_disp(rn, req_unit)} — exceeds requirement by "
                   f"{pct:.1f}% (accepted).")
        elif ok:
            exp = f"{_disp(on, unit)} {op} {_disp(rn, req_unit)} — meets {req['id']}."
        else:
            exp = (f"{_disp(on, unit)} does not satisfy {op} {_disp(rn, req_unit)} — deviation "
                   f"on {key}.")
        notes = []
        if key == "shell_material" and str(val) not in ("SA-516-70", "SA-516-70N-HIC", "SA-240-316L"):
            notes.append("grade not present in the approved material list (rules/materials.yaml)")
        return ReqResult(**base, required=req_disp, offered=_disp(on, unit), verdict=verdict,
                         explanation=exp, raw_offered=str(text), notes=notes)

    if op == "contains":
        ok = str(req_val or "").lower() in str(val or text).lower()
        return ReqResult(**base, required=req_disp, offered=str(val or text),
                         verdict="Compliant" if ok else "Deviating",
                         explanation=(f"Offered '{val or text}' contains '{req_val}'." if ok else
                                      f"Offered '{val or text}' does not contain '{req_val}'."),
                         raw_offered=str(text))

    return ReqResult(**base, required=req_disp, offered=str(val or text), verdict="Unclear",
                     explanation=f"Unsupported operator '{op}'.", raw_offered=str(text))


def compare_all(requirements: List[dict], mds: Dict[str, MdsRow],
                offers: Dict[str, Dict[str, Candidate]],
                replies: Dict[tuple, str]) -> List[ReqResult]:
    out: List[ReqResult] = []
    for req in requirements:
        req_val, req_unit, req_disp = required_value(req, mds)
        for vendor, cands in offers.items():
            answer = replies.get((vendor, req["id"]))
            cand = cands.get(req["key"])
            out.append(compare_one(req, req_val, req_unit, req_disp, vendor, cand, answer))
    return out
