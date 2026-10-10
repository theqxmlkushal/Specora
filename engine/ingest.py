"""Ingest any supported file into `cells with locators`.

Excel : Sheet1!C7      text : txt:line9      pdf : p2:line14
Every later step works on this common structure, so the source of every value
is always traceable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SUPPORTED_XLSX = {".xlsx", ".xlsm"}
SUPPORTED_TXT = {".txt", ".csv", ".md"}
SUPPORTED_PDF = {".pdf"}


@dataclass
class Cell:
    text: str
    locator: str
    sheet: str = ""
    row: int = 0
    col: int = 0


@dataclass
class Document:
    source_file: str
    kind: str                    # xlsx | csv | txt | pdf
    layout: str                  # L1 | L2 | L3
    cells: List[Cell] = field(default_factory=list)
    grid: Dict[str, List[List[str]]] = field(default_factory=dict)   # sheet -> rows
    lines: List[Tuple[str, str]] = field(default_factory=list)       # (locator, text) for text/pdf
    labels: List[Tuple[str, str]] = field(default_factory=list)      # (label, locator) filled by extract
    error: str = ""

    @property
    def is_text(self) -> bool:
        return self.kind in ("txt", "pdf")

    def preview_df(self):
        import pandas as pd
        if self.is_text:
            return pd.DataFrame([(loc, txt) for loc, txt in self.lines], columns=["locator", "text"])
        sheet = next(iter(self.grid))
        return pd.DataFrame(self.grid[sheet]).fillna("")


def col_letter(idx: int) -> str:
    out = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def ingest(path, name: Optional[str] = None) -> Document:
    p = Path(path)
    name = name or p.name
    suffix = p.suffix.lower()
    if suffix in SUPPORTED_XLSX:
        return _ingest_xlsx(p, name)
    if suffix == ".pdf":
        return _ingest_pdf(p, name)
    return _ingest_text(p, name)


def _ingest_xlsx(p: Path, name: str) -> Document:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(str(p), data_only=True, read_only=True)
    except Exception as exc:                      # pragma: no cover
        return Document(name, "xlsx", "L1", error=f"Could not open workbook: {exc}")
    grid: Dict[str, List[List[str]]] = {}
    cells: List[Cell] = []
    for ws in wb.worksheets:
        rows = []
        for r, row in enumerate(ws.iter_rows(values_only=True), start=1):
            vals = [_s(v) for v in row]
            if any(vals):
                rows.append((r, vals))
        if not rows:
            continue
        width = max(len(v) for _, v in rows)
        mat = [[""] * width for _ in range(len(rows))]
        for i, (r, vals) in enumerate(rows):
            for c, v in enumerate(vals, start=1):
                mat[i][c - 1] = v
        grid[ws.title] = mat
        for i, row in enumerate(mat, start=1):
            for c, v in enumerate(row, start=1):
                if v != "":
                    cells.append(Cell(v, f"{ws.title}!{col_letter(c)}{i}", ws.title, i, c))
    wb.close()
    if not grid:
        return Document(name, "xlsx", "L1", error="Workbook has no data.")
    first = grid[next(iter(grid))]
    header_len = len([x for x in first[0] if x]) if first else 0
    layout = "L2" if header_len >= 6 else "L1"
    return Document(name, "xlsx", layout, cells=cells, grid=grid)


def _ingest_text(p: Path, name: str) -> Document:
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:                      # pragma: no cover
        return Document(name, "txt", "L3", error=str(exc))
    lines = [(f"txt:line{i}", ln.rstrip("\n")) for i, ln in enumerate(raw.splitlines(), start=1)]
    cells = [Cell(t, loc) for loc, t in lines if t.strip()]
    return Document(name, "csv" if p.suffix.lower() == ".csv" else "txt", "L3",
                    cells=cells, lines=lines)


def _ingest_pdf(p: Path, name: str) -> Document:
    try:
        import pdfplumber
    except Exception:
        return Document(name, "pdf", "L3", error="pdfplumber is not installed — PDF input disabled.")
    lines: List[Tuple[str, str]] = []
    try:
        with pdfplumber.open(str(p)) as pdf:
            for pi, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                for li, ln in enumerate(text.splitlines(), start=1):
                    lines.append((f"p{pi}:line{li}", ln))
    except Exception as exc:
        return Document(name, "pdf", "L3", error=f"Could not read PDF: {exc}")
    cells = [Cell(t, loc) for loc, t in lines if t.strip()]
    return Document(name, "pdf", "L3", cells=cells, lines=lines)


# ------------------------------------------------------------------ parsing
PAIR_RE = re.compile(r"^\s*(?P<label>[^:=]{1,60}?)\s*[:=]\s*(?P<val>.+?)\s*$")
INLINE_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
UNIT_WORDS = ("mpa(g)", "mpag", "mpa", "barg", "bara", "bar(g)", "bar", "psig", "psia", "psi",
              "kpag", "kpa", "degc", "degf", "°c", "°f", "c", "f", "mm", "cm", "m", "in",
              "inch", "inches", "ft", "ppm", "%")


def parse_value_unit(txt: str):
    """'145 psig' -> (145.0,'psig') ; 'SA-516-70' -> (None,'SA-516-70')."""
    num, unit, _notes, _amb = parse_value_unit_full(txt)
    return num, unit


def parse_value_unit_full(txt: str):
    """-> (number|None, unit, notes, ambiguity_code)"""
    from engine.normalize import parse_number
    if txt is None:
        return None, "", [], None
    s = str(txt).strip()
    if not s:
        return None, "", [], None
    m = re.match(r"^(?P<num>[-+]?\d[\d\s,._]*(?:[.,]\d+)?)\s*(?P<rest>.*)$", s)
    if not m:
        return None, s, [], None
    num, notes, amb = parse_number(m.group("num"))
    if num is None:
        return None, s, [], None
    rest = (m.group("rest") or "").strip()
    if rest == "":
        return num, "", notes, amb
    if rest.lower() in UNIT_WORDS or re.match(r"^[a-z°/%µ³²().-]+$", rest.lower()):
        return num, rest, notes, amb
    return None, s, [], None     # looks like text, not "number unit"
