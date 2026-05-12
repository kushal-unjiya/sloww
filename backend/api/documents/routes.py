from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.auth.deps import CurrentUser, get_current_user, get_settings_dep
from api.config import Settings
from api.documents.repository import DocumentRepository
from api.documents.responses import (
    DocumentListOut,
    RegisterDocumentBody,
    RegisterDocumentOut,
)
from api.documents.services import DocumentService
from api.projects.repository import ProjectRepository
from api.shared.db import get_session
from api.shared.pubsub import publish_ingestion_job

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_repository(
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> DocumentRepository:
    return DocumentRepository(db, settings)


def get_project_repository(
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ProjectRepository:
    return ProjectRepository(db, settings)


def get_document_service(
    repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> DocumentService:
    return DocumentService(repo, settings, project_repo)


@router.post("", response_model=RegisterDocumentOut)
def register_document(
    body: RegisterDocumentBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[DocumentService, Depends(get_document_service)],
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> RegisterDocumentOut:
    out = svc.register(user.id, body)
    db.commit()
    publish_ingestion_job(
        topic_full=settings.pubsub_ingestion_topic_full,
        enabled=settings.pubsub_enabled,
        project_id=body.project_id,
        document_id=out.id,
        job_id=out.job_id,
        storage_key=body.storage_key,
    )
    return out


@router.get("", response_model=DocumentListOut)
def list_project_documents(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[DocumentService, Depends(get_document_service)],
    project_id: Annotated[UUID, Query()],
) -> DocumentListOut:
    """List documents for a specific project. project_id is REQUIRED."""
    return svc.list_documents(user.id, project_id=project_id)


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[DocumentService, Depends(get_document_service)],
    db: Annotated[Session, Depends(get_session)],
) -> None:
    svc.delete_document(user.id, document_id)
    db.commit()


@router.post("/{document_id}/reprocess", response_model=RegisterDocumentOut)
def reprocess_document(
    document_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[DocumentService, Depends(get_document_service)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> RegisterDocumentOut:
    out = svc.reprocess(user.id, document_id)
    db.commit()
    pid = project_repo.get_project_id_for_document(document_id)
    row = repo.fetch_row_for_user(user.id, document_id)
    sk = row["storage_key"] if row else None
    if pid:
        publish_ingestion_job(
            topic_full=settings.pubsub_ingestion_topic_full,
            enabled=settings.pubsub_enabled,
            project_id=pid,
            document_id=out.id,
            job_id=out.job_id,
            storage_key=sk,
        )
    return out
