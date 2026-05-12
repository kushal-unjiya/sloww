"""Pydantic DTOs for chat API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None


class ConversationListOut(BaseModel):
    items: list[ConversationOut]


class CreateConversationBody(BaseModel):
    title: str | None = Field(default="Chat", max_length=512)


class MessageOut(BaseModel):
    id: UUID
    role: int
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MessageListOut(BaseModel):
    items: list[MessageOut]


class StreamChatBody(BaseModel):
    query: str
    notebook_id: UUID  # project UUID (Qdrant notebook_id == project id string)
    conversation_id: UUID | None = None
