from __future__ import annotations

from dataclasses import dataclass

import httpx

from api.config import Settings
from api.shared.db import check_database
from api.shared.logging import get_logger, timer

logger = get_logger("sloww.startup")


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool | None  # None = skipped
    detail: str
    elapsed_ms: int


async def _http_probe(
    *, name: str, base_url: str | None, timeout_s: float
) -> CheckResult:
    if not base_url:
        return CheckResult(name=name, ok=None, detail="skipped (url not set)", elapsed_ms=0)

    url = base_url.rstrip("/") + "/health"
    t = timer()
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url)
        ok = 200 <= r.status_code < 300
        return CheckResult(
            name=name,
            ok=ok,
            detail=f"GET /health -> {r.status_code}",
            elapsed_ms=t.ms(),
        )
    except Exception as e:
        return CheckResult(
            name=name,
            ok=False,
            detail=f"GET /health failed: {type(e).__name__}",
            elapsed_ms=t.ms(),
        )


async def run_startup_checks(settings: Settings) -> list[CheckResult]:
    results: list[CheckResult] = []

    # DB readiness (sync)
    t = timer()
    ok = check_database()
    results.append(
        CheckResult(
            name="database",
            ok=ok,
            detail="SELECT 1" if ok else "not ready",
            elapsed_ms=t.ms(),
        )
    )

    # External/service probes (async, best-effort)
    timeout_s = settings.startup_probe_timeout_seconds
    results.append(
        await _http_probe(name="inference", base_url=settings.inference_url, timeout_s=timeout_s)
    )
    results.append(await _http_probe(name="ui", base_url=settings.ui_url, timeout_s=timeout_s))
    results.append(
        await _http_probe(name="data_loader", base_url=settings.data_loader_url, timeout_s=timeout_s)
    )

    for r in results:
        if r.ok is True:
            logger.info("startup_check_ok name=%s detail=%s elapsed_ms=%s", r.name, r.detail, r.elapsed_ms)
        elif r.ok is None:
            logger.info("startup_check_skip name=%s detail=%s", r.name, r.detail)
        else:
            logger.warning(
                "startup_check_fail name=%s detail=%s elapsed_ms=%s",
                r.name,
                r.detail,
                r.elapsed_ms,
            )

    return results

