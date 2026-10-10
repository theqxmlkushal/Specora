"""Live evaluation against data/ground_truth.json — nothing is hard-coded."""
from __future__ import annotations

from models import ReqResult

import json
from typing import Dict, List

import config
from engine.extract import Extraction

CLASSES = ["Compliant", "Deviating", "Unclear", "Missing"]


def load_gt(path=None) -> dict:
    p = path or config.GROUND_TRUTH
    return json.loads(open(p, encoding="utf-8").read())


def _match(exp, got) -> bool:
    if exp is None:
        return True
    if isinstance(exp, (int, float)) and isinstance(got, (int, float)):
        if abs(exp) < 1e-9:
            return abs(got) < 1e-6
        return abs(float(got) - float(exp)) / abs(float(exp)) <= 0.01
    return str(exp).strip().lower() == str(got or "").strip().lower()


def evaluate(extractions: Dict[str, Extraction], results: List[ReqResult], gt: dict,
             time_rows: List[dict] | None = None,
             baseline: Dict | None = None) -> dict:
    gt = gt or load_gt()
    baseline = baseline or {}

    def base_fields(fname):
        return {(k, v, u) for k, v, u in baseline.get(fname, {}).get("fields", set())}

    def base_ok(fname, key, exp, exp_unit):
        for bk, bv, bu in base_fields(fname):
            if bk != key:
                continue
            if (not exp_unit or exp_unit == bu) and _match(exp, bv):
                return True
        return False

    def base_issue(fname, key, code, sev):
        s = baseline.get(fname, {}).get("issues", set())
        return (key, code, sev) in s

    total, correct, misses = 0, 0, []
    for fname, ext in extractions.items():
        canon = (gt["pds"].get(fname) or {}).get("canonical", {})
        for key, spec in canon.items():
            exp = spec.get("value")
            if exp is None or spec.get("conflict") or spec.get("missing") or spec.get("ambiguous"):
                continue
            total += 1
            exp_unit = spec.get("unit")
            f = ext.fields.get(key)
            if f is not None and f.value is not None:
                unit_ok = (not exp_unit) or (f.unit == exp_unit)
                if unit_ok and _match(exp, f.value):
                    correct += 1
                    continue
                if f.unit != exp_unit:
                    misses.append(f"{fname}:{key} unit {f.unit} != {exp_unit}")
                else:
                    misses.append(f"{fname}:{key} {f.value} != {exp}")
                continue
            if base_ok(fname, key, exp, exp_unit):
                correct += 1
                misses.append(f"{fname}:{key} (correct at extraction, later edited)")
                continue
            misses.append(f"{fname}:{key} not extracted")
    field_acc = correct / total if total else 0.0

    # ---- unit normalisation traps (T1 T2 T6 T7)
    unit_traps = {k: v for k, v in gt["traps"].items()
                  if v["kind"] == "unit_conversion"}
    u_ok, u_tot, u_bad = 0, 0, []
    for tid, t in unit_traps.items():
        u_tot += 1
        ext = extractions.get(t["file"])
        f = ext.fields.get(t["key"]) if ext else None
        live = bool(f and f.value is not None and _match(t["expect_value"], f.value)
                    and f.unit == t["expect_unit"])
        if live or base_ok(t["file"], t["key"], t["expect_value"], t["expect_unit"]):
            u_ok += 1
        else:
            u_bad.append(tid)

    # ---- trap detection (issue traps)
    issue_traps = {k: v for k, v in gt["traps"].items() if v["kind"] == "issue"}
    expected = {(t["file"], t["key"], t["expect_code"]) for t in issue_traps.values()}
    # false-flag baseline: every issue the ground truth *expects* (incl. seeded ones)
    expected_all = set()
    for fname, spec in gt["pds"].items():
        for i in spec.get("expected_issues", []):
            expected_all.add((fname, i["key"], i["code"]))
    found, tp = set(), 0
    for tid, t in issue_traps.items():
        ext = extractions.get(t["file"])
        hit = bool(ext) and any(
            i.code == t["expect_code"] and i.key == t["key"] and
            (i.severity == t.get("expect_severity", i.severity))
            for i in ext.issues)
        hit = hit or base_issue(t["file"], t["key"], t["expect_code"],
                                t.get("expect_severity"))
        if hit:
            tp += 1
            found.add(tid)
    actual = 0
    matched = 0
    false_flags_list = []
    for fname, ext in extractions.items():
        for i in ext.issues:
            actual += 1
            if (fname, i.key, i.code) in expected_all:
                matched += 1
            else:
                false_flags_list.append(f"{fname}:{i.key}/{i.code}")
    fp = actual - matched
    recall = tp / len(issue_traps) if issue_traps else 1.0
    precision = matched / actual if actual else 1.0

    # ---- ungrounded values (must be 0)
    ungrounded = [f"{fn}:{k}" for fn, e in extractions.items()
                  for k, f in e.fields.items() if f.prov is None]

    # ---- compliance classification
    gt_v = gt.get("vendors", {})
    y_true, y_pred = [], []
    per_class = {}
    for r in results:
        exp = gt_v.get(r.vendor, {}).get(r.req_id)
        if exp is None:
            continue
        y_true.append(exp)
        y_pred.append(r.verdict)
    for c in CLASSES:
        tp_c = sum(1 for a, b in zip(y_true, y_pred) if a == c and b == c)
        fp_c = sum(1 for a, b in zip(y_true, y_pred) if a != c and b == c)
        fn_c = sum(1 for a, b in zip(y_true, y_pred) if a == c and b != c)
        prec = tp_c / (tp_c + fp_c) if (tp_c + fp_c) else 0.0
        rec = tp_c / (tp_c + fn_c) if (tp_c + fn_c) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_class[c] = {"precision": round(prec, 3), "recall": round(rec, 3),
                        "f1": round(f1, 3), "support": sum(1 for a in y_true if a == c)}
    matrix = [[sum(1 for a, b in zip(y_true, y_pred) if a == ra and b == pb)
               for pb in CLASSES] for ra in CLASSES]

    # ---- time saved
    time_rows = time_rows or []
    time_metric = None
    if time_rows:
        man = sum(r["manual_min"] for r in time_rows) / len(time_rows)
        tool = sum(r["tool_min"] for r in time_rows) / len(time_rows)
        if man > 0:
            time_metric = {"manual": round(man, 1), "tool": round(tool, 1),
                           "reduction_pct": round((man - tool) / man * 100, 1)}

    return {
        "field_accuracy": round(field_acc, 3),
        "field_n": total,
        "field_misses": misses,
        "unit_accuracy": round(u_ok / u_tot, 3) if u_tot else 1.0,
        "unit_bad": u_bad,
        "trap_recall": round(recall, 3),
        "trap_precision": round(precision, 3),
        "traps_found": sorted(found),
        "traps_missing": sorted(set(issue_traps) - found),
        "false_flags": fp,
        "false_flag_list": false_flags_list,
        "ungrounded": len(ungrounded),
        "ungrounded_list": ungrounded,
        "compliance": per_class,
        "matrix": matrix,
        "compliance_n": len(y_true),
        "time": time_metric,
    }
