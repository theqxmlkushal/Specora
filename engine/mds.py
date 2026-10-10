"""Unified MDS engine: deterministic, YAML-driven, with formula traces.

If an input is RED or missing, dependent rows are marked `BLOCKED: needs <field>`
and are never computed from a guess.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from engine import calculator as calc
from models import FieldValue, MdsRow

BLOCK_MSG = "BLOCKED: needs {field}"


def _ok(fields: Dict[str, FieldValue], key: str) -> bool:
    f = fields.get(key)
    return f is not None and f.value is not None and f.status != "RED"


def _val(fields: Dict[str, FieldValue], key: str):
    return fields[key].value


def _prov(fields: Dict[str, FieldValue], key: str) -> str:
    f = fields.get(key)
    return f.prov.locator if f and f.prov else ""


def build_mds(fields: Dict[str, FieldValue], rules: dict, materials: dict) -> List[MdsRow]:
    rows: List[MdsRow] = []

    def add(key, label, value, unit, method, trace, source, status="GREEN", blocked_by="",
            prov=None):
        rows.append(MdsRow(key=key, label=label, value=value, unit=unit, method=method,
                           trace=trace, source=source, status=status, blocked_by=blocked_by,
                           prov=prov))

    # --- simple carry-overs ------------------------------------------------
    for key, label in (("tag_no", "Tag number"), ("fluid", "Service / fluid"),
                       ("radiography", "Radiography")):
        if _ok(fields, key):
            f = fields[key]
            add(key, label, f.value, f.unit, f.method,
                f"carried from {f.prov.locator}: \"{f.prov.raw_text}\"",
                f"{f.prov.source_file}!{f.prov.locator}", f.status, prov=f.prov)
        else:
            add(key, label, None, None, "derived", BLOCK_MSG.format(field=key),
                "", "RED", blocked_by=key)

    # --- design basis ------------------------------------------------------
    add("design_code", "Design code", rules.get("design_code"), None, "derived",
        f"equipment = {rules.get('equipment')} -> {rules.get('design_code')}",
        "rules/vessel_rules.yaml", "GREEN")

    if _ok(fields, "operating_pressure"):
        op = float(_val(fields, "operating_pressure"))
        dp = calc.design_pressure_mpa_g(op, rules)
        add("design_pressure", "Design pressure", round(dp, 4), "MPa(g)", "derived",
            f"P_design = max(P_op×(1+{rules['design_pressure']['margin_pct']}%), "
            f"P_op+{rules['design_pressure']['min_margin_barg']} bar) = "
            f"max({op:.3f}×1.10, {op:.3f}+0.20) = {dp:.3f} MPa(g)",
            "rules/vessel_rules.yaml#design_pressure", "AMBER")
    else:
        need = "operating_pressure"
        add("design_pressure", "Design pressure", None, "MPa(g)", "derived",
            BLOCK_MSG.format(field=need), "", "RED", blocked_by=need)

    if _ok(fields, "operating_temperature"):
        ot = float(_val(fields, "operating_temperature"))
        dt = calc.design_temperature_c(ot, rules)
        add("design_temperature", "Design temperature", round(dt, 4), "degC", "derived",
            f"T_design = T_op + {rules['design_temperature']['margin_c']} degC = "
            f"{ot:g} + {rules['design_temperature']['margin_c']} = {dt:g} degC",
            "rules/vessel_rules.yaml#design_temperature", "AMBER")
    else:
        add("design_temperature", "Design temperature", None, "degC", "derived",
            BLOCK_MSG.format(field="operating_temperature"), "", "RED",
            blocked_by="operating_temperature")

    # --- material ----------------------------------------------------------
    fluid = _val(fields, "fluid") if _ok(fields, "fluid") else None
    h2s = _val(fields, "h2s_ppm") if _ok(fields, "h2s_ppm") else None
    mdmt = _val(fields, "mdmt_c") if _ok(fields, "mdmt_c") else None
    sour = calc.is_sour(h2s if isinstance(h2s, (int, float)) else None)
    if fluid is not None:
        grade, idx, note = calc.select_material(str(fluid), h2s, mdmt, materials)
        info = materials["materials"][grade]
        add("shell_material", "Shell material", grade, None, "derived",
            f"material rule #{idx+1} [{note}]  (h2s={h2s if h2s is not None else '0'} ppm, "
            f"mdmt={mdmt if mdmt is not None else 'n/a'} degC)",
            "rules/materials.yaml#selection", "AMBER")
        add("allowable_stress", "Allowable stress", info["allowable_mpa"], "MPa", "derived",
            f"S = {info['allowable_mpa']} MPa for {grade} "
            f"(valid {info['min_temp_c']}..{info['max_temp_c']} degC)",
            "rules/materials.yaml", "AMBER")
    else:
        need = "fluid"
        add("shell_material", "Shell material", None, None, "derived",
            BLOCK_MSG.format(field=need), "", "RED", blocked_by=need)
        add("allowable_stress", "Allowable stress", None, "MPa", "derived",
            BLOCK_MSG.format(field=need), "", "RED", blocked_by=need)

    # --- joint efficiency --------------------------------------------------
    rad = _val(fields, "radiography") if _ok(fields, "radiography") else None
    if rad is not None:
        e = calc.joint_efficiency(str(rad), rules)
        add("joint_efficiency", "Joint efficiency", e, None, "derived",
            f"E = {e} (radiography = {rad})",
            "rules/vessel_rules.yaml#joint_efficiency", "AMBER")
    else:
        add("joint_efficiency", "Joint efficiency", None, None, "derived",
            BLOCK_MSG.format(field="radiography"), "", "RED", blocked_by="radiography")

    # --- geometry ----------------------------------------------------------
    id_ok, ca_ok = _ok(fields, "inside_diameter"), _ok(fields, "corrosion_allowance")
    idm = float(_val(fields, "inside_diameter")) if id_ok else None
    ca = float(_val(fields, "corrosion_allowance")) if ca_ok else None
    if id_ok:
        add("inside_diameter", "Inside diameter (as built)", idm, "mm", "extracted",
            f"carried from {_prov(fields, 'inside_diameter')}",
            f"{fields['inside_diameter'].prov.source_file}", fields["inside_diameter"].status,
            prov=fields["inside_diameter"].prov)
    else:
        add("inside_diameter", "Inside diameter (as built)", None, "mm", "extracted",
            BLOCK_MSG.format(field="inside_diameter"), "", "RED", blocked_by="inside_diameter")

    if ca is not None:
        add("corrosion_allowance", "Corrosion allowance", ca, "mm", "extracted",
            f"carried from {_prov(fields, 'corrosion_allowance')}",
            f"{fields['corrosion_allowance'].prov.source_file}",
            fields["corrosion_allowance"].status, prov=fields["corrosion_allowance"].prov)
    else:
        add("corrosion_allowance", "Corrosion allowance", None, "mm", "extracted",
            BLOCK_MSG.format(field="corrosion_allowance"), "", "RED",
            blocked_by="corrosion_allowance")

    # --- thickness / hydrotest / PWHT -------------------------------------
    dp_val = next((r.value for r in rows if r.key == "design_pressure"), None)
    s_val = next((r.value for r in rows if r.key == "allowable_stress"), None)
    e_val = next((r.value for r in rows if r.key == "joint_efficiency"), None)
    blockers = [r.blocked_by for r in rows if r.blocked_by and r.key in
                ("design_pressure", "allowable_stress", "joint_efficiency", "inside_diameter",
                 "corrosion_allowance")]
    if idm is not None and ca is not None:
        add("inside_diameter_corroded", "Inside diameter (corroded)", round(idm + 2 * ca, 4),
            "mm", "derived", f"D_corr = D + 2×CA = {idm:g} + 2×{ca:g} = {idm + 2*ca:g} mm",
            "geometry", "AMBER")

    if not blockers and dp_val is not None and s_val is not None and e_val is not None:
        R = idm / 2.0 + ca
        try:
            t_req, t_with_ca = calc.shell_min_thickness_mm(float(dp_val), idm / 2.0,
                                                            float(s_val),
                                                            float(e_val), float(ca))
            trace = (f"t = P·R/(S·E−0.6P) = {float(dp_val):.3f}·{R:.1f}/"
                     f"({float(s_val):g}×{e_val:g}−0.6×{float(dp_val):.3f}) = {t_req:.2f} mm "
                     f"(+CA = {t_with_ca:.2f} mm)")
            add("shell_thickness_required", "Shell thickness (required)", round(t_req, 4), "mm",
                "derived", trace, "ASME VIII-1 UG-27(c)(1)", "AMBER")
            sel = calc.select_standard_thickness(t_with_ca, rules["thickness_ladder_mm"])
            add("shell_thickness", "Shell thickness (selected)", sel, "mm", "derived",
                f"ladder {rules['thickness_ladder_mm']} → first ≥ {t_with_ca:.2f} mm = {sel:g} mm",
                "rules/vessel_rules.yaml#thickness_ladder_mm", "AMBER")
            ht = calc.hydrotest_mpa_g(float(dp_val), rules["hydrotest"]["factor"],
                                      rules["hydrotest"]["stress_ratio"])
            add("hydrotest_pressure", "Hydrotest pressure", round(ht, 4), "MPa(g)", "derived",
                f"P_ht = {rules['hydrotest']['factor']} × P_design × "
                f"{rules['hydrotest']['stress_ratio']} = {rules['hydrotest']['factor']} × "
                f"{float(dp_val):.3f} = {ht:.3f} MPa(g)  [UG-99(b), edition to confirm]",
                "rules/vessel_rules.yaml#hydrotest", "AMBER")
            pwht = calc.pwht_required(float(sel), sour, rules)
            add("pwht", "PWHT required", "Yes" if pwht else "No", None, "derived",
                f"rule: sour_service={sour}, t={sel:g} mm > "
                f"{rules['pwht_required_if']['thickness_mm_gt']} mm? "
                f"{'Yes' if float(sel) > rules['pwht_required_if']['thickness_mm_gt'] else 'No'}",
                "rules/vessel_rules.yaml#pwht_required_if", "AMBER")
        except ValueError as exc:
            add("shell_thickness_required", "Shell thickness (required)", None, "mm", "derived",
                f"BLOCKED: {exc}", "ASME VIII-1 UG-27(c)(1)", "RED", blocked_by="engineer_check")
            for k, lab, u in (("shell_thickness", "Shell thickness (selected)", "mm"),
                              ("hydrotest_pressure", "Hydrotest pressure", "MPa(g)"),
                              ("pwht", "PWHT required", None)):
                add(k, lab, None, u, "derived", "BLOCKED: needs engineer check",
                    "", "RED", blocked_by="engineer_check")
    else:
        need = blockers[0] if blockers else "design basis inputs"
        for k, lab, u in (("shell_thickness_required", "Shell thickness (required)", "mm"),
                          ("shell_thickness", "Shell thickness (selected)", "mm"),
                          ("hydrotest_pressure", "Hydrotest pressure", "MPa(g)"),
                          ("pwht", "PWHT required", None)):
            add(k, lab, None, u, "derived", BLOCK_MSG.format(field=need), "", "RED",
                blocked_by=need)
    return rows


def mds_map(rows: List[MdsRow]) -> Dict[str, MdsRow]:
    return {r.key: r for r in rows}


def export_mds(rows: List[MdsRow], template, out_path) -> str:
    """Fill MDS_template.xlsx; derived cells get their trace as a cell comment."""
    from openpyxl import load_workbook
    from openpyxl.comments import Comment
    wb = load_workbook(str(template))
    ws = wb["MDS"]
    by_label = {str(r.label).strip().lower(): r for r in rows}
    for row in ws.iter_rows(min_row=5):
        label = str(row[1].value or "").strip().lower()
        r = by_label.get(label)
        if r is None:
            # fall back to key-ish match
            key = label.replace(" ", "_")
            r = next((x for x in rows if x.key == key or x.key.startswith(key)), None)
        if r is None:
            continue
        if r.value is None:
            row[2].value = r.blocked_by and f"BLOCKED: needs {r.blocked_by}" or "—"
        else:
            row[2].value = r.value
        if r.unit:
            row[3].value = r.unit
        row[4].value = r.method
        row[5].value = r.source
        if r.trace:
            cm = Comment(r.trace, "SpecForge")
            cm.width, cm.height = 340, 120
            row[2].comment = cm
    wb.save(str(out_path))
    return str(out_path)
