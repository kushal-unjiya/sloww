"""Per-request log of successful LLM calls (provider + model) for UI streaming."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_llm_calls: ContextVar[list[dict[str, Any]] | None] = ContextVar("llm_turn_calls", default=None)


def begin_llm_turn_trace() -> None:
    _llm_calls.set([])


def record_llm_call(*, provider: str, model: str) -> None:
    log = _llm_calls.get()
    if log is not None:
        log.append({"provider": provider, "model": model})


def snapshot_llm_calls() -> list[dict[str, Any]]:
    log = _llm_calls.get()
    return list(log) if log else []
