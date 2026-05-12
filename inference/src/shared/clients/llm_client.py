from __future__ import annotations

import asyncio
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import httpx

from src.config import Settings
from src.shared.llm_turn_trace import record_llm_call
from src.shared.logging import get_logger, timer
from src.shared.provider_cooldown import ProviderCooldownRegistry
from src.shared.stream_context import get_answer_stream_sink

logger = get_logger("sloww.inference.llm")

# Retry configuration for transient errors (429, 503, etc.)
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BACKOFF_BASE_SECONDS = 1.0


def _is_retryable_status(status: int) -> bool:
    """HTTP status codes that warrant a retry with exponential backoff."""
    return status in (429, 500, 502, 503, 504)


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: int


class LLMClient:
    """LLM client with a provider chain (``LLM_PROVIDER_CHAIN`` or ``LLM_ROUTER_CHAIN``)."""

    def __init__(
        self,
        *,
        settings: Settings,
        chain_role: Literal["generation", "router"] = "generation",
        provider_cooldown: ProviderCooldownRegistry | None = None,
    ) -> None:
        self._groq_key = settings.groq_api_key
        self._openrouter_key = settings.openrouter_api_key
        self._google_key = settings.google_ai_api_key
        self._openrouter_base = settings.openrouter_base_url.rstrip("/")
        if chain_role == "router":
            csv = (settings.llm_router_chain or settings.llm_provider_chain).strip()
            google_model = settings.llm_router_google_model or settings.llm_google_model
        else:
            csv = settings.llm_provider_chain.strip()
            google_model = settings.llm_google_model
        self._chain = _parse_provider_chain(
            settings, chain_csv=csv, google_model=google_model
        )
        self._cooldown = provider_cooldown or ProviderCooldownRegistry(
            cooldown_seconds=settings.provider_failure_cooldown_seconds
        )
        # One client per process: ``google-genai`` ``Client()`` is not free to construct,
        # and reusing it matches typical SDK usage.
        self._google_genai_client: Any = None
        if self._google_key:
            from google import genai

            self._google_genai_client = genai.Client(api_key=self._google_key)

        _llm_timeout = httpx.Timeout(60.0)
        self._http_groq = httpx.AsyncClient(timeout=_llm_timeout) if self._groq_key else None
        self._http_openrouter = httpx.AsyncClient(timeout=_llm_timeout) if self._openrouter_key else None

    def _effective_chain(self) -> list[tuple[str, str]]:
        """Try healthy providers first; if all are in cooldown, try the full chain."""
        available = [(p, m) for p, m in self._chain if not self._cooldown.should_skip(p)]
        return available if available else list(self._chain)

    async def aclose(self) -> None:
        for c in (self._http_groq, self._http_openrouter):
            if c is not None:
                await c.aclose()

    async def complete(self, *, prompt: str, stream_final_answer: bool = False) -> LLMResult:
        last_err: Exception | None = None
        sink = get_answer_stream_sink() if stream_final_answer else None
        chain = self._effective_chain()
        for provider, model in chain:
            # Inner retry loop for rate-limit / transient errors on this provider.
            for attempt in range(1, _RATE_LIMIT_RETRIES + 1):
                try:
                    t = timer()
                    if provider == "groq":
                        if not self._groq_key or self._http_groq is None:
                            raise RuntimeError("GROQ_API_KEY not set")
                        text = await self._complete_openai_compat(
                            client=self._http_groq,
                            base_url="https://api.groq.com/openai/v1",
                            api_key=self._groq_key,
                            model=_strip_prefix(model, "groq:"),
                            prompt=prompt,
                        )
                        if sink:
                            await sink(text)
                    elif provider == "openrouter":
                        if not self._openrouter_key or self._http_openrouter is None:
                            raise RuntimeError("OPENROUTER_API_KEY not set")
                        text = await self._complete_openai_compat(
                            client=self._http_openrouter,
                            base_url=self._openrouter_base,
                            api_key=self._openrouter_key,
                            model=_strip_prefix(model, "openrouter:"),
                            prompt=prompt,
                            extra_headers={"HTTP-Referer": "https://sloww.local", "X-Title": "sloww-inference"},
                        )
                        if sink:
                            await sink(text)
                    else:
                        if not self._google_key:
                            raise RuntimeError("GOOGLE_API_KEY or GOOGLE_AI_API_KEY not set")
                        g_model = _strip_prefix(model, "google:")
                        if sink:
                            text = await self._complete_google_stream(
                                model=g_model, prompt=prompt, sink=sink
                            )
                        else:
                            text = await self._complete_google(model=g_model, prompt=prompt)

                    result = LLMResult(text=text, provider=provider, model=model, latency_ms=t.ms())
                    record_llm_call(provider=provider, model=model)
                    await self._cooldown.note_success(provider)
                    logger.info(
                        "llm_complete_ok",
                        extra={
                            "event": "llm_complete_ok",
                            "provider": provider,
                            "model": model,
                            "latency_ms": result.latency_ms,
                        },
                    )
                    return result
                except httpx.HTTPStatusError as e:
                    last_err = e
                    if _is_retryable_status(e.response.status_code) and attempt < _RATE_LIMIT_RETRIES:
                        wait_s = _RATE_LIMIT_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                        logger.warning(
                            "llm_provider_rate_limited_retrying",
                            extra={
                                "event": "llm_provider_rate_limited_retrying",
                                "provider": provider,
                                "model": model,
                                "status": e.response.status_code,
                                "attempt": attempt,
                                "wait_seconds": wait_s,
                            },
                        )
                        await asyncio.sleep(wait_s)
                        continue
                    # Not retryable or out of retries -> mark failure and move to next provider.
                    await self._cooldown.note_failure(provider)
                    logger.warning(
                        "llm_provider_failed",
                        extra={
                            "event": "llm_provider_failed",
                            "provider": provider,
                            "model": model,
                            "error_type": type(e).__name__,
                            "error_message": str(e)[:400],
                        },
                    )
                    break
                except Exception as e:
                    last_err = e
                    await self._cooldown.note_failure(provider)
                    logger.warning(
                        "llm_provider_failed",
                        extra={
                            "event": "llm_provider_failed",
                            "provider": provider,
                            "model": model,
                            "error_type": type(e).__name__,
                            "error_message": str(e)[:400],
                        },
                    )
                    break

        raise RuntimeError(f"all llm providers failed: {type(last_err).__name__}") from last_err

    async def _complete_openai_compat(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        url = base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}
        if extra_headers:
            headers.update(extra_headers)
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data: Any = r.json()
        return str(data["choices"][0]["message"]["content"])

    async def _complete_google(self, *, model: str, prompt: str) -> str:
        """Gemini / Gemma via ``google.genai`` (official client; sync in ``asyncio.to_thread``)."""
        client = self._google_genai_client
        if client is None:
            raise RuntimeError("GOOGLE_API_KEY or GOOGLE_AI_API_KEY not set")

        def _sync() -> str:
            from google.genai import types as genai_types

            # Default AFC (automatic function calling) allows up to 10 extra remote turns
            # even when we pass no tools — that inflates latency vs. legacy ``generativeai``.
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
                        disable=True,
                    ),
                ),
            )
            if not response.candidates:
                fb = getattr(response, "prompt_feedback", None)
                raise RuntimeError(f"Gemini returned no candidates (blocked or error): {fb}")
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("Gemini returned empty text")
            return text

        return await asyncio.to_thread(_sync)

    async def _complete_google_stream(
        self,
        *,
        model: str,
        prompt: str,
        sink: Callable[[str], Awaitable[None]],
    ) -> str:
        """Stream completion tokens via ``client.aio`` (used for final user-visible answers)."""
        client = self._google_genai_client
        if client is None:
            raise RuntimeError("GOOGLE_API_KEY or GOOGLE_AI_API_KEY not set")
        from google.genai import types as genai_types

        config = genai_types.GenerateContentConfig(
            temperature=0.2,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
                disable=True,
            ),
        )
        stream = await client.aio.models.generate_content_stream(
            model=model,
            contents=prompt,
            config=config,
        )
        parts: list[str] = []
        async for chunk in stream:
            if not chunk.text:
                continue
            piece = chunk.text
            parts.append(piece)
            await sink(piece)
        out = "".join(parts).strip()
        if not out:
            raise RuntimeError("Gemini returned empty text (stream)")
        return out


