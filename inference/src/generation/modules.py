from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.graph.state import AggregatorOutput, CitedAnswer
from src.shared.clients.llm_client import LLMClient
from src.shared.llm_json import parse_llm_json_object
from src.shared.logging import get_logger, timer
from src.shared.turn_timing import mark_turn_phase

logger = get_logger("sloww.inference.generation.modules")

_CITATION_RE = re.compile(r"\[([^\[\]]+)\]")
_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
_NUMBERED_RE = re.compile(r"^(?:[-*•]\s*)?(?P<num>\d+(?:\.\d+){0,5})\s*[:\-–—)]?\s+(?P<title>.+?)\s*$")
_ALPHA_SECTION_RE = re.compile(r"^(?:[-*•]\s*)?(?P<label>[A-Z])(?:\.(?P<sub>\d+(?:\.\d+){0,4}))?\s*[:\-–—)]?\s+(?P<title>.+?)\s*$")


def _extract_chunk_ids(text: str) -> list[str]:
    return [m.group(1).strip() for m in _CITATION_RE.finditer(text)]


def build_structure_hints(source_chunks: str, *, max_items: int = 48) -> str:
    """Extract compact outline-like hints only from explicit structure markers."""
    hints: list[str] = []
    seen: set[str] = set()
    for raw_line in source_chunks.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        title: str | None = None
        key: str | None = None
        match = _HEADING_RE.match(line)
        if match:
            title = match.group("title").strip()
            key = f"h:{title}".lower()
        else:
            match = _NUMBERED_RE.match(line)
            if match:
                num = match.group("num")
                title = match.group("title").strip()
                key = f"n:{num} {title}".lower()
            else:
                match = _ALPHA_SECTION_RE.match(line)
                if match:
                    label = match.group("label")
                    sub = match.group("sub") or ""
                    title = match.group("title").strip()
                    key = f"a:{label}.{sub} {title}".lower()
        if not title or not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        hints.append(title)
        if len(hints) >= max_items:
            break
    return "\n".join(hints)


def repair_citations_with_fallback(text: str, chunk_ids: list[str]) -> str:
    """Append fallback ``[chunk_id]`` to lines that lack citations (no extra LLM call)."""
    if not chunk_ids or not text or not text.strip():
        return text
    fallback = chunk_ids[0]
    out_lines: list[str] = []
    for ln in text.split("\n"):
        core = ln.rstrip()
        if not core.strip():
            out_lines.append(ln)
            continue
        stripped = core.strip()
        if stripped.endswith("]") and _CITATION_RE.search(stripped):
            out_lines.append(ln)
            continue
        out_lines.append(f"{core}[{fallback}]")
    return "\n".join(out_lines)


