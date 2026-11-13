"""Load and validate config.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMConfig(_Strict):
    provider: Literal["fake", "claude"] = "fake"
    model: str = "claude-haiku-5-5"
    max_tool_iterations: int = Field(default=8, ge=1, le=20)
    max_analysis_cycles: int = Field(default=8, ge=1, le=50)


class PathsConfig(_Strict):
    sheets_dir: Path = Path("data/sheets")
    sessions_dir: Path = Path("sessions")


class AppConfig(_Strict):
    source: Literal["emulator"] = "emulator"
    scenario: Path
    llm: LLMConfig = LLMConfig()
    paths: PathsConfig = PathsConfig()


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig.model_validate(raw)
