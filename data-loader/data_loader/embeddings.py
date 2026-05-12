"""Sync embedding (same provider chain as inference EmbeddingClient)."""

from __future__ import annotations

from typing import Any, Literal

import httpx

from data_loader.config import Settings

InputType = Literal["passage", "query"]


def _openai_compat_embedding(url: str, headers: dict[str, str], body: dict[str, Any]) -> list[float]:
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, headers=headers, json=body)
    r.raise_for_status()
    data: Any = r.json()
    vec = data["data"][0]["embedding"]
    return [float(x) for x in vec]


def embed_text(
    text: str,
    settings: Settings,
    *,
    input_type: InputType = "passage",
) -> list[float]:
    """Embed text. Use ``input_type=passage`` for indexing; ``query`` for retrieval (NIM models)."""
    model = settings.embedding_model
    last_err: Exception | None = None

    for provider in ("nvidia_nim", "openrouter", "huggingface"):
        try:
            if provider == "nvidia_nim":
                if not settings.nvidia_nim_api_key:
                    raise RuntimeError("NVIDIA_NIM_API_KEY not set")
                url = f"{settings.nvidia_nim_base_url.rstrip('/')}/embeddings"
                headers = {"Authorization": f"Bearer {settings.nvidia_nim_api_key}"}
                # NIM llama-nemotron-embed-vl-* requires input_type (passage vs query).
                body: dict[str, Any] = {
                    "model": model,
                    "input": text,
                    "input_type": input_type,
                    "encoding_format": "float",
                    "truncate": "END",
                }
                return _openai_compat_embedding(url, headers, body)

            if provider == "openrouter":
                if not settings.openrouter_api_key:
                    raise RuntimeError("OPENROUTER_API_KEY not set")
                url = f"{settings.openrouter_base_url.rstrip('/')}/embeddings"
                headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
                body = {"model": model, "input": text}
                return _openai_compat_embedding(url, headers, body)

            if not settings.hf_api_key:
                raise RuntimeError("HF_API_KEY not set")
            hf_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model}"
            hf_headers = {"Authorization": f"Bearer {settings.hf_api_key}"}
            with httpx.Client(timeout=120.0) as client:
                r = client.post(hf_url, headers=hf_headers, json={"inputs": text})
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data and isinstance(data[0], list):
                if data and data[0] and isinstance(data[0][0], (int, float)):
                    return [float(x) for x in data[0]]
                token_vecs = [[float(x) for x in row] for row in data]
                dim = len(token_vecs[0])
                sums = [0.0] * dim
                for row in token_vecs:
                    for i, x in enumerate(row):
                        sums[i] += x
                return [s / max(len(token_vecs), 1) for s in sums]
            raise ValueError("unexpected HF embedding response shape")
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"all embedding providers failed: {last_err!r}") from last_err
