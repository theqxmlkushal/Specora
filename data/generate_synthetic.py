"""Generate the synthetic, sanitised demo corpus for SpecForge.

Run once:  python data/generate_synthetic.py

Outputs (committed):
  data/pds/*.xlsx|*.txt     8 Process Data Sheets in 3 layouts
  data/extra/PDS_V-109.pdf  optional PDF PDS (only if reportlab is installed)
  data/vendor/*.xlsx        3 vendor offers (A: mostly compliant, B: cheap but
                            deviating, C: incomplete / vague)
  data/ground_truth.json    canonical values + seeded traps + expected verdicts
  templates/MDS_template.xlsx

Everything here is synthetic.  No real company document is ever used.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = Path(__file__).resolve().parent.parent
PDS_DIR = ROOT / "data" / "pds"
VENDOR_DIR = ROOT / "data" / "vendor"
EXTRA_DIR = ROOT / "data" / "extra"
TEMPLATE_DIR = ROOT / "templates"

HDR_FILL = PatternFill("solid", fgColor="1F3B63")
HDR_FONT = Font(bold=True, color="FFFFFF")
LBL_FONT = Font(bold=True, color="DCE6F5")
THIN = Side(style="thin", color="8FA8C8")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


# --------------------------------------------------------------------- helpers
def _sheet(rows, title="PDS"):
    wb = Workbook()
    ws = wb.active
    ws.title = title
    for r in rows:
        ws.append(r)
    for cell in ws[1]:
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(horizontal="center")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = BORDER
            if cell.column == 1:
                cell.font = LBL_FONT
    for col, width in zip("ABCDE", (34, 44, 12, 26, 26)):
        ws.column_dimensions[col].width = width
    return wb, ws


def write_l1(path: Path, rows, title="PDS"):
    """Layout L1: vertical table  label | value | unit."""
    wb, ws = _sheet([["Parameter", "Value", "Unit"]] + rows, title)
    wb.save(path)


def write_l2(path: Path, headers, values, title="Offer"):
    """Layout L2: horizontal header row + one value row."""
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(headers)
    ws.append(values)
    for cell in ws[1]:
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
    for cell in ws[2]:
        cell.border = BORDER
    for i, _ in enumerate(headers, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(
            14, min(30, len(str(headers[i - 1])) + 4)
        )
    wb.save(path)


def write_text(path: Path, lines):
    """Layout L3: free-text notes, one 'Label: value unit' per line."""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ PDS files
# L1 ---------------------------------------------------------------------
PDS_V101 = [  # clean golden case: P=8 bar(g), ID=1200, CA=3, spot RT, SA-516-70
    ("Tag No", "V-101", ""),
    ("Fluid", "Sweet crude oil and water", ""),
    ("Operating Pressure", 8, "bar(g)"),
    ("Operating Temperature", 60, "degC"),
    ("Design Pressure", 10, "bar(g)"),
    ("Design Temperature", 80, "degC"),
    ("Inside Diameter", 1200, "mm"),
    ("Tan to Tan Length", 3000, "mm"),
    ("Corrosion Allowance", 3, "mm"),
    ("Radiography", "spot", ""),
    ("Design Code", "ASME VIII-1", ""),
]

PDS_V102 = [  # trap showcase: T1 psi, T4 conflict, T5 missing CA, T6 inch, T7 degF
    ("Tag No", "V-102", ""),
    ("Fluid", "Condensate", ""),
    ("Operating Pressure", 145, "psig"),          # T1
    ("Operating Temperature", 212, "degF"),       # T7
    ("Inside Diameter", 48, "in"),                # T6
    ("Tan to Tan Length", 3500, "mm"),
    ("Corrosion Allowance", "", "mm"),            # T5  (label present, value blank)
    ("Radiography", "full", ""),
    ("Design Pressure", 10, "bar(g)"),
    ("Remarks", "Design pressure as per process note: 8 barg", ""),   # T4 conflict
]

PDS_V103 = [  # T3 unitless pressure, T8 ambiguous thousands/decimal comma
    ("Tag No", "V-103", ""),
    ("Fluid", "Lean amine", ""),
    ("Operating Pressure", 8, ""),                # T3  no unit at all
    ("Operating Temperature", 55, "degC"),
    ("Design Pressure", 10, "bar(g)"),
    ("Inside Diameter", "1,200", "mm"),           # T8
    ("Tan to Tan Length", 2900, "mm"),
    ("Corrosion Allowance", 3, "mm"),
    ("Radiography", "spot", ""),
]

# L2 ---------------------------------------------------------------------
def l2(name, headers, values, title="PDS"):
    write_l2(PDS_DIR / name, headers, values, title)


BASE_HEADERS = [
    "Tag No", "Fluid", "Operating Pressure", "Operating Temperature",
    "Design Pressure", "Design Temperature", "Inside Diameter",
    "Tan to Tan Length", "Corrosion Allowance", "Radiography",
]

PDS_V104_VALUES = [   # T9 H2S in fluid, T10 design < operating
    "V-104", "Sour condensate, H2S 150 ppm", "8 bar(g)", "65 degC",
    "6 bar(g)", "85 degC", "1100 mm", "3200 mm", "3 mm", "full",
]

PDS_V105_HEADERS = [   # T11 unknown label "Duty pressure"
    "Tag No", "Fluid", "Duty Pressure", "Operating Temperature",
    "Inside Diameter", "Tan to Tan Length", "Corrosion Allowance", "Radiography",
]
PDS_V105_VALUES = [
    "V-105", "Sweet gas", "8.0 bar(g)", "65 degC",
    "1000 mm", "2800 mm", "3 mm", "spot",
]

PDS_V106_VALUES = [   # clean second L2 sheet
    "V-106", "Sweet crude oil", "10 bar(g)", "70 degC",
    "12 bar(g)", "90 degC", "1400 mm", "3600 mm", "3 mm", "full",
]

# L3 ---------------------------------------------------------------------
PDS_V107 = [
    "PROCESS DATA SHEET - UNFIRED PRESSURE VESSEL",
    "Tag No: V-107",
    "Fluid: Sour condensate gas",
    "Operating pressure: 9.0 barg",
    "Design pressure: 11.0 bara",            # T2 gauge vs absolute
    "Operating temperature: 95 degC",
    "Design temperature: 115 degC",
    "Inside diameter: 36 in",
    "Tan to tan length: 10000 mm",
    "Corrosion allowance: 3 mm",
    "Radiography: full",
    "Remarks: insulated with 50 mm rockwool",
]

PDS_V108 = [
    "PROCESS DATA SHEET - UNFIRED PRESSURE VESSEL",
    "Tag No: V-108",
    "Fluid: Produced water, H2S 250 ppm",
    "Operating pressure: 12 barg",
    "Operating temperature: 80 degC",
    "Design pressure: 14 barg",
    "Design temperature: 100 degC",
    "Inside diameter: 900 mm",
    "Tan to tan length: 2500 mm",
    "Corrosion allowance: 3 mm",
    "Radiography: full",
    "MDMT: -40 degC",
]


# ------------------------------------------------------------------- vendors
VENDOR_HEADERS = [
    "Tag No", "Vendor", "Design pressure", "Design temperature", "Shell material",
    "Shell thickness", "Corrosion allowance", "Radiography", "Hydrotest pressure",
    "Design code", "PWHT", "Certificates", "Inspection witness", "Painting",
    "Delivery documents", "Price EUR", "Delivery weeks",
]

VENDOR_A = [
    "V-101", "Vendor A", "12 barg", "100 degC", "SA-516-70", "10 mm", "2.5 mm",
    "spot", "13 barg", "ASME VIII-1", "No", "EN 10204 3.1", "Witness at hydrotest",
    "Touch-up only", "Packing list, certificate dossier", 185000, 34,
]   # 2 minor deviations: R05 corrosion allowance, R12 painting

VENDOR_B = [
    "V-101", "Vendor B", "11 barg", "90 degC", "SA-516-60", "8 mm", "3 mm",
    "spot", "13.5 barg", "ASME VIII-1", "No", "EN 10204 3.1", "Witness at hydrotest",
    "3-coat epoxy", "Packing list", 152000, 30,
]   # cheap: critical deviations on material (R03) and thickness (R04)

VENDOR_C = [
    "V-101", "Vendor C", "12 barg", "90 degC", "as per standard", "per code",
    "", "as required by code", "", "as per standard", "TBC", "", "TBC", "", "",
    141000, 26,
]   # incomplete and vague


# ------------------------------------------------------------ MDS template
def write_mds_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "MDS"
    rows = [
        ("1", "Tag number", "", "", "extracted", "PDS"),
        ("2", "Service / fluid", "", "", "extracted", "PDS"),
        ("3", "Design code", "", "", "derived", "rules/vessel_rules.yaml"),
        ("4", "Design pressure", "", "MPa(g)", "derived", "P_design = max(Pop*1.10, Pop+2 bar)"),
        ("5", "Design temperature", "", "degC", "derived", "T_design = Top + 20 degC"),
        ("6", "Shell material", "", "", "derived", "rules/materials.yaml"),
        ("7", "Allowable stress", "", "MPa", "derived", "rules/materials.yaml"),
        ("8", "Joint efficiency", "", "", "derived", "rules/vessel_rules.yaml"),
        ("9", "Inside diameter (corroded)", "", "mm", "derived", "geometry"),
        ("10", "Shell thickness (required)", "", "mm", "derived", "t = P*R/(S*E-0.6P)"),
        ("11", "Shell thickness (selected)", "", "mm", "derived", "standard ladder"),
        ("12", "Corrosion allowance", "", "mm", "extracted", "PDS"),
        ("13", "Hydrotest pressure", "", "MPa(g)", "derived", "1.3 * P_design"),
        ("14", "PWHT required", "", "", "derived", "rules/vessel_rules.yaml"),
        ("15", "Radiography", "", "", "extracted", "PDS"),
        ("16", "MDS status", "", "", "default", "approval gate"),
    ]
    ws["A1"] = "MECHANICAL DATA SHEET (draft) — unfired pressure vessel"
    ws["A1"].font = Font(bold=True, size=14, color="1F3B63")
    ws["A2"] = "Prototype output — engineer approval required before use."
    headers = ["#", "MDS item", "Value", "Unit", "Method", "Source / formula"]
    ws.append([])
    ws.append(headers)
    for c in ws[4]:
        c.fill, c.font, c.border = HDR_FILL, HDR_FONT, BORDER
    for r in rows:
        ws.append(list(r))
    for row in ws.iter_rows(min_row=5, max_row=4 + len(rows)):
        for c in row:
            c.border = BORDER
    for col, width in zip("ABCDEF", (5, 34, 26, 12, 14, 46)):
        ws.column_dimensions[col].width = width
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMPLATE_DIR / "MDS_template.xlsx"
    wb.save(path)
    return path


# ---------------------------------------------------------------- ground truth
def canonical_from(rows, unit_map):
    """rows: list of (key, value, unit) already in canonical units."""
    out = {}
    for key, value, unit in rows:
        out[key] = {"value": value, "unit": unit or None}
    return out


GROUND_TRUTH = {
    "note": "Synthetic ground truth. All values generated by data/generate_synthetic.py.",
    "pds": {
        "PDS_V-101_L1.xlsx": {
            "layout": "L1",
            "canonical": {
                "tag_no": {"value": "V-101", "unit": None},
                "fluid": {"value": "Sweet crude oil and water", "unit": None},
                "operating_pressure": {"value": 0.8, "unit": "MPa(g)"},
                "operating_temperature": {"value": 60, "unit": "degC"},
                "design_pressure": {"value": 1.0, "unit": "MPa(g)"},
                "design_temperature": {"value": 80, "unit": "degC"},
                "inside_diameter": {"value": 1200, "unit": "mm"},
                "tan_to_tan_length": {"value": 3000, "unit": "mm"},
                "corrosion_allowance": {"value": 3, "unit": "mm"},
                "radiography": {"value": "spot", "unit": None},
                "design_code": {"value": "ASME VIII-1", "unit": None},
            },
            "expected_issues": [],
        },
        "PDS_V-102_L1.xlsx": {
            "layout": "L1",
            "canonical": {
                "tag_no": {"value": "V-102", "unit": None},
                "fluid": {"value": "Condensate", "unit": None},
                "operating_pressure": {"value": 1.0, "unit": "MPa(g)"},
                "operating_temperature": {"value": 100, "unit": "degC"},
                "design_pressure": {"value": None, "unit": "MPa(g)", "conflict": True},
                "inside_diameter": {"value": 1219.2, "unit": "mm"},
                "tan_to_tan_length": {"value": 3500, "unit": "mm"},
                "corrosion_allowance": {"value": None, "unit": "mm", "missing": True},
                "radiography": {"value": "full", "unit": None},
            },
            "expected_issues": [
                {"key": "corrosion_allowance", "code": "MISSING", "severity": "RED"},
                {"key": "design_pressure", "code": "CONFLICT", "severity": "RED"},
            ],
        },
        "PDS_V-103_L1.xlsx": {
            "layout": "L1",
            "canonical": {
                "tag_no": {"value": "V-103", "unit": None},
                "fluid": {"value": "Lean amine", "unit": None},
                "operating_pressure": {"value": None, "unit": None, "ambiguous": True},
                "operating_temperature": {"value": 55, "unit": "degC"},
                "design_pressure": {"value": 1.0, "unit": "MPa(g)"},
                "inside_diameter": {"value": 1200, "unit": "mm"},
                "tan_to_tan_length": {"value": 2900, "unit": "mm"},
                "corrosion_allowance": {"value": 3, "unit": "mm"},
                "radiography": {"value": "spot", "unit": None},
            },
            "expected_issues": [
                {"key": "operating_pressure", "code": "UNIT_AMBIGUOUS", "severity": "RED"},
                {"key": "inside_diameter", "code": "UNIT_AMBIGUOUS", "severity": "AMBER"},
            ],
        },
        "PDS_V-104_L2.xlsx": {
            "layout": "L2",
            "canonical": {
                "tag_no": {"value": "V-104", "unit": None},
                "fluid": {"value": "Sour condensate, H2S 150 ppm", "unit": None},
                "h2s_ppm": {"value": 150, "unit": "ppm"},
                "operating_pressure": {"value": 0.8, "unit": "MPa(g)"},
                "operating_temperature": {"value": 65, "unit": "degC"},
                "design_pressure": {"value": 0.6, "unit": "MPa(g)"},
                "design_temperature": {"value": 85, "unit": "degC"},
                "inside_diameter": {"value": 1100, "unit": "mm"},
                "tan_to_tan_length": {"value": 3200, "unit": "mm"},
                "corrosion_allowance": {"value": 3, "unit": "mm"},
                "radiography": {"value": "full", "unit": None},
            },
            "expected_issues": [
                {"key": "design_pressure", "code": "RULE_VIOLATION", "severity": "RED"},
            ],
        },
        "PDS_V-105_L2.xlsx": {
            "layout": "L2",
            "canonical": {
                "tag_no": {"value": "V-105", "unit": None},
                "fluid": {"value": "Sweet gas", "unit": None},
                "operating_pressure": {"value": 0.8, "unit": "MPa(g)"},
                "operating_temperature": {"value": 65, "unit": "degC"},
                "inside_diameter": {"value": 1000, "unit": "mm"},
                "tan_to_tan_length": {"value": 2800, "unit": "mm"},
                "corrosion_allowance": {"value": 3, "unit": "mm"},
                "radiography": {"value": "spot", "unit": None},
            },
            "expected_issues": [
                {"key": "operating_pressure", "code": "MISSING", "severity": "RED"},
                {"key": "hydrotest_pressure", "code": "LOW_MATCH", "severity": "AMBER"},
            ],
            "alias_demo": {"label": "Duty Pressure", "canonical": "operating_pressure"},
        },
        "PDS_V-106_L2.xlsx": {
            "layout": "L2",
            "canonical": {
                "tag_no": {"value": "V-106", "unit": None},
                "fluid": {"value": "Sweet crude oil", "unit": None},
                "operating_pressure": {"value": 1.0, "unit": "MPa(g)"},
                "operating_temperature": {"value": 70, "unit": "degC"},
                "design_pressure": {"value": 1.2, "unit": "MPa(g)"},
                "design_temperature": {"value": 90, "unit": "degC"},
                "inside_diameter": {"value": 1400, "unit": "mm"},
                "tan_to_tan_length": {"value": 3600, "unit": "mm"},
                "corrosion_allowance": {"value": 3, "unit": "mm"},
                "radiography": {"value": "full", "unit": None},
            },
            "expected_issues": [],
        },
        "PDS_V-107_L3.txt": {
            "layout": "L3",
            "canonical": {
                "tag_no": {"value": "V-107", "unit": None},
                "fluid": {"value": "Sour condensate gas", "unit": None},
                "operating_pressure": {"value": 0.9, "unit": "MPa(g)"},
                "design_pressure": {"value": 0.99868, "unit": "MPa(g)"},
                "operating_temperature": {"value": 95, "unit": "degC"},
                "design_temperature": {"value": 115, "unit": "degC"},
                "inside_diameter": {"value": 914.4, "unit": "mm"},
                "tan_to_tan_length": {"value": 10000, "unit": "mm"},
                "corrosion_allowance": {"value": 3, "unit": "mm"},
                "radiography": {"value": "full", "unit": None},
            },
            "expected_issues": [],
        },
        "PDS_V-108_L3.txt": {
            "layout": "L3",
            "canonical": {
                "tag_no": {"value": "V-108", "unit": None},
                "fluid": {"value": "Produced water, H2S 250 ppm", "unit": None},
                "h2s_ppm": {"value": 250, "unit": "ppm"},
                "operating_pressure": {"value": 1.2, "unit": "MPa(g)"},
                "operating_temperature": {"value": 80, "unit": "degC"},
                "design_pressure": {"value": 1.4, "unit": "MPa(g)"},
                "design_temperature": {"value": 100, "unit": "degC"},
                "inside_diameter": {"value": 900, "unit": "mm"},
                "tan_to_tan_length": {"value": 2500, "unit": "mm"},
                "corrosion_allowance": {"value": 3, "unit": "mm"},
                "radiography": {"value": "full", "unit": None},
                "mdmt_c": {"value": -40, "unit": "degC"},
            },
            "expected_issues": [],
        },
    },
    "traps": {
        "T1": {"file": "PDS_V-102_L1.xlsx", "key": "operating_pressure",
               "kind": "unit_conversion", "expect_value": 1.0, "expect_unit": "MPa(g)",
               "detail": "145 psig on a bar sheet -> 1.0 MPa(g)"},
        "T2": {"file": "PDS_V-107_L3.txt", "key": "design_pressure",
               "kind": "unit_conversion", "expect_value": 0.99868, "expect_unit": "MPa(g)",
               "detail": "11.0 bara -> gauge by subtracting 0.101325 MPa, AMBER note"},
        "T3": {"file": "PDS_V-103_L1.xlsx", "key": "operating_pressure",
               "kind": "issue", "expect_code": "UNIT_AMBIGUOUS", "expect_severity": "RED",
               "detail": "unitless pressure 8 -> UNIT_AMBIGUOUS, question to process engineer"},
        "T4": {"file": "PDS_V-102_L1.xlsx", "key": "design_pressure",
               "kind": "issue", "expect_code": "CONFLICT", "expect_severity": "RED",
               "detail": "header 10 barg vs remark 8 barg -> CONFLICT, both sources shown"},
        "T5": {"file": "PDS_V-102_L1.xlsx", "key": "corrosion_allowance",
               "kind": "issue", "expect_code": "MISSING", "expect_severity": "RED",
               "detail": "missing corrosion allowance -> MISSING, never defaulted"},
        "T6": {"file": "PDS_V-102_L1.xlsx", "key": "inside_diameter",
               "kind": "unit_conversion", "expect_value": 1219.2, "expect_unit": "mm",
               "detail": "48 in -> 1219.2 mm"},
        "T7": {"file": "PDS_V-102_L1.xlsx", "key": "operating_temperature",
               "kind": "unit_conversion", "expect_value": 100, "expect_unit": "degC",
               "detail": "212 degF -> 100 degC"},
        "T8": {"file": "PDS_V-103_L1.xlsx", "key": "inside_diameter",
               "kind": "issue", "expect_code": "UNIT_AMBIGUOUS", "expect_severity": "AMBER",
               "detail": "'1,200' thousands vs decimal comma -> UNIT_AMBIGUOUS (AMBER)"},
        "T9": {"file": "PDS_V-104_L2.xlsx", "key": "h2s_ppm",
               "kind": "material_rule", "expect_material": "SA-516-70N-HIC",
               "expect_pwht": True, "detail": "H2S 150 ppm -> HIC grade + PWHT flag"},
        "T10": {"file": "PDS_V-104_L2.xlsx", "key": "design_pressure",
                "kind": "issue", "expect_code": "RULE_VIOLATION", "expect_severity": "RED",
                "detail": "design pressure below operating pressure -> RULE_VIOLATION"},
        "T11": {"file": "PDS_V-105_L2.xlsx", "key": "hydrotest_pressure",
                "kind": "issue", "expect_code": "LOW_MATCH", "expect_severity": "AMBER",
                "detail": "unknown label 'Duty Pressure' -> fuzzy LOW_MATCH + alias learning",
                "alias_demo": {"label": "Duty Pressure", "canonical": "operating_pressure"}},
    },
    "vendors": {
        "Vendor A": {
            "R01": "Compliant", "R02": "Compliant", "R03": "Compliant", "R04": "Compliant",
            "R05": "Deviating", "R06": "Compliant", "R07": "Compliant", "R08": "Compliant",
            "R09": "Compliant", "R10": "Compliant", "R11": "Compliant", "R12": "Deviating",
            "R13": "Compliant",
        },
        "Vendor B": {
            "R01": "Compliant", "R02": "Compliant", "R03": "Deviating", "R04": "Deviating",
            "R05": "Compliant", "R06": "Compliant", "R07": "Compliant", "R08": "Compliant",
            "R09": "Compliant", "R10": "Compliant", "R11": "Compliant", "R12": "Compliant",
            "R13": "Compliant",
        },
        "Vendor C": {
            "R01": "Compliant", "R02": "Compliant", "R03": "Unclear", "R04": "Unclear",
            "R05": "Missing", "R06": "Unclear", "R07": "Missing", "R08": "Unclear",
            "R09": "Unclear", "R10": "Missing", "R11": "Unclear", "R12": "Missing",
            "R13": "Missing",
        },
    },
    "expected_ranking": ["Vendor A", "Vendor B", "Vendor C"],
}


# ----------------------------------------------------------------------- main
def make_pdf():
    """Optional: one PDF PDS so the pdfplumber ingest path has something to chew."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except Exception:
        return None
    EXTRA_DIR.mkdir(parents=True, exist_ok=True)
    path = EXTRA_DIR / "PDS_V-109.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, 275 * mm, "PROCESS DATA SHEET - UNFIRED PRESSURE VESSEL (synthetic)")
    c.setFont("Helvetica", 11)
    lines = [
        "Tag No: V-109",
        "Fluid: Sweet natural gas",
        "Operating pressure: 25 barg",
        "Operating temperature: 45 degC",
        "Design pressure: 30 barg",
        "Design temperature: 65 degC",
        "Inside diameter: 700 mm",
        "Tan to tan length: 2200 mm",
        "Corrosion allowance: 3 mm",
        "Radiography: spot",
    ]
    for i, line in enumerate(lines):
        c.drawString(20 * mm, (265 - 8 * i) * mm, line)
    c.save()
    return path


