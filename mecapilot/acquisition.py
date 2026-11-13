"""Vehicle acquisition: the VehicleSource interface and a scenario-driven emulator.

Measurements are raw readings (no plausibility validation in the MVP). This module does not
journal anything: the agent's tool layer records readings in the session journal.
"""
from __future__ import annotations

import json
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mecapilot.models import DtcReport, Measurement


class UnsupportedPidError(KeyError):
    """Requested PID is not available from this source."""


class VehicleSource(ABC):
    """The only vehicle interface the agent knows. PID names follow python-OBD command names."""

    @abstractmethod
    def read_vin(self) -> str | None: ...

    @abstractmethod
    def read_dtcs(self) -> DtcReport: ...

    @abstractmethod
    def read_freeze_frame(self) -> list[Measurement]: ...

    @abstractmethod
    def read_pid(self, name: str) -> Measurement: ...

    @abstractmethod
    def supported_pids(self) -> list[str]: ...

    @abstractmethod
    def clear_dtcs(self) -> bool:
        """Side effect. Python-only, after explicit human approval; never exposed to the LLM."""


# --- Scenario format -------------------------------------------------------------------------

class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenValue(_Strict):
    value: float
    unit: str


class PidModel(_Strict):
    """How the emulator produces a PID: a fixed value, or one value per named engine condition."""
    unit: str
    type: Literal["fixed", "by_condition"]
    value: float | None = None
    values: dict[str, float] | None = None
    noise: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _check_type(self) -> PidModel:
        if self.type == "fixed" and self.value is None:
            raise ValueError("fixed PID requires 'value'")
        if self.type == "by_condition" and not self.values:
            raise ValueError("by_condition PID requires 'values'")
        return self


class Scenario(_Strict):
    id: str
    synthetic: Literal[True]               # MVP rule: all automotive data is synthetic
    description: str = ""
    vin: str | None = None
    dtcs: DtcReport
    freeze_frame: dict[str, FrozenValue] = Field(default_factory=dict)
    conditions: list[str] = Field(default_factory=lambda: ["idle"])
    pids: dict[str, PidModel] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_conditions(self) -> Scenario:
        for name, pid in self.pids.items():
            if pid.type == "by_condition":
                missing = set(self.conditions) - set(pid.values or {})
                if missing:
                    raise ValueError(f"PID {name}: no value for conditions {sorted(missing)}")
        return self


def load_scenario(path: str | Path) -> Scenario:
    with open(path, encoding="utf-8") as f:
        return Scenario.model_validate(json.load(f))


# --- Emulator --------------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmulatorSource(VehicleSource):
    """Replays a synthetic scenario. `set_condition` is a simulation control, not part of VehicleSource."""

    def __init__(self, scenario: Scenario, seed: int | None = 0,
                 clock: Callable[[], datetime] = _utcnow):
        self.scenario = scenario
        self.condition = scenario.conditions[0]
        self._dtcs = scenario.dtcs.model_copy(deep=True)
        self._rng = random.Random(seed)
        self._clock = clock
        self._label = f"emulator:{scenario.id}"

    def set_condition(self, condition: str) -> None:
        if condition not in self.scenario.conditions:
            raise ValueError(f"unknown condition {condition!r}; expected one of {self.scenario.conditions}")
        self.condition = condition

    def read_vin(self) -> str | None:
        return self.scenario.vin

    def read_dtcs(self) -> DtcReport:
        return self._dtcs.model_copy(deep=True)

    def read_freeze_frame(self) -> list[Measurement]:
        now = self._clock()
        return [Measurement(pid=name, value=v.value, unit=v.unit, timestamp=now, source=f"{self._label}:freeze_frame")
                for name, v in self.scenario.freeze_frame.items()]

    def read_pid(self, name: str) -> Measurement:
        model = self.scenario.pids.get(name)
        if model is None:
            raise UnsupportedPidError(name)
        base = model.value if model.type == "fixed" else model.values[self.condition]
        value = base + self._rng.uniform(-model.noise, model.noise) if model.noise else base
        return Measurement(pid=name, value=round(value, 2), unit=model.unit,
                           timestamp=self._clock(), source=self._label)

    def supported_pids(self) -> list[str]:
        return sorted(self.scenario.pids)

    def clear_dtcs(self) -> bool:
        self._dtcs = DtcReport()
        return True


def make_source(source: str, scenario_path: str | Path, seed: int | None = None) -> VehicleSource:
    if source == "emulator":
        return EmulatorSource(load_scenario(scenario_path), seed=seed)
    raise ValueError(f"unsupported source {source!r} (MVP supports 'emulator' only)")
