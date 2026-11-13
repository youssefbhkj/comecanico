"""Append-only JSONL session journal: one event per line, source of truth for reports."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mecapilot.models import JournalEvent, State

EVENT_TYPES = {
    "session_opened",
    "dtcs_read",
    "freeze_frame_read",
    "vin_read",
    "pid_read",
    "symptoms_entered",
    "state_changed",
    "tool_called",
    "docs_retrieved",
    "analysis_submitted",
    "test_proposed",
    "test_result",
    "cause_confirmed",
    "cause_disputed",
    "document_generated",
    "refusal",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Journal:
    def __init__(self, path: Path, session_id: str, clock: Callable[[], datetime] = _utcnow):
        self.path = path
        self.session_id = session_id
        self._clock = clock
        self.events: list[JournalEvent] = []

    @classmethod
    def create(cls, sessions_dir: str | Path, clock: Callable[[], datetime] = _utcnow) -> Journal:
        session_id = uuid.uuid4().hex[:12]
        path = Path(sessions_dir) / f"{session_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(path, session_id, clock)

    @classmethod
    def load(cls, path: str | Path) -> Journal:
        path = Path(path)
        journal = cls(path, path.stem)
        with open(path, encoding="utf-8") as f:
            journal.events = [JournalEvent.model_validate_json(line) for line in f if line.strip()]
        return journal

    def log(self, type: str, state: State | None = None, **data: Any) -> JournalEvent:
        if type not in EVENT_TYPES:
            raise ValueError(f"unknown journal event type {type!r}")
        event = JournalEvent(id=f"E{len(self.events) + 1:04d}", t=self._clock(), type=type, state=state, data=data)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
        self.events.append(event)
        return event

    def get(self, event_id: str) -> JournalEvent | None:
        return next((e for e in self.events if e.id == event_id), None)

    def of_type(self, type: str) -> list[JournalEvent]:
        return [e for e in self.events if e.type == type]