@dataclass
class AggregatorModule:
    llm: LLMClient

    async def __call__(self, *, query: str, doc_a_chunks: str, doc_b_chunks: str) -> AggregatorOutput:
        t = timer()
        prompt = (
            "You are aggregating information across two documents. "
            "Detect agreements and conflicts, then produce a consolidated view.\n\n"
            "Return ONLY valid JSON (no markdown) matching:\n"
            "{\n"
            '  "agreements": string[],\n'
            '  "conflicts": [{\n'
            '     "topic": string,\n'
            '     "doc_a_claim": string,\n'
            '     "doc_b_claim": string,\n'
            '     "chunk_ids_a": string[],\n'
            '     "chunk_ids_b": string[],\n'
            '     "conflict_type": "ontological"|"mathematical"|"interpretive"\n'
            "  }],\n"
            '  "consolidated": string,\n'
            '  "reasoning_trace": string\n'
            "}\n\n"
            f"Query: {query}\n\n"
            f"Doc A chunks:\n{doc_a_chunks}\n\n"
            f"Doc B chunks:\n{doc_b_chunks}\n\n"
            "Output JSON:"
        )
        res = await self.llm.complete(prompt=prompt)
        try:
            data = parse_llm_json_object(res.text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(
                "aggregator_json_parse_failed",
                extra={
                    "event": "aggregator_json_parse_failed",
                    "error": str(e),
                    "response_preview": (res.text[:500] if res.text else ""),
                },
            )
            raise ValueError(f"aggregator returned non-JSON: {e}") from e
        out = AggregatorOutput.model_validate(data)
        logger.info(
            "aggregator",
            extra={
                "event": "aggregator",
                "component": "aggregator",
                "provider": res.provider,
                "model": res.model,
                "latency_ms": t.ms(),
                "conflicts_found": len(out.conflicts),
            },
        )
        mark_turn_phase("aggregator", latency_ms=t.ms(), conflicts=len(out.conflicts))
        return out


@dataclass
class CitedSummaryModule:
    llm: LLMClient

    async def __call__(self, *, query: str, consolidated: str, source_chunks: str, structure_hints: str = "") -> CitedAnswer:
        t = timer()
        prompt = (
            "Write a grounded answer to the user's query using ONLY the provided chunks.\n"
            "Rules (strict):\n"
            "- Plain text only — no markdown headings, lists, or bullets in the answer.\n"
            "- Answer with enough detail to be useful; prefer 6-12 grounded lines when the evidence supports it.\n"
            "- Each non-empty line may contain one or two related sentences, but every line must stay focused on a single point.\n"
            "- If the user asks to list parts of a document, be exhaustive and include every distinct item supported by the chunks.\n"
            "- Preserve the source outline only when it is explicitly visible in the chunks.\n"
            "- If no explicit outline is present, answer in a flat style and do not invent headings or subsection groupings.\n"
            "- Every line MUST end with a citation bracket copied EXACTLY from the chunk list "
            "(hyphen line starts with `- chunk_id:`). Example endings: "
            "`.[proj_x_chunk_01]` or `.[chunk_1]` — no space before the opening `[`.\n"
            "- Do NOT use footnotes like '1.' at end of line, '(1)', or '[1]'; only real chunk_ids from the list.\n"
            "- If a sentence cannot be grounded in the chunks, omit that sentence.\n\n"
            "Structural hints extracted from the source text, if any:\n"
            f"{structure_hints or '(none)'}\n\n"
            "Few-shot example:\n"
            "Chunks:\n"
            "- chunk_1: Cats are mammals.\n"
            "- chunk_2: Cats purr when content.\n"
            "Answer:\n"
            "Cats are mammals.[chunk_1]\n"
            "They often purr when content.[chunk_2]\n\n"
            f"Query: {query}\n\n"
            f"Consolidated context:\n{consolidated}\n\n"
            f"Chunks:\n{source_chunks}\n\n"
            "Answer:"
        )
        res = await self.llm.complete(prompt=prompt, stream_final_answer=True)
        text = res.text.strip()
        logger.info(
            "cited_summary",
            extra={
                "event": "cited_summary",
                "component": "cited_summary",
                "provider": res.provider,
                "model": res.model,
                "latency_ms": t.ms(),
            },
        )
        mark_turn_phase("cited_summary", latency_ms=t.ms())

        # Node will enforce assertion/retries; module returns raw output.
        return CitedAnswer(text=text, citations=[], assertion_failed=False)


@dataclass
class NormalTextModule:
    llm: LLMClient

    async def __call__(self, *, query: str) -> str:
        t = timer()
        prompt = (
            "You are a helpful assistant. Answer conversationally and with enough detail to be useful. "
            "Prefer a fuller explanation over a terse reply unless the user clearly asks for brevity.\n\n"
            f"User: {query}\n"
            "Assistant:"
        )
        res = await self.llm.complete(prompt=prompt, stream_final_answer=True)
        logger.info(
            "normal_text",
            extra={
                "event": "normal_text",
                "component": "normal_text",
                "provider": res.provider,
                "model": res.model,
                "latency_ms": t.ms(),
            },
        )
        mark_turn_phase("normal_text", latency_ms=t.ms())
        return res.text.strip()


@dataclass
class VisualizerModule:
    llm: LLMClient

    async def __call__(self, *, query: str, data_payload: str) -> dict:
        t = timer()
        prompt = (
            "Generate a JSON chart schema from the provided data.\n"
            "Return ONLY valid JSON (no markdown). Schema:\n"
            "{\n"
            '  "chart_type": "bar"|"line"|"pie",\n'
            '  "x": string[],\n'
            '  "y": number[],\n'
            '  "labels": string[]\n'
            "}\n\n"
            f"Query: {query}\n"
            f"Data:\n{data_payload}\n"
            "Output JSON:"
        )
        res = await self.llm.complete(prompt=prompt)
        chart = parse_llm_json_object(res.text)
        logger.info(
            "visualizer",
            extra={
                "event": "visualizer",
                "component": "visualizer",
                "provider": res.provider,
                "model": res.model,
                "latency_ms": t.ms(),
                "chart_type": chart.get("chart_type"),
            },
        )
        return chart


def explain_citation_assertion_failure(text: str) -> dict[str, object]:
    """Why ``every_claim_has_chunk_id`` failed (for logs)."""
    raw = (text or "").strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not raw:
        return {"reason": "empty_answer"}
    if not lines:
        return {"reason": "no_non_empty_lines"}
    ids = _extract_chunk_ids(raw)
    if not ids:
        trailing_num = bool(re.search(r"(?:^|\s)\d{1,2}\.\s*$", lines[-1]))
        return {
            "reason": "no_bracket_citations_found",
            "line_count": len(lines),
            "last_line_preview": lines[-1][:160],
            "suspected_numeric_footnotes": trailing_num,
        }
    for i, ln in enumerate(lines):
        if not ln.endswith("]"):
            return {
                "reason": "line_missing_trailing_bracket",
                "line_index": i,
                "line_preview": ln[:200],
                "line_count": len(lines),
            }
        if not _CITATION_RE.search(ln):
            return {
                "reason": "line_has_no_bracket_chunk_id",
                "line_index": i,
                "line_preview": ln[:200],
                "line_count": len(lines),
            }
    return {"reason": "unknown", "line_count": len(lines)}


def every_claim_has_chunk_id(text: str) -> bool:
    # Heuristic assertion: each non-empty line ends with [...], and at least one chunk id exists.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    if not _extract_chunk_ids(text):
        return False
    for ln in lines:
        if not ln.endswith("]"):
            return False
        if not _CITATION_RE.search(ln):
            return False
    return True

