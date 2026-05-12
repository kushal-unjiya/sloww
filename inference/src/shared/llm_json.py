"""Best-effort JSON extraction from LLM text (markdown fences, preamble)."""

from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def parse_llm_json_object(text: str) -> dict:
    """Parse the first JSON object from model output (ignores trailing text / second objects)."""
    s = (text or "").strip()
    if not s:
        raise ValueError("empty model response")

    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()

    s = s.strip().strip("`")

    start = s.find("{")
    if start == -1:
        raise ValueError("no JSON object start '{' in model response")

    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(s[start:])
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON object: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("expected a JSON object at start of value")
    return obj
