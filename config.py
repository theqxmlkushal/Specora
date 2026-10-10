"""Specora configuration: paths, gate thresholds, TBE defaults.

Everything the UI or engine needs that is a *constant* lives here so that
views stay declarative and the engine stays pure.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

RULES_DIR = ROOT / "rules"
DATA_DIR = ROOT / "data"
PDS_DIR = DATA_DIR / "pds"
VENDOR_DIR = DATA_DIR / "vendor"
TEMPLATE_DIR = ROOT / "templates"
MDS_TEMPLATE = TEMPLATE_DIR / "MDS_template.xlsx"
GROUND_TRUTH = DATA_DIR / "ground_truth.json"
DB_PATH = ROOT / "specora.db"

# ---------------------------------------------------------------- rules files
RULES_VESSEL = RULES_DIR / "vessel_rules.yaml"
RULES_MATERIALS = RULES_DIR / "materials.yaml"
RULES_ALIASES = RULES_DIR / "aliases.yaml"
RULES_REQUIREMENTS = RULES_DIR / "requirements.yaml"
RULES_ENQUIRY = RULES_DIR / "enquiry.yaml"

# ---------------------------------------------------------------- gate / match
GATE_THRESHOLDS = {
    "green": 0.85,   # confidence needed for the GREEN lane
    "amber": 0.60,   # below this and above none -> RED-ish handling in UI
}
FUZZY = {"high": 88, "low": 70}   # rapidfuzz ratio bands

# ---------------------------------------------------------------- units / keys
CANONICAL_UNITS = {
    "operating_pressure": "MPa(g)",
    "design_pressure": "MPa(g)",
    "hydrotest_pressure": "MPa(g)",
    "operating_temperature": "degC",
    "design_temperature": "degC",
    "mdmt_c": "degC",
    "inside_diameter": "mm",
    "tan_to_tan_length": "mm",
    "corrosion_allowance": "mm",
    "shell_thickness": "mm",
    "h2s_ppm": "ppm",
}

TEXT_KEYS = {
    "tag_no", "fluid", "radiography", "shell_material", "selected_material",
    "design_code", "pwht", "certificates", "inspection_witness", "painting",
    "delivery_documents",
}

REQUIRED_FIELDS = [
    "tag_no", "fluid", "operating_pressure", "operating_temperature",
    "inside_diameter", "tan_to_tan_length", "corrosion_allowance", "radiography",
]

# ---------------------------------------------------------------- TBE defaults
POINTS = {"Compliant": 1.0, "Unclear": 0.4, "Deviating": 0.2, "Missing": 0.0}

CATEGORY_WEIGHTS = {
    "Design basis": 30,
    "Material": 25,
    "Fabrication & NDE": 15,
    "Testing": 15,
    "Documentation": 15,
}

ROBUSTNESS_TRIALS = 500
ROBUSTNESS_PERTURB = 0.20
ROBUSTNESS_SEED = 42

# ---------------------------------------------------------------- LLM (optional)
def _env_flag(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


LLM_ENABLED_DEFAULT = _env_flag("ENABLE_LLM", "false")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
LLM_HAS_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))

PROTOTYPE_FOOTER = (
    "Prototype using synthetic data. Not a certified design tool. Engineer approval required."
)
APP_TAGLINE = (
    "Process Data Sheet  →  Mechanical Data Sheet  →  auditable vendor bid evaluation"
)
