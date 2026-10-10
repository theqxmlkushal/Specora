"""Pydantic data contracts shared by the whole app."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Method = Literal["extracted", "derived", "default", "engineer_edit", "llm_grounded"]
Status = Literal["GREEN", "AMBER", "RED"]
Verdict = Literal["Compliant", "Deviating", "Unclear", "Missing"]


class Provenance(BaseModel):
    source_file: str
    locator: str                 # "Sheet1!C7" | "p2:line14" | "txt:line9"
    raw_text: str                # exact text found at the source


class FieldValue(BaseModel):
    key: str                                     # canonical key, e.g. "operating_pressure"
    value: Optional[float | str] = None
    unit: Optional[str] = None                   # canonical unit, e.g. "MPa(g)", "degC", "mm"
    prov: Optional[Provenance] = None
    confidence: float = 0.0
    method: Method = "extracted"
    notes: List[str] = Field(default_factory=list)   # e.g. "converted from 145 psig"
    status: Status = "RED"                       # set by the gate
    label: str = ""                              # raw label as found on the sheet
    needs_review: bool = False                   # set by the gate (unit assumption, fuzzy, ...)

    @property
    def display(self) -> str:
        if self.value is None:
            return "—"
        if isinstance(self.value, float):
            txt = f"{self.value:.4g}"
        else:
            txt = str(self.value)
        return f"{txt} {self.unit}" if self.unit else txt


class Issue(BaseModel):
    code: str                     # MISSING | CONFLICT | UNIT_AMBIGUOUS | RULE_VIOLATION | LOW_MATCH
    key: str
    severity: Status
    message: str
    question: Optional[str] = None   # clarification question for the right person
    locators: List[str] = Field(default_factory=list)


class ReqResult(BaseModel):
    req_id: str
    vendor: str
    required: str
    offered: str
    verdict: Verdict
    critical: bool
    category: str
    explanation: str
    question: Optional[str] = None
    source: str = "MDS"
    weight: int = 1
    key: str = ""
    op: str = "=="
    raw_offered: str = ""
    notes: List[str] = Field(default_factory=list)


class MdsRow(BaseModel):
    key: str
    label: str
    value: Optional[float | str] = None
    unit: Optional[str] = None
    method: Method = "derived"
    trace: str = ""                # formula trace / rule id / source
    source: str = ""               # rule id, file!locator or "rules/vessel_rules.yaml"
    status: Status = "GREEN"
    blocked_by: str = ""           # "needs operating_pressure" when RED upstream
    prov: Optional[Provenance] = None
