import pytest
from pydantic import ValidationError

from mecapilot.models import AnalysisSubmission, FaultSheet, Measurement, make_citation, make_ref, split_ref


def synthetic_sheet(**overrides) -> dict:
    sheet = {
        "id": "SYN-001",
        "synthetic": True,
        "title": "Synthetic sheet - not real automotive data",
        "codes": ["P0171"],
        "safety_critical": False,
        "source": "Synthetic test data",
        "causes": {"C1": "Synthetic cause A", "C2": "Synthetic cause B"},
        "tests": {
            "T1": {
                "description": "Synthetic test 1",
                "duration_min": 2,
                "outcomes": {"outcome_x": {"C1": "strengthened", "C2": "weakened"}},
            }
        },
        "sections": {"causes": "Synthetic text."},
    }
    sheet.update(overrides)
    return sheet


def test_valid_sheet_loads():
    sheet = FaultSheet.model_validate(synthetic_sheet())
    assert sheet.tests["T1"].outcomes["outcome_x"]["C1"].value == "strengthened"


@pytest.mark.parametrize(
    "overrides",
    [
        {"codes": ["P171"]},                                     # bad DTC format
        {"tests": {"T1": {"description": "x", "duration_min": 1,
                          "outcomes": {"o": {"C9": "confirmed"}}}}},   # unknown cause
        {"tests": {"T1": {"description": "x", "duration_min": 1,
                          "outcomes": {"o": {"C1": "open"}}}}},        # effect not allowed
        {"pid_ranges": {"RPM": {"min": 0, "max": 1}}},            # removed field
        {"source": None},                                         # missing source
    ],
)
def test_invalid_sheet_rejected(overrides):
    with pytest.raises(ValidationError):
        FaultSheet.model_validate(synthetic_sheet(**overrides))


def test_measurement_has_no_plausibility_field():
    with pytest.raises(ValidationError):
        Measurement(pid="RPM", value=1, unit="rpm", timestamp="2026-11-14T10:00:00Z",
                    source="emulator", plausible=True)


def test_refs_roundtrip():
    assert split_ref(make_ref("SYN-001", "C1")) == ("SYN-001", "C1")
    assert make_citation("SYN-001", "causes") == "SYN-001#causes"
    with pytest.raises(ValueError):
        split_ref("SYN-001")


def test_submission_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AnalysisSubmission.model_validate({"hypotheses": [], "message_to_technician": "x", "state": "completed"})
