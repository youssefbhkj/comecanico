"""Shared data contracts (Pydantic v2). Keep minimal; see CLAUDE.md for the rules they encode."""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

DTC_PATTERN = re.compile(r"^[PBCU][0-9A-F]{4}$")


class State(str, Enum):
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    AWAITING_TEST_RESULT = "awaiting_test_result"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    REPORTING = "reporting"
    COMPLETED = "completed"
    STOPPED = "stopped"


class StopReason(str, Enum):
    CODE_NOT_FOUND = "code_not_found"
    SAFETY = "safety"
    INSUFFICIENT_DOCUMENTATION = "insufficient_documentation"


class CauseStatus(str, Enum):
    OPEN = "open"
    STRENGTHENED = "strengthened"
    WEAKENED = "weakened"
    ELIMINATED = "eliminated"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"


# Statuses a sheet's test outcome may assign (open/disputed are set by Python only).
OUTCOME_EFFECTS = {
    CauseStatus.STRENGTHENED,
    CauseStatus.WEAKENED,
    CauseStatus.ELIMINATED,
    CauseStatus.CONFIRMED,
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Acquisition ---------------------------------------------------------------------------

class Measurement(_Strict):
    """Raw PID reading. Not technically validated (no plausibility check in the MVP)."""
    pid: str
    value: float
    unit: str
    timestamp: datetime
    source: str                      # e.g. "emulator:SYN-001"
    event_id: str | None = None      # journal event that recorded it


class DtcReport(_Strict):
    stored: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)


# --- Knowledge base ------------------------------------------------------------------------

class SheetTest(_Strict):
    description: str
    duration_min: float = Field(ge=0)
    tools: list[str] = Field(default_factory=list)
    pids: list[str] = Field(default_factory=list)
    outcomes: dict[str, dict[str, CauseStatus]] = Field(min_length=1)


class FaultSheet(_Strict):
    id: str
    synthetic: bool
    title: str
    codes: list[str] = Field(min_length=1)
    safety_critical: bool
    source: str
    validated_by: str | None = None
    causes: dict[str, str] = Field(min_length=1)
    tests: dict[str, SheetTest] = Field(default_factory=dict)
    sections: dict[str, str] = Field(min_length=1)   # searchable, citable text

    @model_validator(mode="after")
    def _check_consistency(self) -> FaultSheet:
        for code in self.codes:
            if not DTC_PATTERN.match(code):
                raise ValueError(f"{self.id}: invalid DTC format {code!r}")
        for test_id, test in self.tests.items():
            for outcome, effects in test.outcomes.items():
                for cause_id, status in effects.items():
                    if cause_id not in self.causes:
                        raise ValueError(f"{self.id}:{test_id}/{outcome}: unknown cause {cause_id!r}")
                    if status not in OUTCOME_EFFECTS:
                        raise ValueError(f"{self.id}:{test_id}/{outcome}: effect {status.value!r} not allowed")
        return self


# --- References ------------------------------------------------------------------------------

def make_ref(sheet_id: str, local_id: str) -> str:
    """Cause/test ref: 'SYN-001:C1'."""
    return f"{sheet_id}:{local_id}"


def split_ref(ref: str) -> tuple[str, str]:
    sheet_id, sep, local_id = ref.partition(":")
    if not sep or not sheet_id or not local_id:
        raise ValueError(f"invalid ref {ref!r}, expected 'SHEET:ID'")
    return sheet_id, local_id


def make_citation(sheet_id: str, section: str) -> str:
    """Citation id: 'SYN-001#causes'."""
    return f"{sheet_id}#{section}"


# --- LLM output (submit_analysis) -----------------------------------------------------------

class Hypothesis(_Strict):
    cause_ref: str
    rationale: str
    evidence_refs: list[str]   # journal event ids
    citations: list[str]       # citation ids returned by a tool this session


class TestProposal(_Strict):
    __test__ = False           # not a pytest test class
    test_ref: str
    rationale: str


class AnalysisSubmission(_Strict):
    hypotheses: list[Hypothesis]          # order = LLM's judgment
    proposed_test: TestProposal | None = None
    insufficient_documentation: bool = False
    missing_information: list[str] = Field(default_factory=list)
    message_to_technician: str


# --- Journal ---------------------------------------------------------------------------------

class JournalEvent(_Strict):
    id: str
    t: datetime
    type: str
    state: State | None = None
    data: dict[str, Any] = Field(default_factory=dict)
