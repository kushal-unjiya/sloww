from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from src.config import Settings
from src.shared.logging import get_logger, timer
from src.shared.provider_cooldown import ProviderCooldownRegistry

logger = get_logger("sloww.inference.embedding")

# Retry configuration for transient errors (429, 503, etc.)
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BACKOFF_BASE_SECONDS = 1.0


def _is_retryable_status(status: int) -> bool:
    return status in (429, 500, 502, 503, 504)


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    provider: str
    model: str
    dim: int


class EmbeddingClient:
    """Embedding client enforcing a single model invariant.

    Provider chain: Nvidia NIM -> OpenRouter -> HuggingFace (Inference API).
    """

    _PROVIDER_ORDER: tuple[str, ...] = ("nvidia_nim", "openrouter", "huggingface")

    def __init__(
        self,
        *,
        settings: Settings,
        provider_cooldown: ProviderCooldownRegistry | None = None,
    ) -> None:
        self._model = settings.embedding_model
        self._nvidia_key = settings.nvidia_nim_api_key
        self._nvidia_base = settings.nvidia_nim_base_url.rstrip("/")
        self._openrouter_key = settings.openrouter_api_key
        self._openrouter_base = settings.openrouter_base_url.rstrip("/")
        self._hf_key = settings.hf_api_key
        self._cooldown = provider_cooldown or ProviderCooldownRegistry(
            cooldown_seconds=settings.provider_failure_cooldown_seconds
        )
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    def _effective_providers(self) -> tuple[str, ...]:
        """Try embeddings from healthy providers first; if all cooled down, retry all."""
        available = tuple(p for p in self._PROVIDER_ORDER if not self._cooldown.should_skip(p))
        return available if available else self._PROVIDER_ORDER

    @property
    def model(self) -> str:
        return self._model

    async def aclose(self) -> None:
        await self._http.aclose()

    async def embed(self, text: str) -> EmbeddingResult:
        last_err: Exception | None = None

        for provider in self._effective_providers():
            for attempt in range(1, _RATE_LIMIT_RETRIES + 1):
                try:
                    t = timer()
                    if provider == "nvidia_nim":
                        if not self._nvidia_key:
                            raise RuntimeError("NVIDIA_NIM_API_KEY not set")
                        vec = await self._embed_nvidia(text)
                    elif provider == "openrouter":
                        if not self._openrouter_key:
                            raise RuntimeError("OPENROUTER_API_KEY not set (embedding fallback)")
                        vec = await self._embed_openrouter(text)
                    else:
                        if not self._hf_key:
                            raise RuntimeError("HF_API_KEY not set")
                        vec = await self._embed_hf(text)

                    dim = len(vec)
                    await self._cooldown.note_success(provider)
                    logger.info(
                        "embedding_ok",
                        extra={
                            "event": "embedding_ok",
                            "substage": "embedding",
                            "provider": provider,
                            "model": self._model,
                            "latency_ms": t.ms(),
                            "embedding_dim": dim,
                        },
                    )
                    return EmbeddingResult(vector=vec, provider=provider, model=self._model, dim=dim)
                except httpx.HTTPStatusError as e:
                    last_err = e
                    if _is_retryable_status(e.response.status_code) and attempt < _RATE_LIMIT_RETRIES:
                        wait_s = _RATE_LIMIT_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                        logger.warning(
                            "embedding_provider_rate_limited_retrying",
                            extra={
                                "event": "embedding_provider_rate_limited_retrying",
                                "provider": provider,
                                "model": self._model,
                                "status": e.response.status_code,
                                "attempt": attempt,
                                "wait_seconds": wait_s,
                            },
                        )
                        await asyncio.sleep(wait_s)
                        continue
                    await self._cooldown.note_failure(provider)
                    logger.warning(
                        "embedding_provider_failed",
                        extra={
                            "event": "embedding_provider_failed",
                            "substage": "embedding",
                            "provider": provider,
                            "model": self._model,
                            "error_type": type(e).__name__,
                        },
                    )
                    break
                except Exception as e:
                    last_err = e
                    await self._cooldown.note_failure(provider)
                    logger.warning(
                        "embedding_provider_failed",
                        extra={
                            "event": "embedding_provider_failed",
                            "substage": "embedding",
                            "provider": provider,
                            "model": self._model,
                            "error_type": type(e).__name__,
                        },
                    )
                    break

        raise RuntimeError(f"all embedding providers failed: {type(last_err).__name__}") from last_err

    async def _embed_nvidia(self, text: str) -> list[float]:
        url = f"{self._nvidia_base}/embeddings"
        headers = {"Authorization": f"Bearer {self._nvidia_key}"}
        body: dict[str, Any] = {"model": self._model, "input": text}
        if "nemotron" in self._model.lower():
            body["input_type"] = "query"
            body["encoding_format"] = "float"
            body["truncate"] = "END"
        return await self._openai_compat_embedding(url=url, headers=headers, body=body)

    async def _embed_openrouter(self, text: str) -> list[float]:
        url = f"{self._openrouter_base}/embeddings"
        headers = {"Authorization": f"Bearer {self._openrouter_key}"}
        body = {"model": self._model, "input": text}
        return await self._openai_compat_embedding(url=url, headers=headers, body=body)

    async def _embed_hf(self, text: str) -> list[float]:
        # HuggingFace Inference API (feature-extraction).
        url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self._model}"
        headers = {"Authorization": f"Bearer {self._hf_key}"}
        r = await self._http.post(url, headers=headers, json={"inputs": text})
        r.raise_for_status()
        data: Any = r.json()
        # Many HF embedding pipelines return nested lists (tokens x dim). We pool mean.
        if isinstance(data, list) and data and isinstance(data[0], list):
            if data and data[0] and isinstance(data[0][0], (int, float)):
                # single vector
                return [float(x) for x in data[0]]
            # token vectors -> mean pool
            token_vecs = [[float(x) for x in row] for row in data]
            dim = len(token_vecs[0])
            sums = [0.0] * dim
            for row in token_vecs:
                for i, x in enumerate(row):
                    sums[i] += x
            return [s / max(len(token_vecs), 1) for s in sums]
        raise ValueError("unexpected HF embedding response shape")

    async def _openai_compat_embedding(
        self, *, url: str, headers: dict[str, str], body: dict[str, Any]
    ) -> list[float]:
        r = await self._http.post(url, headers=headers, json=body)
        r.raise_for_status()
        data: Any = r.json()
        vec = data["data"][0]["embedding"]
        return [float(x) for x in vec]
