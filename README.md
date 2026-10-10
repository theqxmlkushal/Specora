# SpecForge

**Process Data Sheet → Mechanical Data Sheet → auditable vendor-bid evaluation.**

> *"SpecForge turns a Process Data Sheet into an engineer-approved Mechanical Data Sheet and an
> auditable vendor-bid evaluation, where every value is traceable to its source, every number
> comes from deterministic code, and AI is never allowed to invent data."*

Prototype for the L&T manufacturing hackathon, problem statement #6 —
*Automation from Process Data Sheet to Mechanical Data Sheet*.
**Prototype using synthetic data. Not a certified design tool. Engineer approval required.**

## Run it

```bash
pip install -r requirements.txt
python data/generate_synthetic.py     # regenerate the synthetic corpus (already committed)
streamlit run app.py
```

No API key, no internet required. Everything works offline; the LLM toggle is OFF by default.

## The 7 pages

| Page | What it proves |
|---|---|
| **Command Center** | live KPIs, the 6-step pipeline, 🟢🟡🔴 lanes |
| **Inputs & Extraction** | 3 PDS layouts + vendor offers, provenance table, issues panel, donut |
| **Review & Approve** | side-by-side source highlight, Accept / Edit / Mark unknown, alias learning, approval gate |
| **MDS Draft** | formula traces, `BLOCKED` rows, Excel export |
| **Vendor Compare** | heatmap, deviation register, clarification questions + simulated replies |
| **TBE & What-if** | weight sliders, ranking, radar, rank robustness, Excel export |
| **Evidence** | live metrics vs ground truth, audit chain + tamper demo, time study, real feedback |

## Principles (non-negotiable)

1. The LLM never calculates, never picks values, never classifies compliance.
2. Grounding check: an LLM value must appear verbatim in the source span, else `rejected_ungrounded`.
3. No silent defaults — a missing corrosion allowance becomes 🔴 with a clarification question.
4. Every field carries provenance: `value, unit, source_file, locator, raw_text, confidence, method`.
5. Human approval gate; open 🔴 items need a written override reason.
6. Tamper-evident audit log (SHA-256 hash chain).
7. Synthetic / sanitized documents only; LLM OFF by default with a visible warning.
8. One equipment category; demo rule values flagged `CONFIRM WITH EXPERT`.

## Seeded traps (T1–T11)

| ID | Trap | Expected behaviour |
|---|---|---|
| T1 | `145 psig` on a bar sheet | → 1.0 MPa(g) with a note |
| T2 | `11.0 bara` | → gauge (−0.101325 MPa), 🟡 note |
| T3 | unitless `8` | `UNIT_AMBIGUOUS` 🔴 + question |
| T4 | 8 barg vs 10 barg | `CONFLICT` 🔴, both sources shown |
| T5 | missing corrosion allowance | `MISSING` 🔴, never defaulted |
| T6 | `48 in` | → 1219.2 mm |
| T7 | `212 °F` | → 100 °C |
| T8 | `1,200` | `UNIT_AMBIGUOUS` 🟡 |
| T9 | H2S 150 ppm | HIC grade + PWHT flag |
| T10 | design < operating | `RULE_VIOLATION` 🔴 |
| T11 | unknown "Duty Pressure" | fuzzy 🟡 `LOW_MATCH` + alias learning |

## Golden calculation (asserted in `tests/test_calculator.py`)

`P_op = 8 bar(g)`, `ID = 1200 mm`, `S = 138 MPa`, `E = 0.85`, `CA = 3 mm`
→ `P_design = 1.0 MPa(g)`, `R = 603 mm`, `t ≈ 5.17 mm`, `t+CA ≈ 8.17 mm`,
selected **10 mm**, `hydrotest = 1.3 MPa(g) = 13 bar(g)`.

## Tests

```bash
pytest            # 24 tests: golden case, unit conversions, gauge/absolute,
                  # decimal comma, comparator operators, scoring
```

## Layout

```
app.py config.py models.py db.py styles.py state.py
rules/   vessel_rules · materials · aliases · requirements · enquiry
engine/  ingest extract normalize validate calculator mds gate compare tbe llm evaluate
views/   command_center inputs_extract review mds_draft vendor_compare tbe evidence
data/    generate_synthetic.py  pds/  vendor/  ground_truth.json  extra/
templates/  MDS_template.xlsx
tests/   test_calculator.py test_normalize.py test_compare.py
```

## 90-second demo

1. **Command Center** → *Load demo project*.
2. **Inputs & Extraction** → *Run extraction* → donut + issues (psi, gauge/abs, conflict, missing CA).
3. **Review** → highlight the source cell → resolve the conflict with a reason → teach
   "Duty Pressure" → **Approve MDS**.
4. **MDS Draft** → formula trace + golden calculation → export Excel.
5. **Vendor Compare** → heatmap → Vendor B's critical deviations → simulate Vendor C's reply.
6. **TBE** → drag a weight slider, ranking moves → robustness %.
7. **Evidence** → metrics, `Chain valid ✅`, feedback cards.
