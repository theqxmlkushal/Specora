"""Field extractor: alias + fuzzy match -> FieldValue (optional LLM, grounding-checked).

Label -> canonical key:
  exact alias          -> confidence 1.00  (GREEN eligible)
  fuzzy ratio >= 88    -> confidence 0.95  (GREEN eligible)
  fuzzy 70..88         -> confidence score (AMBER, LOW_MATCH issue)
  below 70             -> ignored, listed under "Unmapped labels" (alias teaching)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from rapidfuzz import fuzz

import config
from engine.ingest import Document, PAIR_RE, parse_value_unit, parse_value_unit_full
from engine.normalize import normalize_value, parse_number, amb_issue_from
from models import FieldValue, Issue, Provenance

_WORD = lambda s: re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()
_SKIP_INLINE = {"ca", "rt", "id", "tt", "t t", "p op", "t op", "p design", "t design"}


# ------------------------------------------------------------------- aliases
def load_aliases(path: Optional[Path] = None) -> Dict[str, List[str]]:
    p = Path(path or config.RULES_ALIASES)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("aliases", {}) or {}


def alias_pairs(aliases: Dict[str, List[str]]) -> List[Tuple[str, str, str]]:
    """(canonical_key, alias_text, normalized_alias)"""
    out = []
    for key, vals in aliases.items():
        for a in vals:
            out.append((key, str(a), _WORD(a)))
    return out


def teach_alias(label: str, key: str, path: Optional[Path] = None) -> bool:
    """Persist a learned alias (alias learning loop). Returns True if new."""
    p = Path(path or config.RULES_ALIASES)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    aliases = data.setdefault("aliases", {})
    norm = _WORD(label)
    if not norm:
        return False
    existing = [_WORD(x) for x in aliases.get(key, [])]
    if norm in existing:
        return False
    aliases.setdefault(key, []).append(norm)
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return True


def map_label(label: str, pairs) -> Tuple[Optional[str], float, Optional[str]]:
    """-> (key, confidence, match_note)"""
    n = _WORD(label)
    if not n:
        return None, 0.0, None
    for key, raw, na in pairs:
        if n == na:
            return key, 1.0, None
    best_key, best_score, best_raw = None, -1.0, ""
    for key, raw, na in pairs:
        s = fuzz.ratio(n, na) / 100.0
        if s > best_score:
            best_key, best_score, best_raw = key, s, raw
    if best_score * 100 >= config.FUZZY["high"]:
        return best_key, 0.95, f"fuzzy match {best_score*100:.0f}%"
    if best_score * 100 >= config.FUZZY["low"]:
        return best_key, best_score, f"low fuzzy match {best_score*100:.0f}%"
    return None, 0.0, None


# --------------------------------------------------------------- candidates
@dataclass
class Candidate:
    key: str
    label: str
    locator: str
    source_file: str
    raw_text: str                 # exact text at the source (value cell / line)
    raw_value: object = None
    raw_unit: str = ""
    value: object = None          # normalized
    unit: Optional[str] = None
    confidence: float = 1.0
    method: str = "extracted"
    notes: List[str] = field(default_factory=list)
    pre_notes: List[str] = field(default_factory=list)
    pre_amb: Optional[str] = None
    issue: Optional[Issue] = None


@dataclass
class Extraction:
    fields: Dict[str, FieldValue] = field(default_factory=dict)
    candidates: Dict[str, List[Candidate]] = field(default_factory=dict)
    issues: List[Issue] = field(default_factory=list)
    unmapped: List[Dict] = field(default_factory=list)
    doc: Optional[Document] = None


def _candidates_from_doc(doc: Document, pairs) -> Tuple[List[Candidate], List[Dict]]:
    out: List[Candidate] = []
    unmapped: List[Dict] = []

    def add(label, locator, raw_text, raw_value, raw_unit, pre_notes=None, pre_amb=None):
        key, score, note = map_label(label, pairs)
        if key is None:
            if str(label).strip():
                unmapped.append({"label": str(label).strip(), "locator": locator,
                                 "best": "", "score": 0.0})
            return
        out.append(Candidate(key=key, label=str(label).strip(), locator=locator,
                             source_file=doc.source_file, raw_text=str(raw_text),
                             raw_value=raw_value, raw_unit=raw_unit or "",
                             confidence=score, method="extracted",
                             notes=([note] if note else []),
                             pre_notes=list(pre_notes or []), pre_amb=pre_amb))

    if doc.is_text:
        for loc, line in doc.lines:
            m = PAIR_RE.match(line)
            if not m:
                continue
            label, val = m.group("label"), m.group("val")
            num, unit, notes, amb = parse_value_unit_full(val)
            add(label, loc, val, num if num is not None else val, unit, notes, amb)
    else:
        sheet = next(iter(doc.grid))
        rows = doc.grid[sheet]
        if doc.layout == "L2":
            headers = rows[0]
            values = rows[1] if len(rows) > 1 else []
            for i, h in enumerate(headers):
                if not str(h).strip():
                    continue
                v = values[i] if i < len(values) else ""
                if str(v).strip() == "":
                    continue
                num, unit, notes, amb = parse_value_unit_full(v)
                add(h, f"{sheet}!{chr(65+i) if i < 26 else 'A'+chr(65+i-26)}2", v,
                    num if num is not None else v, unit, notes, amb)
        else:
            skip0 = str(rows[0][0]).strip().lower() in ("parameter", "item", "field", "description")
            for r, row in enumerate(rows, start=1):
                if skip0 and r == 1:
                    continue
                label = str(row[0]).strip() if row else ""
                if not label:
                    continue
                val = str(row[1]).strip() if len(row) > 1 else ""
                unit = str(row[2]).strip() if len(row) > 2 else ""
                if val == "":
                    continue
                num, u2, notes, amb = parse_value_unit_full(val)
                add(label, f"{sheet}!B{r}", val, num if num is not None else val,
                    unit or u2, notes, amb)

    # ---- inline free-text scan (e.g. "Design pressure as per process note: 8 barg")
    inline = _inline_scan(doc, pairs)
    seen = {(c.key, c.locator) for c in out}
    for c in inline:
        if (c.key, c.locator) not in seen:
            out.append(c)
            seen.add((c.key, c.locator))
    return out, unmapped


def _inline_scan(doc: Document, pairs) -> List[Candidate]:
    from config import CANONICAL_UNITS
    numeric_keys = {k for k in CANONICAL_UNITS}
    pats = []
    for key, raw, na in pairs:
        if key not in numeric_keys or len(na) < 3 or na in _SKIP_INLINE:
            continue
        pats.append((key, re.compile(r"\b" + re.escape(na) + r"\b")))
    found: List[Candidate] = []
    texts = ([(loc, t) for loc, t in lines_visible(doc)] if doc.is_text else
             [(c.locator, c.text) for c in doc.cells])
    for loc, text in texts:
        low = str(text).lower()
        for key, pat in pats:
            m = pat.search(low)
            if not m:
                continue
            tail = str(text)[m.end():]
            nm = re.search(r"[-+]?\d+(?:[.,]\d+)?", tail)
            if not nm:
                continue
            num, punit, nnotes, namb = parse_value_unit_full(
                nm.group(0) + tail[nm.end():nm.end() + 8])
            if num is None:
                num, nnotes, namb = parse_number(nm.group(0))
                rest = tail[nm.end():].strip()
                um = re.match(r"([A-Za-z°/%µ³²().]+)", rest)
                punit = um.group(1) if um else ""
            unit = punit
            if num is None:
                continue
            found.append(Candidate(key=key, label=raw_label_of(pat), locator=loc,
                                   source_file=doc.source_file, raw_text=str(text),
                                   raw_value=num, raw_unit=unit, confidence=0.90,
                                   notes=["extracted from free text"],
                                   pre_notes=nnotes, pre_amb=namb))
            break
    return found


def raw_label_of(pat) -> str:
    return pat.pattern.replace("\\b", "")


def lines_visible(doc: Document):
    return doc.lines


# ---------------------------------------------------------------- extraction
def extract(doc: Document, aliases: Optional[Dict] = None, llm_enabled: bool = False,
            audit_cb=None) -> Extraction:
    aliases = aliases if aliases is not None else load_aliases()
    pairs = alias_pairs(aliases)
    res = Extraction(doc=doc)
    cands, unmapped = _candidates_from_doc(doc, pairs)
    res.unmapped = unmapped

    if llm_enabled:
        _llm_pass(doc, cands, res, audit_cb)

    for c in cands:
        val, unit, notes, issue = normalize_value(c.key, c.raw_value, c.raw_unit, c.locator)
        c.value, c.unit, c.notes = val, unit, list(c.notes) + list(c.pre_notes) + list(notes)
        if issue is None and c.pre_amb:
            issue = amb_issue_from(c.pre_amb, c.key, c.locator)
        if issue is not None:
            issue.locators = issue.locators or [c.locator]
            c.issue = issue
        res.candidates.setdefault(c.key, []).append(c)

    for key, cs in res.candidates.items():
        cs.sort(key=lambda x: (-x.confidence, x.locator))
        best = cs[0]
        fv = FieldValue(
            key=key, value=best.value, unit=best.unit,
            prov=Provenance(source_file=best.source_file, locator=best.locator,
                            raw_text=best.raw_text),
            confidence=round(min(best.confidence, 1.0), 3), method=best.method,
            notes=best.notes, label=best.label,
            needs_review=bool(best.notes) or best.issue is not None,
        )
        if len(cs) > 1:
            fv.notes = fv.notes + [f"{len(cs)} sources for this field"]
        res.fields[key] = fv
        for c in cs:
            if c.issue is not None and c.issue not in res.issues:
                res.issues.append(c.issue)
        if 0 < best.confidence < 0.88 and best.method == "extracted":
            res.issues.append(Issue(
                code="LOW_MATCH", key=key, severity="AMBER",
                message=(f"Label '{best.label}' matched '{key}' at "
                         f"{best.confidence*100:.0f}% ({best.locator})."),
                question=(f"Does '{best.label}' mean {key}? Confirm the mapping, or teach a "
                          f"new alias so it applies to future sheets."),
                locators=[best.locator]))
    return res


def extract_offer(doc: Document, aliases: Optional[Dict] = None) -> Dict[str, Candidate]:
    """Vendor offers: raw values only, no issue pipeline (compare.py classifies)."""
    aliases = aliases if aliases is not None else load_aliases()
    pairs = alias_pairs(aliases)
    cands, _ = _candidates_from_doc(doc, pairs)
    out: Dict[str, Candidate] = {}
    for c in sorted(cands, key=lambda x: (-x.confidence, x.locator)):
        out.setdefault(c.key, c)
    return out


# ------------------------------------------------------------- optional LLM
def _llm_pass(doc, cands, res, audit_cb):
    """LLM may only propose values from messy text; every proposal is grounded
    against the source span or rejected as `rejected_ungrounded`."""
    from engine.llm import llm_extract, grounding_check
    if not doc.is_text:
        return
    span = "\n".join(t for _, t in doc.lines)
    proposals = llm_extract(span)
    if not proposals:
        return
    for p in proposals:
        text = str(p.get("value", ""))
        if not grounding_check(text, span):
            if audit_cb:
                audit_cb("rejected_ungrounded", {"label": p.get("label"), "value": text})
            continue
        key, score, note = map_label(str(p.get("label", "")), alias_pairs(load_aliases()))
        if key is None or score < 0.70:
            continue
        loc = p.get("locator", "llm")
        val, unit, notes, issue = normalize_value(key, text, "", loc)
        cands.append(Candidate(key=key, label=str(p.get("label")), locator=loc,
                               source_file=doc.source_file, raw_text=text,
                               raw_value=val if val is not None else text,
                               raw_unit=unit or "", value=val, unit=unit,
                               confidence=0.8, method="llm_grounded",
                               notes=["LLM proposal, grounded in source span"],
                               issue=issue))
