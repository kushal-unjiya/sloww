from __future__ import annotations

from src.orchestration.modules import CoverageScorer


class CoverageScorerBridge:
    def __init__(self, *, scorer: CoverageScorer) -> None:
        self._scorer = scorer

    async def __call__(self, *, query: str, chunks: list[str]) -> float:
        return float(await self._scorer(query=query, chunks=chunks))

