"""Per-chat-turn wall-clock timeline for latency debugging (ContextVar-scoped)."""

from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

_t0: ContextVar[float | None] = ContextVar("turn_timing_t0", default=None)
_marks: ContextVar[list[dict[str, Any]] | None] = ContextVar("turn_timing_marks", default=None)


def begin_turn_timeline() -> None:
    _t0.set(time.perf_counter())
    _marks.set([])


def mark_turn_phase(phase: str, **extra: Any) -> None:
    t0 = _t0.get()
    marks = _marks.get()
    if t0 is None or marks is None:
        return
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    row: dict[str, Any] = {"phase": phase, "elapsed_ms": elapsed_ms}
    row.update(extra)
    marks.append(row)


def snapshot_turn_timeline() -> list[dict[str, Any]]:
    marks = _marks.get()
    return list(marks) if marks else []


def timeline_segments(marks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wall time between consecutive marks (``segment_ms``) for ``chat_turn_end`` debugging."""
    out: list[dict[str, Any]] = []
    prev = 0
    for m in marks:
        cum = int(m.get("elapsed_ms") or 0)
        out.append(
            {
                "phase": m.get("phase"),
                "segment_ms": cum - prev,
                "cumulative_ms": cum,
            }
        )
        prev = cum
    return out


def end_turn_timeline() -> None:
    _t0.set(None)
    _marks.set(None)
