from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.config import Settings

_PROJECT_COLS = "id, user_id, title, description, is_default, status, num_sources, created_at, updated_at"


class ProjectRepository:
    def __init__(self, db: Session, settings: Settings) -> None:
        self._db = db
        self._schema = settings.db_schema

    @property
    def session(self) -> Session:
        return self._db

    def create_default_project(self, user_id: UUID) -> dict[str, Any]:
        """Create and return the user's default project."""
        row = self._db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.projects
                  (id, user_id, title, description, is_default, status, num_sources, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :user_id, 'Default Project', NULL, true, 1, 0, now(), now())
                RETURNING {_PROJECT_COLS}
                """
            ),
            {"user_id": user_id},
        ).mappings().one()
        return dict(row)

    def get_default_project_for_user(self, user_id: UUID) -> dict[str, Any] | None:
        """Retrieve the user's default project, or None if not found."""
        row = self._db.execute(
            text(
                f"""
                SELECT {_PROJECT_COLS}
                FROM {self._schema}.projects
                WHERE user_id = :user_id AND is_default = true AND is_deleted = false
                """
            ),
            {"user_id": user_id},
        ).mappings().first()
        return dict(row) if row else None

    def get_or_create_default_project(self, user_id: UUID) -> dict[str, Any]:
        """Get the user's default project, creating it if necessary.

        Handles all cases:
        - Project exists and is active: return it
        - Project exists but soft-deleted: undelete and return it
        - Project doesn't exist: create it
        """
        existing = self.get_default_project_for_user(user_id)
        if existing:
            return existing

        # Check if a soft-deleted default project exists
        deleted_row = self._db.execute(
            text(
                f"""
                SELECT {_PROJECT_COLS}
                FROM {self._schema}.projects
                WHERE user_id = :user_id AND is_default = true AND is_deleted = true
                """
            ),
            {"user_id": user_id},
        ).mappings().first()

        if deleted_row:
            self._db.execute(
                text(
                    f"""
                    UPDATE {self._schema}.projects
                    SET is_deleted = false, deleted_at = NULL, updated_at = now()
                    WHERE id = :project_id
                    """
                ),
                {"project_id": deleted_row["id"]},
            )
            return dict(deleted_row)

        # Insert atomically — race condition safe
        self._db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.projects
                  (id, user_id, title, description, is_default, status, num_sources, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :user_id, 'Default Project', NULL, true, 1, 0, now(), now())
                ON CONFLICT (user_id) WHERE is_default = true AND is_deleted = false DO NOTHING
                """
            ),
            {"user_id": user_id},
        )
        final = self.get_default_project_for_user(user_id)
        if final:
            return final

        raise RuntimeError(f"Failed to get or create default project for user {user_id}")

    def get_project_by_id(self, project_id: UUID) -> dict[str, Any] | None:
        """Retrieve a non-deleted project by ID."""
        row = self._db.execute(
            text(
                f"""
                SELECT {_PROJECT_COLS}
                FROM {self._schema}.projects
                WHERE id = :project_id AND is_deleted = false
                """
            ),
            {"project_id": project_id},
        ).mappings().first()
        return dict(row) if row else None

    def list_projects_for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        """List all active, non-deleted projects for a user, ordered by most recently updated."""
        rows = self._db.execute(
            text(
                f"""
                SELECT {_PROJECT_COLS}
                FROM {self._schema}.projects
                WHERE user_id = :user_id AND is_deleted = false
                ORDER BY updated_at DESC
                """
            ),
            {"user_id": user_id},
        ).mappings().all()
        return [dict(r) for r in rows]

    def create_project(
        self, user_id: UUID, title: str, description: str | None = None
    ) -> dict[str, Any]:
        """Create a new project for a user."""
        row = self._db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.projects
                  (id, user_id, title, description, is_default, status, num_sources, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :user_id, :title, :description, false, 1, 0, now(), now())
                RETURNING {_PROJECT_COLS}
                """
            ),
            {"user_id": user_id, "title": title, "description": description},
        ).mappings().one()
        return dict(row)

    def patch_project(
        self, project_id: UUID, title: str | None = None, description: str | None = None
    ) -> dict[str, Any] | None:
        """Update a project's title and/or description."""
        parts = []
        params: dict[str, Any] = {"project_id": project_id}
        if title is not None:
            parts.append("title = :title")
            params["title"] = title
        if description is not None:
            parts.append("description = :description")
            params["description"] = description

        if not parts:
            row = self._db.execute(
                text(
                    f"""
                    SELECT {_PROJECT_COLS}
                    FROM {self._schema}.projects
                    WHERE id = :project_id
                    """
                ),
                {"project_id": project_id},
            ).mappings().first()
            return dict(row) if row else None

        parts.append("updated_at = now()")
        set_clause = ", ".join(parts)
        row = self._db.execute(
            text(
                f"""
                UPDATE {self._schema}.projects
                SET {set_clause}
                WHERE id = :project_id
                RETURNING {_PROJECT_COLS}
                """
            ),
            params,
        ).mappings().first()
        return dict(row) if row else None

    def delete_project(self, project_id: UUID) -> None:
        """Soft delete a project (mark as deleted)."""
        self._db.execute(
            text(
                f"""
                UPDATE {self._schema}.projects
                SET is_deleted = true, deleted_at = now(), updated_at = now()
                WHERE id = :project_id AND is_deleted = false
                """
            ),
            {"project_id": project_id},
        )

    def increment_num_sources(self, project_id: UUID) -> None:
        """Increment num_sources counter when a document is added to a project."""
        self._db.execute(
            text(
                f"""
                UPDATE {self._schema}.projects
                SET num_sources = num_sources + 1, updated_at = now()
                WHERE id = :project_id
                """
            ),
            {"project_id": project_id},
        )

    def decrement_num_sources(self, project_id: UUID) -> None:
        """Decrement num_sources counter when a document is removed from a project.
        Never goes below 0."""
        self._db.execute(
            text(
                f"""
                UPDATE {self._schema}.projects
                SET num_sources = GREATEST(0, num_sources - 1), updated_at = now()
                WHERE id = :project_id
                """
            ),
            {"project_id": project_id},
        )

    def associate_document_with_project(
        self, project_id: UUID, document_id: UUID
    ) -> dict[str, Any]:
        """Associate a document with a project."""
        row = self._db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.project_documents
                  (id, project_id, document_id, created_at)
                VALUES
                  (gen_random_uuid(), :project_id, :document_id, now())
                RETURNING id, project_id, document_id, created_at
                """
            ),
            {"project_id": project_id, "document_id": document_id},
        ).mappings().first()
        return dict(row) if row else {}

    def get_project_id_for_document(
        self, document_id: UUID
    ) -> UUID | None:
        """Get the project a document belongs to (for decrement on delete)."""
        row = self._db.execute(
            text(
                f"""
                SELECT project_id
                FROM {self._schema}.project_documents
                WHERE document_id = :document_id
                LIMIT 1
                """
            ),
            {"document_id": document_id},
        ).first()
        return row[0] if row else None
