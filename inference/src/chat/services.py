from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from src.agent.events import agent_event_sink
from src.chat.repository import RetrievalCacheRepository
from src.chat.responses import FinalSSEEvent, StreamChunk
from src.graph.state import FinalResponse, GraphState
from src.orchestration.nodes import _heuristic_chitchat_intent, format_user_facing_preamble
from src.shared.llm_turn_trace import begin_llm_turn_trace, snapshot_llm_calls
from src.shared.logging import get_logger, log_event, timer
from src.shared.request_context import set_request_id
from src.shared.stream_context import answer_stream_sink
from src.shared.turn_timing import (
    begin_turn_timeline,
    snapshot_turn_timeline,
    timeline_segments,
)

logger = get_logger("sloww.inference.chat.service")

_GRAPH_USER_MESSAGES: dict[str, str] = {
    "base_query_processor": "Analyzing your question and deciding whether project sources are needed…",
    "retrieval_engine": "Searching sources in your project for evidence that can support the answer…",
    "orchestrator": "Reviewing the retrieved evidence and choosing the next step in the answer plan…",
    "aggregator": "Comparing documents and consolidating agreement or conflict points…",
    "cited_summary_generator": "Writing a grounded answer with citations from the retrieved chunks…",
    "normal_text_generator": "Composing a direct reply with enough detail to be useful…",
    "visualizer": "Turning the answer into chart-ready data when the question calls for it…",
    "response_assembler": "Packing the final answer, citations, warnings, and chart data together…",
}
_GRAPH_TRACE_REASONS: dict[str, str] = {
    "base_query_processor": "Classifies the request and prepares the retrieval path only when the question depends on project sources.",
    "retrieval_engine": "Looks for source chunks that can support the answer and feeds them back into the graph.",
    "orchestrator": "Checks whether the evidence is sufficient, then chooses between retrieval, synthesis, or a direct answer.",
    "aggregator": "Merges evidence across documents so conflicts and agreements can be summarized cleanly.",
    "cited_summary_generator": "Drafts an answer from retrieved chunks and keeps every claim tied to a citation.",
    "normal_text_generator": "Responds directly when retrieval is unnecessary, while still keeping the answer readable.",
    "visualizer": "Converts the answer into chart-ready data when the request has a visual structure.",
    "response_assembler": "Collects the final answer text, citations, warnings, and chart payload into the response object.",
}
_HEARTBEAT_MESSAGES = (
    "Still working through the evidence and checking for missing context…",
    "Checking whether the retrieved context is enough to support a fuller answer…",
    "Keeping the answer grounded in your sources while the final draft is assembled…",
)
_GRAPH_NODES = frozenset(_GRAPH_USER_MESSAGES)

_STREAM_END = object()
_EXTREME_FALLBACK = (
    "I ran into a temporary issue while generating the answer. "
    "The retrieval step may have completed, but the language model did not return usable text. "
    "Please try again in a moment."
)


def _sse(data: dict) -> str:
    return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


