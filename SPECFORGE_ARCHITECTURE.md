# SpecForge — Architecture

**Process Data Sheet (PDS) → Mechanical Data Sheet (MDS) → auditable vendor bid evaluation**

The lane layout mirrors the reference image in the problem statement (layout only — every
block below is SpecForge's own content):

```
┌──────────────┐   ┌─────────────────────────┐   ┌──────────────────────────┐
│ User inputs  │   │ Pre-processing modules  │   │ Unified engine           │
│ · PDS Excel  │──▶│ · Document parser       │──▶│ · rules (YAML)           │
│ · PDS PDF/txt│   │ · Field extractor       │   │ · deterministic calc     │
│ · Vendor offer│  │ · Unit normalizer       │   │ · requirement comparator │
│ · Ref pack   │   │ · Provenance tagger     │   │                          │
│   (template, │   │ · Conflict/missing chk  │   │                          │
│    rules,    │   └─────────────────────────┘   └────────────┬─────────────┘
│    materials)│                                              │
└──────────────┘                                              ▼
                                        ┌──────────────────────────────────┐
                                        │ Decision gate                    │
                                        │ Confidence & compliance gate     │
                                        └────────────┬─────────────────────┘
                     ┌───────────────────────────────┼───────────────────────────────┐
                     ▼                               ▼                               ▼
        🟢 Auto-fill / Compliant      🟡 Engineer review / unclear        🔴 Clarify & block
        · accepted by the engineer    · converted units, fuzzy match       · missing / conflicting
        · MDS row computed            · derived with assumption            · MDS rows BLOCKED
                     │                               │                               │
                     └───────────────────────────────┼───────────────────────────────┘
                                                     ▼
                                        ┌──────────────────────────────────┐
                                        │ Closed loop                     │
                                        │ · engineer approval (human gate) │
                                        │ · vendor replies → re-classify   │
                                        │ · TBE re-scoring + robustness    │
                                        │ · alias & rule learning          │
                                        │ · tamper-evident audit log       │
                                        └──────────────────────────────────┘
```

## Responsibility split ("AI done responsibly")

| Step | Owner | LLM allowed? |
|---|---|---|
| Read cells/lines with locators | `engine/ingest.py` | never |
| Label → canonical key | `engine/extract.py` (alias + rapidfuzz) | only for messy text, then grounding-checked |
| Unit conversion | `engine/normalize.py` | never |
| Design maths | `engine/calculator.py` | never |
| Missing / conflict / rule checks | `engine/validate.py` | never |
| GREEN/AMBER/RED classification | `engine/gate.py` | never |
| Requirement verdict | `engine/compare.py` | never (wording only) |
| Scoring, ranking, robustness | `engine/tbe.py` | never |
| Approval | **human** | — |

## Data flow contracts

`Cell(text, locator)` → `Candidate(key, raw_value, raw_unit, locator)` →
`FieldValue(value, unit, prov, confidence, method, notes, status)` →
`MdsRow(value, method, trace, blocked_by)` → `ReqResult(verdict, explanation, question)` →
`TBE score / rank`.

Every `FieldValue` carries `Provenance(source_file, locator, raw_text)`. A value without a
source pointer is rejected — `Ungrounded values` on the Evidence page must read **0**.

## Storage

* SQLite (`specforge.db`): hash-chained `audit`, `feedback`, `time_study`, vendor `replies`.
* `rules/*.yaml`: vessel rules, materials, aliases (grows via alias learning), requirements,
  enquiry clauses.
* `data/ground_truth.json`: canonical values, the 11 seeded traps, expected vendor verdicts.
