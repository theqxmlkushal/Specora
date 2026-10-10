"""Configurable TBE scoring, what-if and rank robustness."""
from __future__ import annotations

from typing import Dict, List

import config
from models import ReqResult


def score(results: List[ReqResult], points: Dict[str, float] | None = None,
          cat_weights: Dict[str, int] | None = None) -> Dict:
    points = dict(points or config.POINTS)
    cat_weights = dict(cat_weights or config.CATEGORY_WEIGHTS)
    by_vendor: Dict[str, List[ReqResult]] = {}
    for r in results:
        by_vendor.setdefault(r.vendor, []).append(r)

    out = {"vendors": {}, "points": points, "cat_weights": cat_weights}
    for vendor, rs in by_vendor.items():
        cats: Dict[str, dict] = {}
        for r in rs:
            c = cats.setdefault(r.category, {"num": 0.0, "den": 0.0, "items": []})
            p = points.get(r.verdict, 0.0)
            c["num"] += p * r.weight
            c["den"] += r.weight
            c["items"].append((r.req_id, r.verdict, p, r.weight, r.critical))
        total, detail = 0.0, {}
        for cat, c in cats.items():
            cs = (c["num"] / c["den"]) if c["den"] else 0.0
            w = cat_weights.get(cat, 0)
            detail[cat] = {"score": round(cs * 100, 1), "weight": w,
                           "contribution": round(cs * w, 2),
                           "items": c["items"]}
            total += cs * w
        blocking = [r for r in rs
                    if r.critical and r.verdict in ("Deviating", "Missing")]
        out["vendors"][vendor] = {
            "total": round(total, 2),
            "categories": detail,
            "blocking": [f"{r.req_id} {r.key}" for r in blocking],
            "acceptable": not blocking,
            "open_clarifications": [r.req_id for r in rs if r.verdict in ("Unclear", "Missing")],
        }
    ranked = sorted(out["vendors"], key=lambda v: -out["vendors"][v]["total"])
    out["ranking"] = ranked
    return out


def what_if(results: List[ReqResult], points=None, cat_weights=None) -> Dict:
    """Assume open clarifications (Unclear) resolve favourably.

    Items that were never offered (Missing) are not a pending clarification and
    stay at their score, so the what-if can never flatter an incomplete bid.
    """
    pts = dict(points or config.POINTS)
    pts["Unclear"] = 1.0
    return score(results, pts, cat_weights)


def robustness(results: List[ReqResult], points=None, cat_weights=None,
               trials: int | None = None, perturb: float | None = None,
               seed: int | None = None) -> Dict:
    """Perturb category weights +-20% N times; report how often each vendor is #1."""
    import numpy as np
    trials = trials or config.ROBUSTNESS_TRIALS
    perturb = perturb if perturb is not None else config.ROBUSTNESS_PERTURB
    seed = seed if seed is not None else config.ROBUSTNESS_SEED
    base = dict(cat_weights or config.CATEGORY_WEIGHTS)
    cats = list(base)
    arr = np.array([base[c] for c in cats], dtype=float)
    rng = np.random.default_rng(seed)
    wins = {r.vendor: 0 for r in results}
    wins = {v: 0 for v in {r.vendor for r in results}}
    for _ in range(trials):
        w = arr * (1 + rng.uniform(-perturb, perturb, size=len(arr)))
        w = w / w.sum()
        cw = {c: float(w[i] * 100) for i, c in enumerate(cats)}
        s = score(results, points, cw)
        if s["ranking"]:
            wins[s["ranking"][0]] += 1
    return {"trials": trials, "perturb": perturb,
            "pct": {v: round(n / trials * 100, 1) for v, n in wins.items()}}


def export_tbe(out_path, results: List[ReqResult], sc: Dict, rob: Dict | None,
               whatif_sc: Dict | None) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "TBE"
    ws.append(["TECHNICAL BID EVALUATION — SpecForge (prototype)"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["Scoring points"] + [f"{k}={v}" for k, v in sc["points"].items()])
    ws.append(["Category weights"] + [f"{k}={v}" for k, v in sc["cat_weights"].items()])
    ws.append([])
    ws.append(["Rank", "Vendor", "Score /100", "Technically acceptable", "Blocking items"])
    for c in ws[6]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3B63")
    for i, v in enumerate(sc["ranking"], start=1):
        d = sc["vendors"][v]
        ws.append([i, v, d["total"], "Yes" if d["acceptable"] else "No — pending clarification",
                   ", ".join(d["blocking"]) or "—"])
    ws.append([])
    if whatif_sc:
        ws.append(["What-if (open clarifications resolve favourably)"])
        for v in whatif_sc["ranking"]:
            ws.append(["", v, whatif_sc["vendors"][v]["total"]])
        ws.append([])
    if rob:
        ws.append([f"Rank robustness ({rob['trials']} trials, weights perturbed "
                   f"±{int(rob['perturb']*100)}%)"])
        for v, p in rob["pct"].items():
            ws.append(["", v, f"{p}% first place"])
        ws.append([])
    ws.append(["Requirement detail"])
    hdr = ["Vendor", "Req", "Key", "Category", "Source", "Critical", "Weight",
           "Required", "Offered", "Verdict", "Explanation"]
    ws.append(hdr)
    start = ws.max_row
    for c in ws[start]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3B63")
    for r in results:
        ws.append([r.vendor, r.req_id, r.key, r.category, r.source,
                   "Yes" if r.critical else "No", r.weight, r.required, r.offered,
                   r.verdict, r.explanation])
    for col, width in zip("ABCDEFGHIJK", (12, 8, 22, 20, 14, 10, 8, 24, 24, 13, 62)):
        ws.column_dimensions[col].width = width
    wb.save(str(out_path))
    return str(out_path)
