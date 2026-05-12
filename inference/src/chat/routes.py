from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from src.chat.responses import ChatRequest
from src.chat.services import ChatService, get_chat_service
from src.config import get_settings
from src.shared.logging import get_logger
from src.shared.request_context import set_request_id

logger = get_logger("sloww.inference.chat.routes")

router = APIRouter(prefix="/chat", tags=["chat"])


def _require_internal_auth(authorization: str | None) -> str | None:
    settings = get_settings()
    if settings.internal_token is None:
        return None
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.internal_token:
        raise HTTPException(status_code=403, detail="invalid token")
    return "internal"


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    service: ChatService = Depends(get_chat_service),
    authorization: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> StreamingResponse:
    user_id = _require_internal_auth(authorization)

    request_id = x_request_id or str(uuid.uuid4())
    set_request_id(request_id)

    logger.info(
        "chat_stream_request",
        extra={
            "event": "chat_stream_request",
            "request_id": request_id,
            "notebook_id": body.notebook_id,
            "conversation_id": body.conversation_id,
        },
    )

    gen = service.stream_chat(
        query=body.query,
        conversation_id=body.conversation_id,
        notebook_id=body.notebook_id,
        request_id=request_id,
        user_id=user_id,
    )

    return StreamingResponse(gen, media_type="text/event-stream")

