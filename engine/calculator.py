"""Deterministic design maths — pure functions, unit tested (tests/test_calculator.py).

Demo rule values: CONFIRM WITH EXPERT.  Not a certified design tool.
"""
from __future__ import annotations

from typing import List, Optional, Tuple


def design_pressure_mpa_g(p_op_mpa_g: float, rules: dict) -> float:
    m = rules["design_pressure"]
    return max(p_op_mpa_g * (1 + m["margin_pct"] / 100), p_op_mpa_g + m["min_margin_barg"] / 10)


def design_temperature_c(t_op_c: float, rules: dict) -> float:
    return t_op_c + rules["design_temperature"]["margin_c"]


def shell_min_thickness_mm(P_mpa_g: float, R_inside_mm: float, S_mpa: float, E: float, CA_mm: float):
    """ASME VIII-1 UG-27(c)(1): t = P*R / (S*E - 0.6*P), R = inside radius, corroded."""
    R = R_inside_mm + CA_mm
    denom = S_mpa * E - 0.6 * P_mpa_g
    if denom <= 0 or P_mpa_g > 0.385 * S_mpa * E:
        raise ValueError("Outside UG-27 thin-wall validity: flag for engineer")
    t_req = P_mpa_g * R / denom
    return t_req, t_req + CA_mm            # (required, required + CA)


def select_standard_thickness(t_mm: float, ladder: List[float]) -> float:
    for x in ladder:
        if x >= t_mm:
            return float(x)
    raise ValueError(f"Required thickness {t_mm:.2f} mm exceeds the biggest ladder step "
                     f"{max(ladder)} mm — flag for engineer")


def hydrotest_mpa_g(P_design_mpa_g: float, factor: float, stress_ratio: float = 1.0) -> float:
    return factor * P_design_mpa_g * stress_ratio


def joint_efficiency(radiography: Optional[str], rules: dict) -> float:
    key = (radiography or "none").strip().lower()
    if key in ("full", "full rt", "100%", "rt full"):
        return rules["joint_efficiency"]["full"]
    if key in ("spot", "spot rt", "partial"):
        return rules["joint_efficiency"]["spot"]
    return rules["joint_efficiency"]["none"]


def select_material(fluid: str, h2s_ppm: Optional[float], mdmt_c: Optional[float],
                    materials: dict) -> Tuple[str, int, str]:
    """First match wins. Returns (grade, rule_index, note)."""
    fluid_l = (fluid or "").lower()
    for idx, rule in enumerate(materials["selection"]):
        when = rule.get("when")
        if when is None and rule.get("default"):
            return rule["select"], idx, rule.get("note", "default rule")
        if when is None:
            continue
        if "h2s_ppm_gt" in when:
            if h2s_ppm is None or not (h2s_ppm > when["h2s_ppm_gt"]):
                continue
            return rule["select"], idx, rule.get("note", "")
        if "fluid_contains" in when:
            if not any(tok in fluid_l for tok in when["fluid_contains"]):
                continue
            return rule["select"], idx, rule.get("note", "")
        if "mdmt_c_lt" in when:
            if mdmt_c is None or not (mdmt_c < when["mdmt_c_lt"]):
                continue
            return rule["select"], idx, rule.get("note", "")
    last = materials["selection"][-1]
    return last["select"], len(materials["selection"]) - 1, last.get("note", "")


def pwht_required(t_mm: Optional[float], sour_service: bool, rules: dict) -> bool:
    cond = rules["pwht_required_if"]
    if sour_service and cond.get("sour_service"):
        return True
    if t_mm is not None and t_mm > cond["thickness_mm_gt"]:
        return True
    return False


def is_sour(h2s_ppm: Optional[float]) -> bool:
    return bool(h2s_ppm is not None and h2s_ppm > 0)
