from __future__ import annotations

from dataclasses import dataclass

from sentence_transformers import CrossEncoder

from src.graph.state import Chunk
from src.shared.logging import get_logger, log_event, timer

logger = get_logger("sloww.inference.reranker")


@dataclass
class CrossEncoderReranker:
    model_name: str

    def __post_init__(self) -> None:
        t = timer()
        self._model = CrossEncoder(self.model_name)
        logger.info(
            "cross_encoder_loaded",
            extra={"event": "cross_encoder_loaded", "model": self.model_name, "latency_ms": t.ms()},
        )

    def rerank(self, *, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]:
        t = timer()
        pairs = [(query, c.raw_text) for c in chunks[:top_n]]
        scores = self._model.predict(pairs)
        rescored: list[Chunk] = []
        for c, s in zip(chunks[:top_n], scores, strict=False):
            rescored.append(c.model_copy(update={"score": float(s)}))
        rescored.sort(key=lambda c: c.score, reverse=True)
        logger.info(
            "cross_encoder_rerank",
            extra={
                "event": "cross_encoder_rerank",
                "substage": "cross_encoder_rerank",
                "model": self.model_name,
                "latency_ms": t.ms(),
                "input_count": min(len(chunks), top_n),
                "output_count": len(rescored),
            },
        )
        log_event(
            logger,
            "cross_encoder_rerank",
            model=self.model_name,
            input_count=min(len(chunks), top_n),
            output_count=len(rescored),
            top_chunk_ids=[c.chunk_id for c in rescored[:5]],
            top_scores=[round(c.score, 4) for c in rescored[:5]],
        )
        return rescored
