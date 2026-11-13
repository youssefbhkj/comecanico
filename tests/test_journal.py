from datetime import datetime, timezone

import pytest

from mecapilot.config import load_config
from mecapilot.journal import Journal
from mecapilot.models import State


def fixed_clock():
    return datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)


def test_log_and_reload(tmp_path):
    journal = Journal.create(tmp_path, clock=fixed_clock)
    first = journal.log("session_opened")
    second = journal.log("pid_read", State.ANALYZING, pid="RPM", value=780.0, unit="rpm")
    assert (first.id, second.id) == ("E0001", "E0002")

    reloaded = Journal.load(journal.path)
    assert [e.id for e in reloaded.events] == ["E0001", "E0002"]
    assert reloaded.get("E0002").data["value"] == 780.0
    assert reloaded.get("E0002").state is State.ANALYZING
    assert len(reloaded.of_type("pid_read")) == 1


def test_unknown_event_type_rejected(tmp_path):
    journal = Journal.create(tmp_path)
    with pytest.raises(ValueError):
        journal.log("plausibility_alert")
    assert not journal.path.exists() or journal.path.read_text() == ""


def test_project_config_loads():
    config = load_config("config.yaml")
    assert config.llm.max_tool_iterations >= 1
