from uuid import UUID

from fastapi import HTTPException

from api.config import Settings
from api.documents.repository import DocumentRepository
from api.documents.responses import (
    DocumentListOut,
    DocumentOut,
    LatestJobOut,
    PatchDocumentBody,
    RegisterDocumentBody,
    RegisterDocumentOut,
)
from api.projects.repository import ProjectRepository
from api.shared.access import assert_document_owner
from api.shared.logging import get_logger
from api.shared.status_codes import STATUS_PROCESSING, STATUS_QUEUED, STATUS_UPLOADED
from api.uploads.storage import delete_object

logger = get_logger("sloww.documents")


def _row_to_document(row: dict) -> DocumentOut:
    job = None
    if row.get("job_status") is not None:
        job = LatestJobOut(
            status=int(row["job_status"]),
            error_message=row.get("job_error_message"),
            updated_at=row.get("job_updated_at"),
        )
    return DocumentOut(
        id=str(row["id"]),
        title=row["title"],
        source_type=row["source_type"],
        storage_key=row["storage_key"],
        original_filename=row["original_filename"],
        mime_type=row["mime_type"],
        byte_size=row["byte_size"],
        checksum_sha256=row["checksum_sha256"],
        status=int(row["document_status"]),
        chunk_count=row["chunk_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        processed_at=row["processed_at"],
        latest_job=job,
    )


class DocumentService:
    def __init__(self, repo: DocumentRepository, settings: Settings, project_repo: ProjectRepository | None = None) -> None:
        self._repo = repo
        self._settings = settings
        self._project_repo = project_repo

    def register(self, user_id: UUID, body: RegisterDocumentBody) -> RegisterDocumentOut:
        prefix = f"{body.project_id}/"
        if not body.storage_key.startswith(prefix):
            raise HTTPException(
                status_code=400,
                detail="storage_key does not belong to this project",
            )
        
        # project_id is now required
        if not body.project_id:
            raise HTTPException(status_code=400, detail="project_id is required")
        
        title = body.title if body.title else body.filename
        logger.info(
            "document_register user_id=%s storage_key=%s filename=%s byte_size=%s project_id=%s",
            user_id,
            body.storage_key,
            body.filename,
            body.byte_size,
            body.project_id,
        )
        processing_count = self._repo.count_processing_jobs_for_user(user_id=user_id)
        can_start_processing = processing_count < self._settings.max_processing_per_user
        initial_status = STATUS_PROCESSING if can_start_processing else STATUS_QUEUED
        doc_row = self._repo.insert_document(
            user_id=user_id,
            title=title,
            storage_key=body.storage_key,
            original_filename=body.filename,
            mime_type=body.mime_type,
            byte_size=body.byte_size,
            checksum=body.checksum_sha256,
            status=STATUS_UPLOADED,
        )
        job_id = self._repo.insert_ingestion_job(
            user_id=user_id,
            document_id=doc_row["id"],
            status=initial_status,
        )
        self._repo.update_document_status(
            user_id=user_id,
            document_id=doc_row["id"],
            status=initial_status,
        )

        # Associate document with specified project and bump source count
        self._project_repo.associate_document_with_project(
            project_id=body.project_id,
            document_id=doc_row["id"],
        )
        self._project_repo.increment_num_sources(body.project_id)
        logger.info(
            "document_associated_with_project user_id=%s document_id=%s project_id=%s",
            user_id,
            doc_row["id"],
            body.project_id,
        )

        logger.info(
            "document_registered user_id=%s document_id=%s status=%s processing_count=%s",
            user_id,
            doc_row["id"],
            initial_status,
            processing_count,
        )
        return RegisterDocumentOut(id=str(doc_row["id"]), status=initial_status, job_id=str(job_id))

    def patch_document(
        self, user_id: UUID, document_id: UUID, body: PatchDocumentBody
    ) -> DocumentOut:
        assert_document_owner(self._settings, self._repo.session, user_id, document_id)
        logger.info(
            "document_rename user_id=%s document_id=%s title=%s",
            user_id,
            document_id,
            body.title,
        )
        self._repo.update_title(
            user_id=user_id, document_id=document_id, title=body.title
        )
        row = self._repo.fetch_row_for_user(user_id, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="document not found")
        return _row_to_document(row)

    def list_documents(self, user_id: UUID, project_id: UUID | None = None) -> DocumentListOut:
        """List documents for a project. project_id is required (no global listing)."""
        logger.debug("documents_list user_id=%s project_id=%s", user_id, project_id)
        rows = self._repo.list_rows_for_user(user_id, project_id=project_id)
        return DocumentListOut(items=[_row_to_document(r) for r in rows])

    def delete_document(self, user_id: UUID, document_id: UUID) -> None:
        logger.info("document_delete user_id=%s document_id=%s", user_id, document_id)
        if not self._delete_document(user_id, document_id):
            raise HTTPException(status_code=404, detail="document not found")

    def _delete_document(self, user_id: UUID, doc_id: UUID) -> bool:
        try:
            assert_document_owner(self._settings, self._repo.session, user_id, doc_id)
        except HTTPException as e:
            if e.status_code == 404:
                return False
            raise
        row = self._repo.fetch_row_for_user(user_id, doc_id)
        if row is None:
            return False
        storage_key: str = row["storage_key"]

        project_id = self._project_repo.get_project_id_for_document(doc_id) if self._project_repo else None

        try:
            delete_object(self._settings, storage_key)
        except Exception:
            logger.exception(
                "storage_delete_failed user_id=%s document_id=%s storage_key=%s",
                user_id,
                doc_id,
                storage_key,
            )
            raise HTTPException(
                status_code=502,
                detail="could not delete file from object storage",
            ) from None

        if not self._repo.soft_delete_document(user_id, doc_id):
            return False

        if project_id and self._project_repo:
            self._project_repo.decrement_num_sources(project_id)

        return True

    def reprocess(self, user_id: UUID, document_id: UUID) -> RegisterDocumentOut:
        assert_document_owner(self._settings, self._repo.session, user_id, document_id)
        logger.info("document_reprocess user_id=%s document_id=%s", user_id, document_id)
        self._repo.reset_document_for_reprocess(
            user_id=user_id, document_id=document_id
        )
        processing_count = self._repo.count_processing_jobs_for_user(user_id=user_id)
        initial_status = (
            STATUS_PROCESSING
            if processing_count < self._settings.max_processing_per_user
            else STATUS_QUEUED
        )
        job_id = self._repo.insert_ingestion_job(
            user_id=user_id,
            document_id=document_id,
            status=initial_status,
        )
        self._repo.update_document_status(
            user_id=user_id,
            document_id=document_id,
            status=initial_status,
        )
        return RegisterDocumentOut(id=str(document_id), status=initial_status, job_id=str(job_id))
