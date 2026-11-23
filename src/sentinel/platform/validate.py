"""A reply becomes a `SignalRead` or nothing. One repair attempt with the validation error, then a person reads it."""

from __future__ import annotations

from dataclasses import dataclass, replace

from pydantic import ValidationError

from ..domain import Prompt, SignalRead
from .readers import Reader


@dataclass(frozen=True)
class ReadResult:
    read: SignalRead | None
    attempts: int
    tokens_in: int
    tokens_cached: int
    tokens_out: int
    latency_s: float
    error: str | None


def read_signal(reader: Reader, prompt: Prompt, max_repairs: int) -> ReadResult:
    tin = tcache = tout = 0
    latency = 0.0
    error: str | None = None
    for attempt in range(max_repairs + 1):
        reply = reader.read(replace(prompt, attempt=attempt, previous_error=error))
        tin += reply.tokens_in
        tcache += reply.tokens_cached
        tout += reply.tokens_out
        latency += reply.latency_s
        try:
            return ReadResult(SignalRead.model_validate_json(reply.text), attempt + 1, tin, tcache, tout, latency, None)
        except ValidationError as e:
            error = str(e)[:800]
    return ReadResult(None, max_repairs + 1, tin, tcache, tout, latency, error)


def cost_eur(r: ReadResult, price: dict[str, float]) -> float:
    fresh = max(0, r.tokens_in - r.tokens_cached)
    return (fresh * float(price["in"]) + r.tokens_cached * float(price["cached"]) + r.tokens_out * float(price["out"])) / 1e6
