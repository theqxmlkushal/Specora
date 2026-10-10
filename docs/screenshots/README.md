# Screenshots (9) — capture with `python scripts/make_screenshots.py`

| File | Story |
|---|---|
| `01_command_center.png` | Live KPIs, 6-step pipeline, 🟢🟡🔴 lanes |
| `02_extraction_traps.png` | Provenance table + issues panel + donut over all 8 PDS (traps T1–T11) |
| `03_review_highlight.png` | Side-by-side source cell glowing while its extracted value is reviewed (`PDS_V-102_L1` conflict) |
| `04_mds_formula_trace.png` | Draft MDS with per-row formula traces and `BLOCKED` rows |
| `05_vendor_heatmap.png` | Requirement × vendor verdict heatmap (CODE / ENQUIRY / MDS sources) |
| `06_deviation_register.png` | Filterable deviation register with proposed resolutions |
| `07_clarifications.png` | Clarification questions + simulated vendor replies loop |
| `08_tbe_sliders.png` | Weight sliders, ranking, radar, robustness % |
| `09_evidence.png` | Live metrics vs ground truth, audit chain, time study, feedback |

Regenerate any time:

```bash
streamlit run app.py --server.port 8511
pip install playwright && python -m playwright install chromium
python scripts/make_screenshots.py
```
