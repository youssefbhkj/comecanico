import pytest
from pydantic import ValidationError

from mecapilot.acquisition import EmulatorSource, Scenario, UnsupportedPidError, load_scenario, make_source


def scenario(**overrides) -> Scenario:
    raw = {
        "id": "SYN-T",
        "synthetic": True,
        "dtcs": {"stored": ["P0171"], "pending": []},
        "freeze_frame": {"RPM": {"value": 800, "unit": "rpm"}},
        "conditions": ["idle", "high"],
        "pids": {
            "RPM": {"unit": "rpm", "type": "by_condition", "values": {"idle": 800, "high": 2000}},
            "TEMP": {"unit": "degC", "type": "fixed", "value": 90, "noise": 2},
        },
    }
    raw.update(overrides)
    return Scenario.model_validate(raw)


def test_reads_dtcs_vin_and_freeze_frame():
    src = EmulatorSource(scenario(vin="SYN123"))
    assert src.read_dtcs().stored == ["P0171"]
    assert src.read_vin() == "SYN123"
    (frame,) = src.read_freeze_frame()
    assert (frame.pid, frame.value, frame.source) == ("RPM", 800, "emulator:SYN-T:freeze_frame")


def test_pid_follows_condition():
    src = EmulatorSource(scenario())
    assert src.read_pid("RPM").value == 800
    src.set_condition("high")
    assert src.read_pid("RPM").value == 2000
    with pytest.raises(ValueError):
        src.set_condition("unknown")


def test_noise_is_bounded_and_seeded():
    a = [EmulatorSource(scenario(), seed=1).read_pid("TEMP").value for _ in range(3)]
    b = [EmulatorSource(scenario(), seed=1).read_pid("TEMP").value for _ in range(3)]
    assert a == b
    assert all(88 <= v <= 92 for v in a)


def test_measurement_is_raw():
    m = EmulatorSource(scenario()).read_pid("TEMP")
    assert set(m.model_dump()) == {"pid", "value", "unit", "timestamp", "source", "event_id"}


def test_unsupported_pid():
    src = EmulatorSource(scenario())
    assert src.supported_pids() == ["RPM", "TEMP"]
    with pytest.raises(UnsupportedPidError):
        src.read_pid("MAF")


def test_clear_dtcs_does_not_mutate_scenario():
    sc = scenario()
    src = EmulatorSource(sc)
    assert src.clear_dtcs() is True
    assert src.read_dtcs().stored == []
    assert sc.dtcs.stored == ["P0171"]


@pytest.mark.parametrize("overrides", [
    {"synthetic": False},                                                     # must be synthetic
    {"pids": {"RPM": {"unit": "rpm", "type": "by_condition", "values": {"idle": 1}}}},  # missing condition
    {"pids": {"RPM": {"unit": "rpm", "type": "fixed"}}},                      # fixed without value
])
def test_invalid_scenario_rejected(overrides):
    with pytest.raises(ValidationError):
        scenario(**overrides)


def test_demo_scenario_loads():
    src = make_source("emulator", "data/scenarios/SYN-001.json")
    assert load_scenario("data/scenarios/SYN-001.json").synthetic is True
    assert "LONG_FUEL_TRIM_1" in src.supported_pids()
