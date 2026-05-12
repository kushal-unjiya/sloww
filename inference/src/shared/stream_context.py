"""Request-scoped hook for streaming final answer tokens (e.g. Google GenAI chunks)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar

StreamAnswerChunkCallback = Callable[[str], Awaitable[None]]

answer_stream_sink: ContextVar[StreamAnswerChunkCallback | None] = ContextVar(
    "answer_stream_sink",
    default=None,
)


def get_answer_stream_sink() -> StreamAnswerChunkCallback | None:
    return answer_stream_sink.get()