@dataclass(frozen=True)
class ChatService:
    graph: Any
    repository: RetrievalCacheRepository

    def _canned_chitchat_response(self, query: str) -> str:
        q = query.strip().lower()
        if q.startswith(("hi", "hello", "hey", "yo", "hiya", "sup")):
            return "Hello! How can I help you today?"
        if "how are you" in q:
            return "I’m doing well. How can I help you today?"
        if "thank" in q:
            return "You’re welcome!"
        if q.startswith(("bye", "goodbye")):
            return "Goodbye! Come back anytime."
        return "Hi! How can I help?"

    async def _consume_graph_for_stream(
        self,
        *,
        input_dict: dict[str, Any],
        out_queue: asyncio.Queue[tuple[str, Any] | object],
    ) -> GraphState:
        final_state: GraphState | None = None
        async for ev in self.graph.astream_events(input_dict, version="v2"):
            et = ev.get("event")
            name = ev.get("name")
            if et == "on_chain_start" and name in _GRAPH_NODES:
                await out_queue.put(
                    (
                        "sse",
                        _sse(
                            {
                                "type": "trace",
                                "phase": "start",
                                "action": name,
                                "message": _GRAPH_USER_MESSAGES[name],
                                "reason": _GRAPH_TRACE_REASONS.get(name),
                            }
                        ),
                    )
                )
                await out_queue.put(
                    (
                        "sse",
                        _sse(
                            {
                                "type": "status",
                                "phase": "start",
                                "node": name,
                                "message": _GRAPH_USER_MESSAGES[name],
                            }
                        ),
                    )
                )
            elif et == "on_chain_end" and name in _GRAPH_NODES:
                await out_queue.put(
                    (
                        "sse",
                        _sse(
                            {
                                "type": "trace",
                                "phase": "end",
                                "action": name,
                                "message": _GRAPH_USER_MESSAGES[name],
                                "reason": _GRAPH_TRACE_REASONS.get(name),
                                "llm_calls": snapshot_llm_calls(),
                            }
                        ),
                    )
                )
                await out_queue.put(
                    (
                        "sse",
                        _sse(
                            {
                                "type": "status",
                                "phase": "end",
                                "node": name,
                                "message": _GRAPH_USER_MESSAGES[name],
                                "llm_calls": snapshot_llm_calls(),
                            }
                        ),
                    )
                )
            elif et == "on_chain_end" and name == "LangGraph":
                out = (ev.get("data") or {}).get("output")
                if isinstance(out, dict):
                    try:
                        final_state = GraphState.model_validate(out)
                    except Exception:
                        logger.exception(
                            "graph_output_validate_failed",
                            extra={"event": "graph_output_validate_failed"},
                        )

        if final_state is None:
            logger.warning(
                "astream_events_no_final_state_using_ainvoke",
                extra={"event": "chat_stream_fallback_ainvoke"},
            )
            out = await self.graph.ainvoke(input_dict)
            final_state = GraphState.model_validate(out)

        return final_state

    async def stream_chat(
        self,
        *,
        query: str,
        conversation_id: str,
        notebook_id: str,
        request_id: str,
        user_id: str | None,
    ) -> AsyncGenerator[str, None]:
        t = timer()
        t_wall0 = time.perf_counter()
        set_request_id(request_id)
        logger.info(
            "chat_turn_start",
            extra={
                "event": "chat_turn_start",
                "conversation_id": conversation_id,
                "notebook_id": notebook_id,
                "query_preview": query[:200],
            },
        )
        log_event(
            logger,
            "chat_turn_start",
            request_id=request_id,
            conversation_id=conversation_id,
            notebook_id=notebook_id,
            user_id=user_id,
            query_length=len(query),
            query_preview=query[:160],
        )

        normalized_query = query.strip()
        heuristic_intent = _heuristic_chitchat_intent(normalized_query)
        log_event(
            logger,
            "chat_turn_router",
            request_id=request_id,
            query_preview=normalized_query[:160],
            heuristic_hit=heuristic_intent is not None,
            intent=(heuristic_intent.model_dump() if heuristic_intent is not None else None),
        )
        if heuristic_intent is not None:
            response_text = self._canned_chitchat_response(normalized_query)
            final_state = GraphState(
                raw_query=query,
                session_id=conversation_id,
                notebook_id=notebook_id,
                request_id=request_id,
                normalized_query=normalized_query,
                intent=heuristic_intent,
                final_response=FinalResponse(answer_text=response_text, citations=[], stream_ready=True),
            )

            logger.info(
                "chat_turn_fastpath_chitchat",
                extra={
                    "event": "chat_turn_fastpath_chitchat",
                    "conversation_id": conversation_id,
                    "notebook_id": notebook_id,
                    "response_preview": response_text[:120],
                },
            )
            log_event(
                logger,
                "chat_turn_fastpath_chitchat",
                request_id=request_id,
                conversation_id=conversation_id,
                notebook_id=notebook_id,
                response_preview=response_text[:120],
            )

            yield _sse(
                {
                    "type": "status",
                    "phase": "start",
                    "node": "chat",
                    "message": format_user_facing_preamble(heuristic_intent, query),
                }
            )
            yield _sse(
                {
                    "type": "trace",
                    "phase": "end",
                    "action": "direct_answer",
                    "message": "Answered directly",
                    "reason": "The message is conversational and does not need document retrieval.",
                }
            )
            yield _sse({"type": "token", "content": response_text})
            yield _sse(
                {
                    "type": "done",
                    "citations": [],
                    "chart_payload": None,
                    "warning": None,
                    "llm_calls": [],
                    "latency_seconds": 0.0,
                }
            )
            try:
                await self.repository.insert_turn_audit(user_id=user_id, state=final_state)
            except Exception as exc:
                logger.exception(
                    "retrieval_cache_insert_failed",
                    extra={
                        "event": "retrieval_cache_insert_failed",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    },
                )
            return

        state = GraphState(
            raw_query=query,
            session_id=conversation_id,
            notebook_id=notebook_id,
            request_id=request_id,
        )
        input_dict = state.model_dump()

        begin_llm_turn_trace()
        begin_turn_timeline()
        log_event(
            logger,
            "chat_turn_pipeline_begin",
            request_id=request_id,
            conversation_id=conversation_id,
            notebook_id=notebook_id,
            preamble=format_user_facing_preamble(state.intent, query),
        )

        out_queue: asyncio.Queue[tuple[str, Any] | object] = asyncio.Queue()
        streamed_word_chunks = [0]

        async def sink(chunk: str) -> None:
            streamed_word_chunks[0] += 1
            await out_queue.put(("tok", chunk))

        async def agent_sink(event: dict[str, Any]) -> None:
            log_payload = {
                **event,
                "agent_message": event.get("message"),
            }
            log_payload.pop("message", None)
            logger.info(
                "agent_trace",
                extra={
                    "event": "agent_trace",
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    **log_payload,
                },
            )
            await out_queue.put(("sse", _sse({"type": "agent_trace", **event})))

        ctx_token = answer_stream_sink.set(sink)
        agent_ctx_token = agent_event_sink.set(agent_sink)
        final_box: list[GraphState | None] = [None]
        err_box: list[BaseException | None] = [None]

        async def worker() -> None:
            try:
                final_box[0] = await self._consume_graph_for_stream(
                    input_dict=input_dict,
                    out_queue=out_queue,
                )
            except BaseException as e:
                err_box[0] = e
            finally:
                await out_queue.put(_STREAM_END)

        yield _sse(
            {
                "type": "status",
                "phase": "start",
                "node": "chat",
                "message": format_user_facing_preamble(state.intent, query),
            }
        )
        yield _sse(
            {
                "type": "trace",
                "phase": "start",
                "action": "turn",
                "message": "Starting a grounded answer",
                "reason": "This query may need information from project sources.",
            }
        )

        task = asyncio.create_task(worker())
        heartbeat_idx = 0
        try:
            while True:
                try:
                    item = await asyncio.wait_for(out_queue.get(), timeout=4.0)
                except asyncio.TimeoutError:
                    yield _sse(
                        {
                            "type": "status",
                            "phase": "progress",
                            "node": "chat",
                            "message": _HEARTBEAT_MESSAGES[heartbeat_idx % len(_HEARTBEAT_MESSAGES)],
                        }
                    )
                    heartbeat_idx += 1
                    continue
                if item is _STREAM_END:
                    break
                kind, payload = item  # type: ignore[assignment,misc]
                if kind == "tok":
                    yield _sse({"type": "token", "content": payload})
                elif kind == "sse":
                    yield payload
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})
            raise
        finally:
            await task
            answer_stream_sink.reset(ctx_token)
            agent_event_sink.reset(agent_ctx_token)

        if err_box[0] is not None:
            err = err_box[0]
            logger.exception(
                "chat_turn_failed_degraded",
                exc_info=err,
                extra={
                    "event": "chat_turn_failed_degraded",
                    "request_id": request_id,
                    "error_type": type(err).__name__,
                    "error_message": str(err)[:500],
                },
            )
            log_event(
                logger,
                "chat_turn_failed_degraded",
                request_id=request_id,
                conversation_id=conversation_id,
                notebook_id=notebook_id,
                error_type=type(err).__name__,
                error_message=str(err)[:500],
            )
            yield _sse(
                {
                    "type": "trace",
                    "phase": "end",
                    "action": "fallback",
                    "message": "Recovered with a fallback response",
                    "reason": "The agent hit an unrecoverable generation error, so it is returning a safe explanation instead of leaving the chat hanging.",
                }
            )
            yield _sse(
                {
                    "type": "error",
                    "message": _EXTREME_FALLBACK,
                    "error_type": type(err).__name__,
                    "recoverable": True,
                }
            )
            yield _sse({"type": "token", "content": _EXTREME_FALLBACK})
            yield _sse(
                {
                    "type": "done",
                    "citations": [],
                    "chart_payload": None,
                    "warning": "generation_failed_degraded",
                    "llm_calls": snapshot_llm_calls(),
                    "latency_seconds": round(time.perf_counter() - t_wall0, 2),
                }
            )
            return

        final_state = final_box[0]
        if final_state is None:
            raise RuntimeError("graph produced no final state")

        answer = (final_state.final_response.answer_text if final_state.final_response else "") or ""
        log_event(
            logger,
            "chat_turn_final_state",
            request_id=request_id,
            answer_length=len(answer),
            citations_count=len(final_state.final_response.citations if final_state.final_response else []),
            warning=(final_state.final_response.warning if final_state.final_response else None),
            stream_ready=(final_state.final_response.stream_ready if final_state.final_response else None),
        )

        token_count = 0
        if streamed_word_chunks[0] == 0:
            for tok in answer.split(" "):
                token_count += 1
                chunk = StreamChunk(token=tok + " ")
                yield _sse({"type": "token", "content": chunk.token})
                logger.debug(
                    "stream_token",
                    extra={"event": "stream_token", "cumulative_tokens": token_count},
                )
        else:
            token_count = len(answer.split())

        elapsed_s = time.perf_counter() - t_wall0
        all_llm = snapshot_llm_calls()
        final_event = FinalSSEEvent(
            done=True,
            citations=(final_state.final_response.citations if final_state.final_response else []),
            chart_payload=(final_state.final_response.chart_payload if final_state.final_response else None),
            warning=(final_state.final_response.warning if final_state.final_response else None),
            llm_calls=all_llm,
            latency_seconds=round(elapsed_s, 2),
        )
        yield _sse({"type": "done", **final_event.model_dump()})

        try:
            await self.repository.insert_turn_audit(user_id=user_id, state=final_state)
        except Exception as exc:
            logger.exception(
                "retrieval_cache_insert_failed",
                extra={
                    "event": "retrieval_cache_insert_failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )

        marks = snapshot_turn_timeline()
        logger.info(
            "chat_turn_end",
            extra={
                "event": "chat_turn_end",
                "latency_ms": t.ms(),
                "latency_seconds": round(elapsed_s, 3),
                "token_count": token_count,
                "citations_count": len(final_event.citations),
                "llm_call_count": len(all_llm),
                "streamed_chunks": streamed_word_chunks[0],
                "timeline": marks,
                "phase_breakdown": timeline_segments(marks),
            },
        )
        log_event(
            logger,
            "chat_turn_end",
            request_id=request_id,
            latency_ms=t.ms(),
            latency_seconds=round(elapsed_s, 3),
            token_count=token_count,
            citations_count=len(final_event.citations),
            llm_call_count=len(all_llm),
            streamed_chunks=streamed_word_chunks[0],
            phase_breakdown=timeline_segments(marks),
        )


def get_chat_service(request: Request) -> ChatService:
    graph: Any = request.app.state.graph
    repo: RetrievalCacheRepository = request.app.state.retrieval_cache_repo
    return ChatService(graph=graph, repository=repo)
