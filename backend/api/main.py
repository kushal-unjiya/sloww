from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response as StarletteResponse

from api.chat.routes import router as chat_router
from api.config import get_settings
from api.documents.routes import router as documents_router
from api.projects.routes import router as projects_router
from api.shared.db import check_database, dispose_db, init_db
from api.shared.logging import configure_logging, get_logger, timer, unify_third_party_loggers
from api.shared.startup_checks import run_startup_checks
from api.uploads.routes import router as uploads_router
from api.user.routes import router as user_router

logger = get_logger("sloww.http")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> StarletteResponse:
        rid = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = rid
        t = timer()

        logger.debug(
            "request_started request_id=%s method=%s path=%s client=%s",
            rid,
            request.method,
            request.url.path,
            request.client.host if request.client else None,
        )
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed request_id=%s method=%s path=%s elapsed_ms=%s",
                rid,
                request.method,
                request.url.path,
                t.ms(),
            )
            raise

        response.headers["x-request-id"] = rid
        logger.info(
            "request_finished request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
            rid,
            request.method,
            request.url.path,
            response.status_code,
            t.ms(),
        )
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    unify_third_party_loggers()
    get_logger("sloww.lifecycle").info("backend_starting")
    init_db()
    settings = get_settings()
    await run_startup_checks(settings)
    yield
    dispose_db()
    get_logger("sloww.lifecycle").info("backend_stopped")


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    application = FastAPI(title="Sloww API", lifespan=lifespan)
    application.add_middleware(RequestLogMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready", response_model=None)
    def ready() -> Response:
        if check_database():
            return JSONResponse({"status": "ready"})
        return JSONResponse(
            status_code=503, content={"status": "not ready"}
        )

    application.include_router(user_router)
    application.include_router(uploads_router)
    application.include_router(projects_router)
    application.include_router(documents_router)
    application.include_router(chat_router)
    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
