# Definition of Done — SpecForge (prototype submission)

Run everything offline, no API key:

```bash
pip install -r requirements.txt
python data/generate_synthetic.py      # regenerate corpus (already committed)
pytest                                 # 24 unit tests incl. the golden case
python tests/smoke_pages.py            # all 7 pages render headlessly
python tests/flow_check.py             # resolve → learn → approve → export → reply loop
streamlit run app.py
```

## Non-negotiables

| # | Requirement | Where |
|---|---|---|
| 1 | LLM never calculates / picks / classifies | `engine/calculator.py`, `compare.py`, `tbe.py` are pure code; LLM only in `engine/llm.py` (wording + messy text) |
| 2 | Grounding check on every LLM value | `engine/llm.py::grounding_check` → `rejected_ungrounded` audit row |
| 3 | LLM OFF by default, warning when ON | sidebar toggle, `config.LLM_ENABLED_DEFAULT`, `st.warning` |
| 4 | No silent defaults | `engine/validate.py` → `MISSING` 🔴 + question; `mds.py` → `BLOCKED: needs <field>` |
| 5 | Provenance on every field | `models.Provenance(source_file, locator, raw_text)` + `confidence`, `method` — Evidence metric **Ungrounded values = 0** |
| 6 | Human approval gate + logged overrides | `state.approve_mds`, `state.override_red`, `resolve_issue` → `audit(actor, action, payload)` |
| 7 | Tamper-evident audit log | `db.verify_chain` + Evidence → *Tamper demo* |
| 8 | Synthetic data only | `data/generate_synthetic.py` (8 PDS, 3 offers, ground truth) |
| 9 | Honest scope disclaimer | `config.PROTOTYPE_FOOTER` on every page + "CONFIRM WITH EXPERT" notes |
| 10 | One equipment category | unfired pressure vessel, ASME VIII-1 |

## Phase acceptance (1–7)

| Phase | Accepted when |
|---|---|
| 1 · Shell | `streamlit run app.py` — nav, theme, sidebar (load demo, LLM toggle, gate slider), footer |
| 2 · Inputs & extraction | 3 layouts (L1/L2/L3) + PDF/CSV parsed with `Sheet!Cell` / `txt:line` locators; provenance table; issues panel; donut |
| 3 · Review & approve | source highlight follows the focused value; Accept / Edit / Mark unknown; RED → question + value/reason; alias learning; approve blocks on open 🔴 |
| 4 · MDS draft | deterministic rows with formula trace; `BLOCKED` on 🔴 inputs; Excel export with cell comments |
| 5 · Vendor compare | heatmap, deviation register export, clarification questions + simulated replies re-score |
| 6 · TBE | configurable weights/points, ranking, radar, what-if, robustness %, Excel export |
| 7 · Evidence | live metrics vs `ground_truth.json`, audit chain + tamper demo, time study, architecture, real feedback |

## Quality bars

* Golden calculation asserted: `P_design = 1.0 MPa(g)`, `R = 603`, `t = 5.17`, `t+CA = 8.17`,
  selected `10 mm`, `hydrotest = 1.3 MPa(g)` → `tests/test_calculator.py`
* 11 seeded traps (T1–T11) all detected on first run — Evidence → *Trap-by-trap status*
* Field extraction ≥ 95 %, unit normalisation 100 %, trap recall/precision 100 %,
  ungrounded = 0, compliance F1 = 1.0 (39 vendor×requirement verdicts)
* 9 screenshots in `docs/screenshots/`
* Runs with no network and no `ANTHROPIC_API_KEY`

## Known prototype limits (stated honestly)

* Rules/materials are demo values — **CONFIRM WITH EXPERT**; not a certified design tool.
* One equipment category (unfired pressure vessel); shell-thickness formula is UG-27(c)(1) only.
* Vendor replies are simulated inside the app (the loop is real, the vendor is not).
* Time study and feedback start empty — enter real measurements/tester ratings during the demo.
