from uuid import UUID

from fastapi import HTTPException

from api.config import Settings
from api.projects.constants import PROJECT_TITLE_MAX_LENGTH
from api.projects.repository import ProjectRepository
from api.projects.responses import (
    CreateProjectBody,
    PatchProjectBody,
    ProjectListOut,
    ProjectOut,
)
from api.shared.logging import get_logger

logger = get_logger("sloww.projects")


def _row_to_project(row: dict) -> ProjectOut:
    return ProjectOut(
        id=str(row["id"]),
        title=row["title"],
        description=row["description"],
        is_default=row["is_default"],
        status=row["status"],
        num_sources=row.get("num_sources", 0),
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )


class ProjectService:
    def __init__(self, repo: ProjectRepository, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings

    def get_or_create_default_project(self, user_id: UUID) -> ProjectOut:
        """Get the user's default project, creating it if necessary.
        
        Uses atomic repository method to handle concurrent requests safely.
        """
        # Use the repository's atomic get_or_create that handles race conditions
        project_row = self._repo.get_or_create_default_project(user_id)
        return _row_to_project(project_row)

    def list_projects(self, user_id: UUID) -> ProjectListOut:
        """List all active projects for a user."""
        rows = self._repo.list_projects_for_user(user_id)
        return ProjectListOut(projects=[_row_to_project(r) for r in rows])

    def get_project(self, user_id: UUID, project_id: UUID) -> ProjectOut:
        """Get a specific project, verifying ownership."""
        row = self._repo.get_project_by_id(project_id)
        if not row:
            raise HTTPException(status_code=404, detail="project not found")
        if row["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="forbidden")
        return _row_to_project(row)

    def create_project(
        self, user_id: UUID, body: CreateProjectBody
    ) -> ProjectOut:
        """Create a new project for a user."""
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="title cannot be empty")
        if len(title) > PROJECT_TITLE_MAX_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"title must be at most {PROJECT_TITLE_MAX_LENGTH} characters",
            )
        logger.info("creating_project user_id=%s title=%s", user_id, title)
        row = self._repo.create_project(
            user_id=user_id,
            title=title,
            description=body.description,
        )
        return _row_to_project(row)

    def patch_project(
        self, user_id: UUID, project_id: UUID, body: PatchProjectBody
    ) -> ProjectOut:
        """Update a project, verifying ownership."""
        row = self._repo.get_project_by_id(project_id)
        if not row:
            raise HTTPException(status_code=404, detail="project not found")
        if row["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="forbidden")

        logger.info("patching_project user_id=%s project_id=%s", user_id, project_id)
        patch_title = (
            body.title.strip() if body.title is not None else None
        )
        if patch_title is not None:
            if not patch_title:
                raise HTTPException(status_code=400, detail="title cannot be empty")
            if len(patch_title) > PROJECT_TITLE_MAX_LENGTH:
                raise HTTPException(
                    status_code=400,
                    detail=f"title must be at most {PROJECT_TITLE_MAX_LENGTH} characters",
                )
        updated = self._repo.patch_project(
            project_id=project_id,
            title=patch_title,
            description=body.description,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="project not found")
        return _row_to_project(updated)

    def delete_project(self, user_id: UUID, project_id: UUID) -> None:
        """Delete a project, verifying ownership."""
        row = self._repo.get_project_by_id(project_id)
        if not row:
            raise HTTPException(status_code=404, detail="project not found")
        if row["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="forbidden")

        logger.info("deleting_project user_id=%s project_id=%s", user_id, project_id)
        self._repo.delete_project(project_id)
