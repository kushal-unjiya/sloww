from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from api.auth.deps import CurrentUser, get_current_user, get_settings_dep
from api.config import Settings
from api.documents.responses import RegisterDocumentBody, RegisterDocumentOut
from api.documents.services import DocumentService
from api.documents.routes import get_document_service
from api.shared.access import assert_project_owner
from api.shared.db import get_session
from api.shared.pubsub import publish_ingestion_job
from api.uploads.responses import PresignBody, PresignResponse, UploadObjectOut
from api.uploads.services import UploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])


def get_upload_service(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> UploadService:
    return UploadService(settings)


@router.post("/presign", response_model=PresignResponse)
def create_presigned_upload(
    body: PresignBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[UploadService, Depends(get_upload_service)],
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> PresignResponse:
    assert_project_owner(settings, db, user.id, body.project_id)
    return svc.create_presigned_put(body)


@router.post("/object", response_model=UploadObjectOut)
async def upload_object_to_storage(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    upload_svc: Annotated[UploadService, Depends(get_upload_service)],
    doc_svc: Annotated[DocumentService, Depends(get_document_service)],
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    project_id: Annotated[UUID, Form()],
    file: UploadFile = File(...),
) -> UploadObjectOut:
    """Stream file to GCS, then register the document in the same transaction."""
    assert_project_owner(settings, db, user.id, project_id)
    blob = await upload_svc.upload_object_for_project(project_id, file)
    body = RegisterDocumentBody(
        storage_key=blob.storage_key,
        filename=blob.filename,
        mime_type=blob.mime_type,
        byte_size=blob.byte_size,
        checksum_sha256=blob.checksum_sha256,
        project_id=project_id,
    )
    try:
        reg: RegisterDocumentOut = doc_svc.register(user.id, body)
    except Exception:
        db.rollback()
        upload_svc.delete_object_best_effort(blob.storage_key)
        raise
    db.commit()
    publish_ingestion_job(
        topic_full=settings.pubsub_ingestion_topic_full,
        enabled=settings.pubsub_enabled,
        project_id=project_id,
        document_id=reg.id,
        job_id=reg.job_id,
        storage_key=blob.storage_key,
    )
    return UploadObjectOut(
        storage_key=blob.storage_key,
        filename=blob.filename,
        mime_type=blob.mime_type,
        byte_size=blob.byte_size,
        checksum_sha256=blob.checksum_sha256,
        document_id=reg.id,
        status=reg.status,
        job_id=reg.job_id,
    )
