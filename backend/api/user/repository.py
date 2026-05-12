from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.config import Settings


class UserRepository:
    """Persistence for `users` and `user_sign_in_events`."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self._db = db
        self._schema = settings.db_schema

    def insert_sign_in_event(
        self,
        *,
        user_id: UUID,
        session_id: str | None,
        user_agent: str | None,
        ip_hash: str | None,
    ) -> None:
        self._db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.user_sign_in_events
                    (id, user_id, signed_in_at, clerk_session_id, auth_method,
                     user_agent, ip_hash, metadata)
                VALUES
                    (gen_random_uuid(), :user_id, now(), :session_id, 'email_otp',
                     :user_agent, :ip_hash, '{{}}'::jsonb)
                """
            ),
            {
                "user_id": user_id,
                "session_id": session_id,
                "user_agent": user_agent,
                "ip_hash": ip_hash,
            },
        )

    def update_user_after_login(
        self,
        *,
        user_id: UUID,
        email: str | None,
        display_name: str | None,
        avatar_url: str | None,
    ) -> None:
        self._db.execute(
            text(
                f"""
                UPDATE {self._schema}.users
                SET
                  last_login_at = now(),
                  updated_at = now(),
                  email = COALESCE(:email, email),
                  display_name = COALESCE(:display_name, display_name),
                  avatar_url = COALESCE(:avatar_url, avatar_url)
                WHERE id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "email": email,
                "display_name": display_name,
                "avatar_url": avatar_url,
            },
        )

    def get_user_by_id(self, user_id: UUID) -> dict[str, Any]:
        row = self._db.execute(
            text(
                f"""
                SELECT id, clerk_user_id, email, display_name, avatar_url
                FROM {self._schema}.users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        ).mappings().one()
        return dict(row)
