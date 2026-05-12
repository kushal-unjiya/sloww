from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, Literal


AgentPhase = Literal["start", "progress", "end", "error"]
AgentEventSink = Callable[[dict[str, Any]], Awaitable[None]]

agent_event_sink: ContextVar[AgentEventSink | None] = ContextVar(
    "agent_event_sink",
    default=None,
)


async def emit_agent_event(
    *,
    agent_id: str,
    label: str,
    role: str,
    phase: AgentPhase,
    message: str,
    input_preview: str | None = None,
    output_preview: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    sink = agent_event_sink.get()
    if sink is None:
        return
    await sink(
        {
            "agent_id": agent_id,
            "label": label,
            "role": role,
            "phase": phase,
            "message": message,
            "input_preview": input_preview,
            "output_preview": output_preview,
            "metadata": metadata or {},
            "ts": time.time(),
        }
    )

