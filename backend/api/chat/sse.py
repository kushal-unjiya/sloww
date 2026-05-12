"""Parse SSE stream text for final `done` event and assistant text."""

from __future__ import annotations

import json
from typing import Any


def _iter_sse_events(sse_buffer: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in sse_buffer.split("\n\n"):
        line = next((l for l in frame.split("\n") if l.startswith("data: ")), None)
        if not line:
            continue
        raw = line.removeprefix("data: ").strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def extract_last_done_payload(sse_buffer: str) -> dict[str, Any] | None:
    """Return the parsed JSON object of the last `type: done` frame, if any."""
    last: dict[str, Any] | None = None
    for obj in _iter_sse_events(sse_buffer):
        if obj.get("type") == "done":
            last = obj
    return last


def extract_agent_trace_payloads(sse_buffer: str) -> list[dict[str, Any]]:
    """Return all structured agent trace frames from an SSE transcript."""
    traces: list[dict[str, Any]] = []
    for obj in _iter_sse_events(sse_buffer):
        if obj.get("type") != "agent_trace":
            continue
        traces.append(
            {
                "agent_id": obj.get("agent_id"),
                "label": obj.get("label"),
                "role": obj.get("role"),
                "phase": obj.get("phase"),
                "message": obj.get("message"),
                "input_preview": obj.get("input_preview"),
                "output_preview": obj.get("output_preview"),
                "metadata": obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {},
                "ts": obj.get("ts"),
            }
        )
    return traces


def collect_answer_text_from_sse(sse_buffer: str) -> str:
    """Reconstruct assistant text from `type: token` frames (`content` holds the token)."""
    parts: list[str] = []
    for obj in _iter_sse_events(sse_buffer):
        if obj.get("type") != "token":
            continue
        tok = obj.get("content")
        if isinstance(tok, str):
            parts.append(tok)
    return "".join(parts).strip()
