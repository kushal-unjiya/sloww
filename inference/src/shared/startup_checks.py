from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.config import Settings
from src.shared.clients.qdrant_client import QdrantClientWrapper
from src.shared.db import check_database
from src.shared.logging import get_logger, timer

logger = get_logger("sloww.inference.startup")


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    elapsed_ms: int


async def check_postgres() -> CheckResult:
    t = timer()
    ok = await check_database()
    return CheckResult(
        name="postgres",
        ok=ok,
        detail="SELECT 1" if ok else "not ready",
        elapsed_ms=t.ms(),
    )


async def check_qdrant(qdrant: QdrantClientWrapper) -> CheckResult:
    t = timer()
    try:
        # This will throw if unreachable.
        qdrant._client.get_collections()  # noqa: SLF001 - local wrapper use for probe
        return CheckResult(name="qdrant", ok=True, detail="get_collections ok", elapsed_ms=t.ms())
    except Exception as e:
        return CheckResult(name="qdrant", ok=False, detail=f"probe failed: {type(e).__name__}", elapsed_ms=t.ms())


async def check_llm_providers(settings: Settings) -> CheckResult:
    # Best-effort: validate credentials are present for at least one provider.
    t = timer()
    ok = bool(settings.groq_api_key or settings.openrouter_api_key or settings.google_ai_api_key)
    return CheckResult(
        name="llm_providers",
        ok=ok,
        detail="has at least one api key" if ok else "no llm api keys configured",
        elapsed_ms=t.ms(),
    )


async def check_cross_encoder_loaded(*, loaded: bool) -> CheckResult:
    t = timer()
    return CheckResult(
        name="cross_encoder",
        ok=loaded,
        detail="loaded" if loaded else "not loaded",
        elapsed_ms=t.ms(),
    )


async def run_startup_checks(
    *,
    settings: Settings,
    qdrant: QdrantClientWrapper,
    cross_encoder_loaded: bool,
) -> list[CheckResult]:
    results = [
        await check_postgres(),
        await check_qdrant(qdrant),
        await check_llm_providers(settings),
        await check_cross_encoder_loaded(loaded=cross_encoder_loaded),
    ]

    for r in results:
        if r.ok:
            logger.info(
                "startup_check_ok",
                extra={"event": "startup_check_ok", "check": r.name, "detail": r.detail, "latency_ms": r.elapsed_ms},
            )
        else:
            logger.error(
                "startup_check_fail",
                extra={"event": "startup_check_fail", "check": r.name, "detail": r.detail, "latency_ms": r.elapsed_ms},
            )

    # Hard-fail if core dependencies are down.
    if not all(r.ok for r in results if r.name in ("postgres", "qdrant", "cross_encoder")):
        raise RuntimeError("startup checks failed")

    return results

