"""Shared session state + the demo-project loader (the app's "pipeline")."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import streamlit as st
import yaml

import config
import db
from engine.extract import extract, extract_offer, load_aliases
from engine.gate import gate_fields
from engine.ingest import Document, ingest
from engine.mds import build_mds, mds_map
from engine.compare import compare_all
from engine.validate import validate


@st.cache_resource
def get_conn():
    return db.connect()


def rules_vessel() -> dict:
    return yaml.safe_load(config.RULES_VESSEL.read_text(encoding="utf-8"))


def rules_materials() -> dict:
    return yaml.safe_load(config.RULES_MATERIALS.read_text(encoding="utf-8"))


def rules_requirements() -> List[dict]:
    return (yaml.safe_load(config.RULES_REQUIREMENTS.read_text(encoding="utf-8"))
            or {}).get("requirements", [])


def thr() -> Dict[str, float]:
    return {"green": st.session_state.get("gate_green", config.GATE_THRESHOLDS["green"]),
            "amber": st.session_state.get("gate_gate_amber", config.GATE_THRESHOLDS["amber"])}


def init_state() -> None:
    s = st.session_state
    s.setdefault("docs", {})             # fname -> Document
    s.setdefault("extractions", {})      # fname -> Extraction
    s.setdefault("offers", {})           # vendor -> {key: Candidate}
    s.setdefault("vendor_names", [])
    s.setdefault("active", "")
    s.setdefault("mds_rows", None)
    s.setdefault("mds_status", "DRAFT")
    s.setdefault("mds_version", 0)
    s.setdefault("results", [])
    s.setdefault("accepted", {})         # fname -> set(keys)
    s.setdefault("overrides", {})        # fname -> {key: reason}
    s.setdefault("baseline", {})
    s.setdefault("llm_on", False)
    s.setdefault("gate_green", config.GATE_THRESHOLDS["green"])
    s.setdefault("audit_ready", False)
    s.setdefault("last_run", "")


def pds_files() -> List[Path]:
    return sorted(config.PDS_DIR.glob("*.xlsx")) + sorted(config.PDS_DIR.glob("*.txt"))


def vendor_files() -> List[Path]:
    return sorted(config.VENDOR_DIR.glob("*.xlsx"))


def run_pipeline(files: List[Path], vendors, conn) -> None:
    """Document parser -> extractor -> normalizer -> provenance -> validate -> gate."""
    aliases = load_aliases()
    base = st.session_state.setdefault("baseline", {})
    for p in files:
        doc = ingest(p)
        st.session_state["docs"][doc.source_file] = doc
        ext = extract(doc, aliases, llm_enabled=st.session_state.get("llm_on", False),
                      audit_cb=lambda a, pl: db.audit(conn, "llm", a, pl))
        validate(ext, rules_vessel())
        gate_fields(ext.fields, ext.issues, thr())
        st.session_state["extractions"][doc.source_file] = ext
        # accumulate a baseline: what extraction caught at least once (evidence stays
        # honest even after an engineer resolves a trap or teaches an alias)
        b = base.setdefault(doc.source_file, {"issues": set(), "fields": set()})
        b["issues"] |= {(i.key, i.code, i.severity) for i in ext.issues}
        b["fields"] |= {(k, f.value, f.unit) for k, f in ext.fields.items()
                        if f.value is not None}
    if vendors is not None:
        st.session_state["offers"] = {}
        st.session_state["vendor_names"] = []
        for p in vendors:
            doc = ingest(p)
            vendor = p.stem.replace("_", " ")
            st.session_state["offers"][vendor] = extract_offer(doc, aliases)
            st.session_state["vendor_names"].append(vendor)
    if not st.session_state["active"] or \
            st.session_state["active"] not in st.session_state["extractions"]:
        st.session_state["active"] = next(iter(st.session_state["extractions"]), "")
    rebuild_mds()
    run_compare()
    st.session_state["last_run"] = "ok"


def load_sample_project() -> None:
    conn = get_conn()
    st.session_state["baseline"] = {}
    run_pipeline(pds_files(), vendor_files(), conn)
    db.audit(conn, "engineer", "load_demo_project",
             {"pds": len(st.session_state["docs"]), "vendors": st.session_state["vendor_names"]})
    st.session_state["accepted"] = {f: set() for f in st.session_state["extractions"]}
    st.session_state["overrides"] = {}
    st.session_state["mds_status"] = "DRAFT"
    st.toast("Demo project loaded: 8 PDS + 3 vendor offers", icon="✅")


def active_extraction():
    return st.session_state["extractions"].get(st.session_state["active"])


def active_doc() -> Document | None:
    return st.session_state["docs"].get(st.session_state["active"])


def rebuild_mds() -> None:
    ext = active_extraction()
    if ext is None:
        st.session_state["mds_rows"] = None
        return
    st.session_state["mds_rows"] = build_mds(ext.fields, rules_vessel(), rules_materials())


def run_compare() -> None:
    rows = st.session_state.get("mds_rows")
    if not rows:
        st.session_state["results"] = []
        return
    conn = get_conn()
    replies = db.get_replies(conn)
    st.session_state["results"] = compare_all(rules_requirements(), mds_map(rows),
                                              st.session_state["offers"], replies)


def regate_all() -> None:
    """Re-apply the confidence gate with the current sidebar thresholds (live lanes)."""
    t = thr()
    for ext in st.session_state.get("extractions", {}).values():
        gate_fields(ext.fields, ext.issues, t)


def lane_counts_all() -> Dict[str, int]:
    counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for ext in st.session_state["extractions"].values():
        for f in ext.fields.values():
            counts[f.status] += 1
        for i in ext.issues:
            if i.severity == "RED" and i.key not in ext.fields:
                counts["RED"] += 1
    return counts


def open_reds(ext) -> List:
    return [i for i in ext.issues if i.severity == "RED"]


def resolve_issue(fname: str, key: str, value: str, reason: str, actor: str = "engineer") -> None:
    """Engineer enters a value + reason for a RED item -> engineer_edit (logged)."""
    ext = st.session_state["extractions"][fname]
    from engine.extract import load_aliases as _la
    from engine.normalize import normalize_value
    from models import FieldValue, Provenance
    from engine.extract import map_label, alias_pairs
    pairs = alias_pairs(_la())
    mapped, conf, _ = map_label(key.replace("_", " "), pairs)
    mapped = mapped or key
    raw = str(value).strip()
    # value may carry its unit, e.g. "3 mm"
    from engine.ingest import parse_value_unit_full
    num, unit, notes, _amb = parse_value_unit_full(raw)
    val, canon_unit, n2, iss = normalize_value(mapped, num if num is not None else raw,
                                               unit, f"engineer:{actor}")
    fld = FieldValue(
        key=mapped, value=val if val is not None else raw, unit=canon_unit,
        prov=Provenance(source_file=fname, locator=f"engineer:{actor}",
                        raw_text=f"{raw} — reason: {reason}"),
        confidence=1.0, method="engineer_edit",
        notes=[f"engineer edit: {reason}"] + notes + n2, label=key.replace("_", " "),
        needs_review=False,
    )
    ext.fields[mapped] = fld
    # the issue is now answered
    ext.issues = [i for i in ext.issues if not (i.key == mapped and i.severity == "RED")]
    gate_fields(ext.fields, ext.issues, thr())
    rebuild_mds()
    run_compare()
    db.audit(get_conn(), actor, "engineer_edit",
             {"file": fname, "key": mapped, "value": raw, "reason": reason})
    st.toast(f"Logged engineer edit: {key} = {raw}", icon="✏️")


def override_red(fname: str, key: str, reason: str, actor: str = "engineer") -> None:
    st.session_state.setdefault("overrides", {}).setdefault(fname, {})[key] = reason
    ext = st.session_state["extractions"][fname]
    ext.issues = [i for i in ext.issues if not (i.key == key and i.severity == "RED")]
    gate_fields(ext.fields, ext.issues, thr())
    rebuild_mds()
    db.audit(get_conn(), actor, "override_open_red", {"file": fname, "key": key, "reason": reason})
    st.toast("Override logged — approval will reference it", icon="⚠️")


def accept_field(fname: str, key: str) -> None:
    st.session_state["accepted"].setdefault(fname, set()).add(key)


def mark_unknown(fname: str, key: str, reason: str = "") -> None:
    """Engineer says 'this value is not on the sheet' -> RED, no default, ever."""
    ext = st.session_state["extractions"][fname]
    ext.fields.pop(key, None)
    if not any(i.key == key and i.code == "MISSING" for i in ext.issues):
        from models import Issue
        ext.issues.append(Issue(
            code="MISSING", key=key, severity="RED",
            message=f"'{key}' marked unknown by the engineer on {fname}.",
            question=f"'{key.replace('_', ' ')}' is not stated on the sheet — please confirm "
                     f"the required value with the process engineer."))
    rebuild_mds()
    db.audit(get_conn(), "engineer", "mark_unknown",
             {"file": fname, "key": key, "reason": reason})
    st.toast("Marked unknown — no default applied", icon="🚫")


def export_with_audit(rows, out):
    from engine.mds import export_mds
    path = export_mds(rows, config.MDS_TEMPLATE, out)
    db.audit(get_conn(), "engineer", "export_mds",
             {"file": Path(path).name, "version": st.session_state.get("mds_version", 0)})
    return path


def teach_and_rerun(label: str, key: str, fname: str) -> None:
    """Alias learning: applied to this sheet and every future sheet."""
    from engine.extract import teach_alias, load_aliases, extract
    new = teach_alias(label, key)
    doc = st.session_state["docs"][fname]
    ext = extract(doc, load_aliases(),
                  llm_enabled=st.session_state.get("llm_on", False))
    validate(ext, rules_vessel())
    gate_fields(ext.fields, ext.issues, thr())
    st.session_state["extractions"][fname] = ext
    rebuild_mds()
    run_compare()
    db.audit(get_conn(), "engineer", "learn_alias",
             {"label": label, "canonical": key, "new": new, "file": fname})
    st.toast(f"Learned: '{label}' → {key}. Applies to future sheets.", icon="🧠")


def approve_mds(actor: str = "engineer") -> bool:
    ext = active_extraction()
    if ext is None:
        return False
    reds = [i for i in ext.issues if i.severity == "RED"]
    overrides = st.session_state.get("overrides", {}).get(st.session_state["active"], {})
    if any(i.key not in overrides for i in reds):
        st.error("Open 🔴 items remain. Resolve them or write an override reason first.")
        return False
    st.session_state["mds_status"] = "APPROVED"
    st.session_state["mds_version"] = int(st.session_state.get("mds_version", 0)) + 1
    db.audit(get_conn(), actor, "approve_mds",
             {"file": st.session_state["active"],
              "version": st.session_state["mds_version"],
              "overrides": overrides})
    st.toast(f"MDS v{st.session_state['mds_version']} APPROVED and locked", icon="🔒")
    return True
