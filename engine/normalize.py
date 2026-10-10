"""Deterministic unit normalization: pressure -> MPa(g), temperature -> degC, length -> mm.

Small explicit functions on purpose (gauge vs absolute needs custom handling).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from models import Issue

ATM_MPA = 0.101325

_NUM = re.compile(r"^(?P<num>[-+]?\d[\d\s_]*(?:[.,]\d+)?)\s*(?P<unit>[A-Za-z°/%µ³²().:-]*)$")


def parse_number(txt) -> Tuple[Optional[float], List[str], Optional[str]]:
    """Return (value, notes, ambiguity_code). Handles decimal comma / thousands."""
    if txt is None:
        return None, [], None
    if isinstance(txt, (int, float)):
        return float(txt), [], None
    s = str(txt).strip().replace("\u2212", "-").replace("_", "")
    if not s:
        return None, [], None
    s = s.replace(" ", "")
    notes: List[str] = []
    amb = None
    if "," in s and "." not in s:
        tail = s.rsplit(",", 1)[1]
        if len(tail) == 3 and s.count(",") == 1:
            s = s.replace(",", "")
            notes.append("interpreted '1,200' style as thousands separator")
            amb = "UNIT_AMBIGUOUS"
        else:
            s = s.replace(",", ".")
            notes.append("interpreted decimal comma (e.g. '1,5' -> 1.5)")
            amb = "UNIT_AMBIGUOUS"
    elif "," in s and "." in s:
        s = s.replace(",", "")
    try:
        return float(s), notes, amb
    except ValueError:
        return None, [], None


def split_value_unit(txt) -> Tuple[Optional[float], str, List[str], Optional[str]]:
    """'145 psig' -> (145, 'psig'). Non numeric text -> (None, text)."""
    if txt is None:
        return None, "", [], None
    if isinstance(txt, (int, float)):
        return float(txt), "", [], None
    s = str(txt).strip()
    if not s:
        return None, "", [], None
    m = _NUM.match(s)
    if not m:
        return None, s, [], None
    num, notes, amb = parse_number(m.group("num"))
    if num is None:
        return None, s, [], None
    return num, (m.group("unit") or "").strip(), notes, amb


def _norm_unit(u: str) -> str:
    return (u or "").strip().lower().replace(" ", "").replace("(", "").replace(")", "")


def normalize_pressure(value: Optional[float], unit: str, key: str = "pressure",
                       locator: str = "", label: str = "") -> Tuple[Optional[float], str, List[str], Optional[Issue]]:
    """-> (MPa(g), canonical unit, notes, issue|None)"""
    if value is None:
        return None, "MPa(g)", [], None
    u = _norm_unit(unit)
    notes: List[str] = []
    issue = None
    abs_ = u.endswith("a") and not u.endswith("g") and u not in ("mpa",)
    if u in ("mpa",):
        # bare MPa -> ambiguous gauge/abs
        issue = Issue(code="UNIT_AMBIGUOUS", key=key, severity="AMBER",
                      message=f"Pressure '{value} MPa' does not state gauge or absolute ({locator}).",
                      question="Is this pressure gauge or absolute? Please confirm with the process engineer.",
                      locators=[locator] if locator else [])
        return value, "MPa(g)", notes, issue
    if u in ("mpag", "mpag)", "mpagauge", "mpag"):
        return value, "MPa(g)", notes, None
    if u in ("mpaa", "mpaabs", "mpaab"):
        notes.append(f"converted from {value} MPa(a) to gauge (−{ATM_MPA} MPa)")
        return round(value - ATM_MPA, 6), "MPa(g)", notes + ["absolute -> gauge"], None
    if u in ("bar", "barbarg"):  # bare bar
        issue = Issue(code="UNIT_AMBIGUOUS", key=key, severity="AMBER",
                      message=f"Pressure '{value} bar' does not state gauge or absolute ({locator}).",
                      question="Is 'bar' gauge or absolute here? Please confirm with the process engineer.",
                      locators=[locator] if locator else [])
        notes.append("unit 'bar' assumed gauge (unconfirmed)")
        return value / 10.0, "MPa(g)", notes, issue
    if u in ("barg", "barg)", "bar(g)", "bargauge"):
        return value / 10.0, "MPa(g)", notes, None
    if u in ("bara", "bar(a)", "barabs", "barabsolute"):
        notes.append(f"converted from {value} bara to gauge (−{ATM_MPA} MPa)")
        return round(value / 10.0 - ATM_MPA, 6), "MPa(g)", notes, None
    if u in ("psig", "psi(g)", "psigauge"):
        notes.append(f"converted from {value} psig")
        return round(value * 0.006894757, 6), "MPa(g)", notes, None
    if u in ("psia", "psi(a)", "psiabs"):
        notes.append(f"converted from {value} psia to gauge")
        return round(value * 0.006894757 - ATM_MPA, 6), "MPa(g)", notes, None
    if u in ("psi",):
        issue = Issue(code="UNIT_AMBIGUOUS", key=key, severity="AMBER",
                      message=f"Pressure '{value} psi' does not state gauge or absolute ({locator}).",
                      question="Is this psi gauge or absolute? Please confirm with the process engineer.",
                      locators=[locator] if locator else [])
        notes.append(f"converted from {value} psi (assumed gauge)")
        return round(value * 0.006894757, 6), "MPa(g)", notes, issue
    if u in ("kpag", "kpa(g)"):
        return value / 1000.0, "MPa(g)", notes, None
    if u in ("kpa", "kpaa"):
        return round(value / 1000.0, 6), "MPa(g)", [f"converted from {value} kPa"], None
    if u == "":
        issue = Issue(code="UNIT_AMBIGUOUS", key=key, severity="RED",
                      message=f"Pressure '{value}' has no unit ({locator}) — gauge/absolute unknown.",
                      question="What unit and convention is this pressure in (bar(g), bara, ...)? "
                               "Please confirm with the process engineer.",
                      locators=[locator] if locator else [])
        return None, "MPa(g)", ["unit missing — value not accepted"], issue
    # unknown unit
    issue = Issue(code="UNIT_AMBIGUOUS", key=key, severity="RED",
                  message=f"Unrecognised pressure unit '{unit}' for '{value}' ({locator}).",
                  question=f"Please confirm the pressure unit '{unit}' with the process engineer.",
                  locators=[locator] if locator else [])
    return None, "MPa(g)", [f"unrecognised unit '{unit}'"], issue


def normalize_temperature(value: Optional[float], unit: str, key: str = "temperature",
                          locator: str = "") -> Tuple[Optional[float], str, List[str], Optional[Issue]]:
    if value is None:
        return None, "degC", [], None
    u = _norm_unit(unit)
    notes: List[str] = []
    if u in ("degc", "c", "°c", "degc)", "celsius"):
        return value, "degC", notes, None
    if u in ("degf", "f", "°f", "degf)", "fahrenheit"):
        notes.append(f"converted from {value} degF")
        return round((value - 32) * 5 / 9, 4), "degC", notes, None
    if u in ("k", "kelvin"):
        notes.append(f"converted from {value} K")
        return round(value - 273.15, 4), "degC", notes, None
    if u == "":
        issue = Issue(code="UNIT_AMBIGUOUS", key=key, severity="RED",
                      message=f"Temperature '{value}' has no unit ({locator}).",
                      question="Is this temperature in degC, degF or K? Please confirm with the process engineer.",
                      locators=[locator] if locator else [])
        return None, "degC", ["unit missing — value not accepted"], issue
    issue = Issue(code="UNIT_AMBIGUOUS", key=key, severity="RED",
                  message=f"Unrecognised temperature unit '{unit}' ({locator}).",
                  question=f"Please confirm the temperature unit '{unit}' with the process engineer.",
                  locators=[locator] if locator else [])
    return None, "degC", [f"unrecognised unit '{unit}'"], issue


def normalize_length(value: Optional[float], unit: str, key: str = "length",
                     locator: str = "", extra_notes=None) -> Tuple[Optional[float], str, List[str], Optional[Issue]]:
    if value is None:
        return None, "mm", [], None
    u = _norm_unit(unit)
    notes: List[str] = list(extra_notes or [])
    if u in ("mm", "millimeter", "millimetre", "mms"):
        return value, "mm", notes, None
    if u in ("cm",):
        notes.append(f"converted from {value} cm")
        return value * 10, "mm", notes, None
    if u in ("m", "meter", "metre") and value is not None:
        notes.append(f"converted from {value} m")
        return value * 1000, "mm", notes, None
    if u in ("in", "inch", "inches", '"', "″"):
        notes.append(f"converted from {value} in")
        return round(value * 25.4, 4), "mm", notes, None
    if u in ("ft", "feet", "foot", "'"):
        notes.append(f"converted from {value} ft")
        return round(value * 304.8, 4), "mm", notes, None
    if u == "":
        issue = Issue(code="UNIT_AMBIGUOUS", key=key, severity="RED",
                      message=f"Length '{value}' has no unit ({locator}).",
                      question="What unit is this dimension in? Please confirm with the process engineer.",
                      locators=[locator] if locator else [])
        return None, "mm", ["unit missing — value not accepted"], issue
    issue = Issue(code="UNIT_AMBIGUOUS", key=key, severity="RED",
                  message=f"Unrecognised length unit '{unit}' ({locator}).",
                  question=f"Please confirm the length unit '{unit}' with the process engineer.",
                  locators=[locator] if locator else [])
    return None, "mm", [f"unrecognised unit '{unit}'"], issue


def normalize_value(key: str, value, unit: str, locator: str = ""):
    """Dispatch on canonical key kind. Returns (value, unit, notes, issue)."""
    from config import CANONICAL_UNITS
    canon = CANONICAL_UNITS.get(key)
    notes: List[str] = []
    amb_issue = None
    if canon in ("MPa(g)",):
        v, notes, amb = _amb(value, locator, key)
        val, u, n, iss = normalize_pressure(v, unit, key, locator)
        notes = n + notes
        return val, u, notes, iss or amb_issue_from(amb, key, locator)
    if canon == "degC":
        v, notes, amb = _amb(value, locator, key)
        val, u, n, iss = normalize_temperature(v, unit, key, locator)
        return val, u, n + notes, iss or amb_issue_from(amb, key, locator)
    if canon == "mm":
        v, notes, amb = _amb(value, locator, key)
        val, u, n, iss = normalize_length(v, unit, key, locator, notes)
        return val, u, n, iss or amb_issue_from(amb, key, locator)
    if canon:  # ppm or other plain number
        v, notes, amb = _amb(value, locator, key)
        if v is None:
            return None, canon, notes, amb_issue_from(amb, key, locator)
        return v, canon, notes, amb_issue_from(amb, key, locator)
    # text field
    txt = "" if value is None else str(value).strip()
    return (txt or None), None, [], None


def _amb(value, locator, key):
    if isinstance(value, str):
        return parse_number(value)[0], parse_number(value)[1], parse_number(value)[2]
    return value, [], None


def amb_issue_from(code, key, locator):
    if not code:
        return None
    return Issue(code=code, key=key, severity="AMBER",
                 message=f"Ambiguous number format ({locator}) — thousands vs decimal comma.",
                 question="Confirm the intended number (e.g. 1,200 = 1200 or 1.2?). "
                          "Please confirm with the process engineer.",
                 locators=[locator] if locator else [])
