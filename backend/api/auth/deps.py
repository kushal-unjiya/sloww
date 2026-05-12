from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.auth.clerk import (
    claims_profile,
    fetch_clerk_user_profile,
    verify_clerk_session_token,
)
from api.config import Settings, get_settings
from api.shared.db import get_session
from api.shared.logging import get_logger

security = HTTPBearer(auto_error=False)
logger = get_logger("sloww.auth")


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    clerk_user_id: str
    email: str
    display_name: str | None
    avatar_url: str | None


@dataclass(frozen=True)
class AuthState:
    user: CurrentUser
    jwt_payload: dict


def get_settings_dep() -> Settings:
    return get_settings()


def _user_row_to_current(row) -> CurrentUser:
    return CurrentUser(
        id=row["id"],
        clerk_user_id=row["clerk_user_id"],
        email=row["email"],
        display_name=row["display_name"],
        avatar_url=row["avatar_url"],
    )


def _relink_clerk_id(
    settings: Settings,
    db: Session,
    *,
    internal_id: UUID,
    clerk_user_id: str,
    email: str,
    display_name: str | None,
    avatar_url: str | None,
) -> CurrentUser:
    row = db.execute(
        text(
            f"""
            UPDATE {settings.db_schema}.users
            SET clerk_user_id = :clerk_user_id,
                display_name = :display_name,
                avatar_url = :avatar_url,
                updated_at = now()
            WHERE id = :id AND email = :email
            RETURNING id, clerk_user_id, email, display_name, avatar_url
            """
        ),
        {
            "id": internal_id,
            "email": email,
            "clerk_user_id": clerk_user_id,
            "display_name": display_name,
            "avatar_url": avatar_url,
        },
    ).mappings().one()
    db.commit()
    return _user_row_to_current(row)


def load_or_create_user(
    settings: Settings,
    db: Session,
    clerk_user_id: str,
    jwt_payload: dict,
) -> CurrentUser:
    existing = db.execute(
        text(
            f"""
            SELECT id, clerk_user_id, email, display_name, avatar_url
            FROM {settings.db_schema}.users
            WHERE clerk_user_id = :clerk_user_id
            """
        ),
        {"clerk_user_id": clerk_user_id},
    ).mappings().first()
    if existing is not None:
        return CurrentUser(
            id=existing["id"],
            clerk_user_id=existing["clerk_user_id"],
            email=existing["email"],
            display_name=existing["display_name"],
            avatar_url=existing["avatar_url"],
        )

    email, display_name, avatar_url = claims_profile(jwt_payload)
    if not email or not display_name or not avatar_url:
        api_email, api_name, api_avatar = fetch_clerk_user_profile(clerk_user_id, settings)
        email = email or api_email
        display_name = display_name or api_name
        avatar_url = avatar_url or api_avatar
    if not email:
        email = f"{clerk_user_id}@clerk.placeholder"

    by_email = db.execute(
        text(
            f"""
            SELECT id, clerk_user_id, email, display_name, avatar_url
            FROM {settings.db_schema}.users
            WHERE email = :email
            """
        ),
        {"email": email},
    ).mappings().first()
    if by_email is not None:
        if by_email["clerk_user_id"] == clerk_user_id:
            return _user_row_to_current(by_email)
        return _relink_clerk_id(
            settings,
            db,
            internal_id=by_email["id"],
            clerk_user_id=clerk_user_id,
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
        )

    try:
        row = db.execute(
            text(
                f"""
                INSERT INTO {settings.db_schema}.users
                    (id, clerk_user_id, email, display_name, avatar_url, status, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :clerk_user_id, :email, :display_name, :avatar_url,
                     1, now(), now())
                RETURNING id, clerk_user_id, email, display_name, avatar_url
                """
            ),
            {
                "clerk_user_id": clerk_user_id,
                "email": email,
                "display_name": display_name,
                "avatar_url": avatar_url,
            },
        ).mappings().one()
        db.commit()
    except IntegrityError as e:
        db.rollback()
        dup_sub = db.execute(
            text(
                f"""
                SELECT id, clerk_user_id, email, display_name, avatar_url
                FROM {settings.db_schema}.users
                WHERE clerk_user_id = :clerk_user_id
                """
            ),
            {"clerk_user_id": clerk_user_id},
        ).mappings().first()
        if dup_sub is not None:
            return CurrentUser(
                id=dup_sub["id"],
                clerk_user_id=dup_sub["clerk_user_id"],
                email=dup_sub["email"],
                display_name=dup_sub["display_name"],
                avatar_url=dup_sub["avatar_url"],
            )
        dup_email = db.execute(
            text(
                f"""
                SELECT id, clerk_user_id, email, display_name, avatar_url
                FROM {settings.db_schema}.users
                WHERE email = :email
                """
            ),
            {"email": email},
        ).mappings().first()
        if dup_email is not None:
            if dup_email["clerk_user_id"] == clerk_user_id:
                return _user_row_to_current(dup_email)
            try:
                return _relink_clerk_id(
                    settings,
                    db,
                    internal_id=dup_email["id"],
                    clerk_user_id=clerk_user_id,
                    email=email,
                    display_name=display_name,
                    avatar_url=avatar_url,
                )
            except IntegrityError as e2:
                db.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="This email is already linked to another account.",
                ) from e2
        raise HTTPException(
            status_code=500,
            detail="Could not create user after a database conflict. Please retry.",
        ) from e
    else:
        return CurrentUser(
            id=row["id"],
            clerk_user_id=row["clerk_user_id"],
            email=row["email"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
        )


def get_auth_state(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    db: Annotated[Session, Depends(get_session)],
) -> AuthState:
    if creds is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    payload = verify_clerk_session_token(creds.credentials, settings)
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="invalid token subject")
    user = load_or_create_user(settings, db, sub, payload)
    logger.debug("auth_ok user_id=%s clerk_user_id=%s", user.id, user.clerk_user_id)
    return AuthState(user=user, jwt_payload=payload)


def get_current_user(auth: Annotated[AuthState, Depends(get_auth_state)]) -> CurrentUser:
    return auth.user
