from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.chat.repository import RetrievalCacheRepository
from src.chat.routes import router as chat_router
from src.config import get_settings
from src.graph.builder import ChatGraphBuilder, GraphConfig
from src.shared.clients.embedding_client import EmbeddingClient
from src.shared.clients.llm_client import LLMClient
from src.shared.clients.qdrant_client import QdrantClientWrapper
from src.shared.db import dispose_db, get_engine, init_db
from src.shared.provider_cooldown import ProviderCooldownRegistry
from src.shared.logging import configure_logging, get_logger
from src.shared.request_context import set_request_id
from src.shared.startup_checks import run_startup_checks
from src.retrieval.reranker import CrossEncoderReranker

logger = get_logger("sloww.inference.main")


class RequestIdMiddleware:
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw = headers.get(b"x-request-id")
        request_id = raw.decode("utf-8") if raw else str(uuid.uuid4())
        set_request_id(request_id)

        async def _send(message):  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                hdrs = list(message.get("headers") or [])
                hdrs.append((b"x-request-id", request_id.encode("utf-8")))
                message["headers"] = hdrs
            await send(message)

        await self.app(scope, receive, _send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(level=settings.log_level)
    logger.info(
        "startup_llm_config provider_chain=%s google_model=%s router_google_model=%s",
        settings.llm_provider_chain,
        settings.llm_google_model,
        settings.llm_router_google_model,
    )

    init_db()
    pg_engine = get_engine()

    llm_cd = ProviderCooldownRegistry(cooldown_seconds=settings.provider_failure_cooldown_seconds)
    emb_cd = ProviderCooldownRegistry(cooldown_seconds=settings.provider_failure_cooldown_seconds)

    llm_generation = LLMClient(settings=settings, chain_role="generation", provider_cooldown=llm_cd)
    router_split = bool(
        (settings.llm_router_chain and settings.llm_router_chain.strip())
        or (settings.llm_router_google_model and settings.llm_router_google_model.strip())
    )
    if router_split:
        llm_router = LLMClient(settings=settings, chain_role="router", provider_cooldown=llm_cd)
        logger.info(
            "inference_llm_router_split",
            extra={
                "event": "inference_llm_router_split",
                "router_chain": settings.llm_router_chain or settings.llm_provider_chain,
                "generation_chain": settings.llm_provider_chain,
            },
        )
    else:
        llm_router = llm_generation

    embedding_client = EmbeddingClient(settings=settings, provider_cooldown=emb_cd)
    qdrant_client = QdrantClientWrapper(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection=settings.qdrant_collection,
    )

    # Load cross-encoder once.
    cross_encoder = CrossEncoderReranker(settings.cross_encoder_model)

    # Build graph once.
    graph = ChatGraphBuilder(
        config=GraphConfig(
            settings=settings,
            llm_client=llm_generation,
            llm_router=llm_router,
            embedding_client=embedding_client,
            qdrant_client=qdrant_client,
            pg_engine=pg_engine,
            cross_encoder=cross_encoder,
        )
    ).build()

    repo = RetrievalCacheRepository(engine=pg_engine)

    # Store on app.state for dependencies.
    app.state.settings = settings
    app.state.pg_engine = pg_engine
    app.state.llm_client = llm_generation
    app.state.embedding_client = embedding_client
    app.state.qdrant_client = qdrant_client
    app.state.cross_encoder = cross_encoder
    app.state.graph = graph
    app.state.retrieval_cache_repo = repo

    await run_startup_checks(settings=settings, qdrant=qdrant_client, cross_encoder_loaded=True)
    logger.info("inference_startup_complete", extra={"event": "inference_startup_complete"})

    try:
        yield
    finally:
        await embedding_client.aclose()
        await llm_generation.aclose()
        if router_split and llm_router is not llm_generation:
            await llm_router.aclose()
        await dispose_db()


app = FastAPI(title="sloww-inference", lifespan=lifespan)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": "inference"}


def run() -> None:
    uvicorn.run("src.main:app", host="0.0.0.0", port=8001, reload=False)

