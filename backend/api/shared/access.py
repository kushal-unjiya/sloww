from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.config import Settings


def assert_document_owner(
    settings: Settings,
    db: Session,
    user_id: UUID,
    document_id: UUID,
) -> None:
    row = db.execute(
        text(
            f"""
            SELECT user_id FROM {settings.db_schema}.documents
            WHERE id = :document_id AND is_deleted = false
            """
        ),
        {"document_id": document_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    if row[0] != user_id:
        raise HTTPException(status_code=403, detail="document access denied")


def assert_conversation_owner(
    settings: Settings,
    db: Session,
    user_id: UUID,
    conversation_id: UUID,
) -> None:
    row = db.execute(
        text(
            f"""
            SELECT user_id FROM {settings.db_schema}.conversations
            WHERE id = :conversation_id
            """
        ),
        {"conversation_id": conversation_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    if row[0] != user_id:
        raise HTTPException(status_code=403, detail="conversation access denied")


def assert_project_owner(
    settings: Settings,
    db: Session,
    user_id: UUID,
    project_id: UUID,
) -> None:
    row = db.execute(
        text(
            f"""
            SELECT user_id FROM {settings.db_schema}.projects
            WHERE id = :project_id AND is_deleted = false
            """
        ),
        {"project_id": project_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    if row[0] != user_id:
        raise HTTPException(status_code=403, detail="project access denied")


def assert_conversation_in_project(
    settings: Settings,
    db: Session,
    *,
    user_id: UUID,
    conversation_id: UUID,
    project_id: UUID,
) -> None:
    assert_conversation_owner(settings, db, user_id, conversation_id)
    row = db.execute(
        text(
            f"""
            SELECT project_id FROM {settings.db_schema}.conversations
            WHERE id = :conversation_id
            """
        ),
        {"conversation_id": conversation_id},
    ).first()
    if row is None or row[0] != project_id:
        raise HTTPException(status_code=400, detail="conversation does not belong to this project")
