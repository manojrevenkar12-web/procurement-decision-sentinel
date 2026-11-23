"""Durable workflow state. Each message is one workflow: read, check, resolve, cards, done.

A step's result is written before the next step starts, so a worker that dies mid-way resumes where it stopped and a
message delivered twice does nothing the second time. `MemoryJournal` serves the study; `service/store.py` keeps the
same steps in SQLite.
"""

from __future__ import annotations

from typing import Any, Protocol


class Journal(Protocol):
    def get(self, msg_id: str) -> dict[str, Any]: ...
    def put(self, msg_id: str, step: str, value: Any) -> None: ...


class MemoryJournal:
    def __init__(self) -> None:
        self._steps: dict[str, dict[str, Any]] = {}

    def get(self, msg_id: str) -> dict[str, Any]:
        return self._steps.get(msg_id, {})

    def put(self, msg_id: str, step: str, value: Any) -> None:
        self._steps.setdefault(msg_id, {})[step] = value


class NoJournal:
    """The ablation: nothing survives a crash and nothing remembers a delivery."""

    def get(self, msg_id: str) -> dict[str, Any]:
        return {}

    def put(self, msg_id: str, step: str, value: Any) -> None:
        return None
