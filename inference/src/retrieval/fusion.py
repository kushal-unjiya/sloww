from __future__ import annotations

from collections import defaultdict

from src.graph.state import Chunk


class ReciprocallRankFusion:
    def __call__(self, *, dense: list[Chunk], sparse: list[Chunk], k: int = 60) -> list[Chunk]:
        # Pure merge: score = Σ 1/(rank + k).
        scores: dict[str, float] = defaultdict(float)
        by_id: dict[str, Chunk] = {}

        for lst in (dense, sparse):
            for rank, c in enumerate(lst, start=1):
                scores[c.chunk_id] += 1.0 / (rank + k)
                by_id[c.chunk_id] = c

        merged = sorted(by_id.values(), key=lambda c: scores[c.chunk_id], reverse=True)
        # Store fused score in `score` for downstream rerank input.
        out: list[Chunk] = []
        for c in merged:
            out.append(c.model_copy(update={"score": float(scores[c.chunk_id])}))
        return out

