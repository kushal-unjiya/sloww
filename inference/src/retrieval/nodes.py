from __future__ import annotations

import asyncio
from dataclasses import dataclass

from src.agent.events import emit_agent_event
from src.graph.state import GraphState
from src.retrieval.dense import QdrantRetriever
from src.retrieval.fusion import ReciprocallRankFusion
from src.retrieval.reranker import CrossEncoderReranker
from src.retrieval.sparse import BM25Retriever
from src.shared.logging import get_logger, log_event, timer
from src.shared.turn_timing import mark_turn_phase

logger = get_logger("sloww.inference.retrieval.engine")


@dataclass(frozen=True)
class RetrievalDeps:
    dense: QdrantRetriever
    sparse: BM25Retriever
    fusion: ReciprocallRankFusion
    reranker: CrossEncoderReranker


class RetrievalEngine:
    def __init__(self, *, deps: RetrievalDeps, top_k: int = 25) -> None:
        self._dense = deps.dense
        self._sparse = deps.sparse
        self._fusion = deps.fusion
        self._reranker = deps.reranker
        self._top_k = top_k

    async def __call__(self, state: GraphState) -> GraphState:
        t = timer()
        raw_q = state.normalized_query or state.raw_query
        hyde = state.expanded_query or state.normalized_query or state.raw_query

        await emit_agent_event(
            agent_id="retrieval-supervisor",
            label="Retrieval supervisor",
            role="supervisor",
            phase="start",
            message="Planning parallel dense and sparse source search.",
            input_preview=raw_q[:240],
            metadata={"notebook_id": state.notebook_id},
        )

        async def run_dense():
            await emit_agent_event(
                agent_id="dense-researcher",
                label="Dense researcher",
                role="researcher",
                phase="start",
                message="Searching semantic matches in vector storage.",
                input_preview=hyde[:240],
            )
            results = await self._dense(notebook_id=state.notebook_id, hyde_text=hyde)
            await emit_agent_event(
                agent_id="dense-researcher",
                label="Dense researcher",
                role="researcher",
                phase="end",
                message="Dense search completed.",
                output_preview=", ".join(c.chunk_id for c in results[:5]),
                metadata={"result_count": len(results)},
            )
            return results

        async def run_sparse():
            await emit_agent_event(
                agent_id="sparse-researcher",
                label="Sparse researcher",
                role="researcher",
                phase="start",
                message="Searching exact keyword and phrase matches.",
                input_preview=raw_q[:240],
            )
            try:
                results = await self._sparse(notebook_id=state.notebook_id, query=raw_q)
            except Exception as exc:
                logger.warning(
                    "sparse_retrieval_failed_degraded",
                    extra={
                        "event": "sparse_retrieval_failed_degraded",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    },
                )
                log_event(
                    logger,
                    "sparse_retrieval_failed_degraded",
                    query_preview=raw_q[:160],
                    notebook_id=state.notebook_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:500],
                )
                await emit_agent_event(
                    agent_id="sparse-researcher",
                    label="Sparse researcher",
                    role="researcher",
                    phase="error",
                    message="Sparse search failed; continuing with dense search results.",
                    output_preview=str(exc)[:240],
                    metadata={"error_type": type(exc).__name__},
                )
                return []
            await emit_agent_event(
                agent_id="sparse-researcher",
                label="Sparse researcher",
                role="researcher",
                phase="end",
                message="Sparse search completed.",
                output_preview=", ".join(c.chunk_id for c in results[:5]),
                metadata={"result_count": len(results)},
            )
            return results

        dense, sparse = await asyncio.gather(run_dense(), run_sparse())
        merged = self._fusion(dense=dense, sparse=sparse)
        await emit_agent_event(
            agent_id="retrieval-supervisor",
            label="Retrieval supervisor",
            role="supervisor",
            phase="progress",
            message="Merging and reranking retrieved evidence.",
            metadata={
                "dense_count": len(dense),
                "sparse_count": len(sparse),
                "merged_count": len(merged),
            },
        )
        reranked = self._reranker.rerank(query=raw_q, chunks=merged, top_n=min(len(merged), self._top_k))
        await emit_agent_event(
            agent_id="retrieval-supervisor",
            label="Retrieval supervisor",
            role="supervisor",
            phase="end",
            message="Evidence retrieval completed.",
            output_preview=", ".join(c.chunk_id for c in reranked[:5]),
            metadata={"final_count": len(reranked)},
        )

        logger.info(
            "retrieval_engine_done",
            extra={
                "event": "retrieval_engine_done",
                "node": "retrieval_engine",
                "latency_ms": t.ms(),
                "dense_count": len(dense),
                "sparse_count": len(sparse),
                "merged_count": len(merged),
                "final_count": len(reranked),
            },
        )
        log_event(
            logger,
            "retrieval_engine_done",
            query_preview=raw_q[:160],
            hyde_preview=hyde[:160],
            dense_count=len(dense),
            sparse_count=len(sparse),
            merged_count=len(merged),
            final_count=len(reranked),
            top_chunk_ids=[c.chunk_id for c in reranked[:5]],
            top_doc_ids=[c.doc_id for c in reranked[:5]],
        )
        mark_turn_phase(
            "retrieval_engine",
            latency_ms=t.ms(),
            final_count=len(reranked),
        )
        return state.model_copy(update={"retrieved_chunks": reranked})