def main() -> int:
    PDS_DIR.mkdir(parents=True, exist_ok=True)
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    # --- PDS: layout L1 (vertical label | value | unit)
    write_l1(PDS_DIR / "PDS_V-101_L1.xlsx", PDS_V101, "V-101")
    write_l1(PDS_DIR / "PDS_V-102_L1.xlsx", PDS_V102, "V-102")
    write_l1(PDS_DIR / "PDS_V-103_L1.xlsx", PDS_V103, "V-103")

    # --- PDS: layout L2 (header row + one value row)
    l2("PDS_V-104_L2.xlsx", BASE_HEADERS, PDS_V104_VALUES, "V-104")
    l2("PDS_V-105_L2.xlsx", PDS_V105_HEADERS, PDS_V105_VALUES, "V-105")
    l2("PDS_V-106_L2.xlsx", BASE_HEADERS, PDS_V106_VALUES, "V-106")

    # --- PDS: layout L3 (free text)
    write_text(PDS_DIR / "PDS_V-107_L3.txt", PDS_V107)
    write_text(PDS_DIR / "PDS_V-108_L3.txt", PDS_V108)

    # --- vendor offers
    write_l2(VENDOR_DIR / "Vendor_A.xlsx", VENDOR_HEADERS, VENDOR_A, "Vendor A")
    write_l2(VENDOR_DIR / "Vendor_B.xlsx", VENDOR_HEADERS, VENDOR_B, "Vendor B")
    write_l2(VENDOR_DIR / "Vendor_C.xlsx", VENDOR_HEADERS, VENDOR_C, "Vendor C")

    # --- ground truth + template + optional PDF
    gt_path = ROOT / "data" / "ground_truth.json"
    gt_path.write_text(json.dumps(GROUND_TRUTH, indent=2), encoding="utf-8")
    tpl = write_mds_template()
    pdf = make_pdf()

    print("PDS files      :", len(list(PDS_DIR.glob('*'))), "->", PDS_DIR)
    print("Vendor offers  :", len(list(VENDOR_DIR.glob('*.xlsx'))), "->", VENDOR_DIR)
    print("Ground truth   :", gt_path)
    print("MDS template   :", tpl)
    print("Optional PDF   :", pdf or "reportlab not installed - skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
