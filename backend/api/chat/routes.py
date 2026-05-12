"""HTTP routes for chat streaming relay + persistence (M3+)."""

from __future__ import annotations

import json
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.auth.deps import CurrentUser, get_current_user, get_settings_dep
from api.chat.repository import ChatRepository, get_chat_repo
from api.chat.responses import (
    ConversationListOut,
    ConversationOut,
    CreateConversationBody,
    MessageListOut,
    MessageOut,
    StreamChatBody,
)
from api.chat.sse import collect_answer_text_from_sse, extract_agent_trace_payloads, extract_last_done_payload
from api.config import Settings
from api.shared.access import assert_conversation_in_project, assert_project_owner
from api.shared.chat_codes import CHAT_ROLE_ASSISTANT, CHAT_ROLE_USER
from api.shared.db import get_session, new_session
from api.shared.logging import get_logger

logger = get_logger("sloww.chat")

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/projects/{project_id}/conversations", response_model=ConversationListOut)
def list_conversations(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    db: Session = Depends(get_session),
    repo: ChatRepository = Depends(get_chat_repo),
) -> ConversationListOut:
    assert_project_owner(settings, db, user.id, project_id)
    rows = repo.list_conversations(user_id=user.id, project_id=project_id)
    return ConversationListOut(
        items=[ConversationOut.model_validate(r) for r in rows],
    )


@router.post("/projects/{project_id}/conversations", response_model=ConversationOut)
def create_conversation(
    project_id: UUID,
    body: CreateConversationBody,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    db: Session = Depends(get_session),
    repo: ChatRepository = Depends(get_chat_repo),
) -> ConversationOut:
    assert_project_owner(settings, db, user.id, project_id)
    title = (body.title or "Chat").strip() or "Chat"
    cid = repo.create_conversation(user_id=user.id, project_id=project_id, title=title)
    db.commit()
    row = repo.get_conversation(user_id=user.id, conversation_id=cid)
    if row is None:
        raise HTTPException(status_code=500, detail="failed to load conversation")
    return ConversationOut.model_validate(row)


@router.get(
    "/projects/{project_id}/conversations/{conversation_id}/messages",
    response_model=MessageListOut,
)
def list_messages(
    project_id: UUID,
    conversation_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    db: Session = Depends(get_session),
    repo: ChatRepository = Depends(get_chat_repo),
) -> MessageListOut:
    assert_conversation_in_project(
        settings,
        db,
        user_id=user.id,
        conversation_id=conversation_id,
        project_id=project_id,
    )
    rows = repo.list_messages(conversation_id=conversation_id)
    out: list[MessageOut] = []
    for r in rows:
        meta = r.get("metadata")
        if meta is None:
            meta_dict: dict = {}
        elif isinstance(meta, dict):
            meta_dict = meta
        else:
            # asyncpg/sqlalchemy may return str for jsonb in some configs
            try:
                meta_dict = json.loads(meta) if isinstance(meta, str) else dict(meta)
            except json.JSONDecodeError:
                meta_dict = {}
        out.append(
            MessageOut(
                id=r["id"],
                role=int(r["role"]),
                content=str(r["content"] or ""),
                metadata=meta_dict,
                created_at=r["created_at"],
            )
        )
    return MessageListOut(items=out)


@router.post("/stream")
async def stream_chat(
    request: Request,
    body: StreamChatBody,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    db: Session = Depends(get_session),
    repo: ChatRepository = Depends(get_chat_repo),
) -> StreamingResponse:
    if not settings.inference_url:
        raise HTTPException(status_code=500, detail="INFERENCE_URL not configured")
    if not settings.internal_token:
        raise HTTPException(status_code=500, detail="INTERNAL_TOKEN not configured")

    assert_project_owner(settings, db, user.id, body.notebook_id)

    conversation_id = body.conversation_id
    if conversation_id is None:
        conversation_id = repo.create_conversation(
            user_id=user.id,
            project_id=body.notebook_id,
            title="Chat",
        )
    else:
        assert_conversation_in_project(
            settings,
            db,
            user_id=user.id,
            conversation_id=conversation_id,
            project_id=body.notebook_id,
        )

    user_msg_id = repo.insert_message(
        conversation_id=conversation_id,
        user_id=user.id,
        role=CHAT_ROLE_USER,
        content=body.query.strip(),
        metadata={"origin": "web"},
    )
    db.commit()

    inference_url = settings.inference_url.rstrip("/") + "/chat/stream"
    rid = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")

    inference_body = {
        "query": body.query.strip(),
        "conversation_id": str(conversation_id),
        "notebook_id": str(body.notebook_id),
    }

    logger.info(
        "chat_stream_relay_start request_id=%s user_id=%s notebook_id=%s conversation_id=%s",
        rid,
        user.id,
        body.notebook_id,
        conversation_id,
    )

    async def gen():
        buf: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    inference_url,
                    headers={
                        "Authorization": f"Bearer {settings.internal_token}",
                        "Content-Type": "application/json",
                        **({"X-Request-ID": rid} if rid else {}),
                    },
                    json=inference_body,
                ) as r:
                    r.raise_for_status()
                    async for chunk in r.aiter_text():
                        buf.append(chunk)
                        yield chunk
        finally:
            persist = new_session()
            try:
                raw = "".join(buf)
                done = extract_last_done_payload(raw)
                if done is None:
                    return
                answer = collect_answer_text_from_sse(raw)
                agent_traces = extract_agent_trace_payloads(raw)
                citations = done.get("citations") or []
                if not isinstance(citations, list):
                    citations = []
                results_payload = [c for c in citations if isinstance(c, dict)]

                persist_repo = get_chat_repo(persist, settings)
                assistant_msg_id = persist_repo.insert_message(
                    conversation_id=conversation_id,
                    user_id=None,
                    role=CHAT_ROLE_ASSISTANT,
                    content=answer or "(no text)",
                    metadata={
                        "user_message_id": str(user_msg_id),
                        "warning": done.get("warning"),
                        "chart_payload": done.get("chart_payload"),
                        "citations": results_payload,
                        "agent_traces": agent_traces,
                        "llm_calls": done.get("llm_calls") or [],
                        **(
                            {"latency_seconds": float(ls)}
                            if (ls := done.get("latency_seconds")) is not None
                            else {}
                        ),
                    },
                )
                retrieval_id = persist_repo.insert_retrieval_run(
                    message_id=assistant_msg_id,
                    user_id=user.id,
                    top_k=len(results_payload),
                    results=results_payload,
                )
                if results_payload:
                    persist_repo.insert_citations(
                        message_id=assistant_msg_id,
                        retrieval_run_id=retrieval_id,
                        citations=results_payload,
                    )
                persist.commit()
            except Exception:
                logger.exception("chat_stream_persist_failed")
                try:
                    persist.rollback()
                except Exception:
                    pass
            finally:
                persist.close()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": str(conversation_id)},
    )