def _strip_prefix(model: str, prefix: str) -> str:
    return model[len(prefix) :] if model.startswith(prefix) else model


def _parse_provider_chain(
    settings: Settings,
    *,
    chain_csv: str,
    google_model: str,
) -> list[tuple[str, str]]:
    models: dict[str, str] = {
        "groq": settings.llm_primary_model,
        "openrouter": settings.llm_openrouter_model,
        "google": google_model,
    }
    order = [p.strip().lower() for p in chain_csv.split(",") if p.strip()]
    out: list[tuple[str, str]] = []
    for p in order:
        if p == "groq" and not settings.groq_api_key:
            logger.info(
                "llm_chain_skip",
                extra={"event": "llm_chain_skip", "provider": "groq", "reason": "no_groq_api_key"},
            )
            continue
        if p == "openrouter" and not settings.openrouter_api_key:
            logger.info(
                "llm_chain_skip",
                extra={"event": "llm_chain_skip", "provider": "openrouter", "reason": "no_openrouter_api_key"},
            )
            continue
        if p == "google" and not settings.google_ai_api_key:
            logger.info(
                "llm_chain_skip",
                extra={"event": "llm_chain_skip", "provider": "google", "reason": "no_google_api_key"},
            )
            continue
        if p not in models:
            logger.warning(
                "llm_provider_chain_unknown",
                extra={"event": "llm_provider_chain_unknown", "provider": p},
            )
            continue
        out.append((p, models[p]))
    if not out:
        raise ValueError(
            "LLM provider chain must list at least one of: groq, openrouter, google"
        )
    return out
