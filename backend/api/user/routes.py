from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import logging

from api.auth.deps import AuthState, get_auth_state, get_settings_dep
from api.config import Settings
from api.projects.repository import ProjectRepository
from api.shared.db import get_session
from api.user.repository import UserRepository
from api.user.responses import MeResponse
from api.user.services import UserService

router = APIRouter(tags=["user"])
logger = logging.getLogger("sloww.user")


def get_user_repository(
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> UserRepository:
    return UserRepository(db, settings)


def get_project_repository(
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ProjectRepository:
    return ProjectRepository(db, settings)


def get_user_service(
    repo: Annotated[UserRepository, Depends(get_user_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> UserService:
    return UserService(repo, settings, project_repo)


@router.get("/me", response_model=MeResponse)
def read_me(
    request: Request,
    auth: Annotated[AuthState, Depends(get_auth_state)],
    svc: Annotated[UserService, Depends(get_user_service)],
    db: Annotated[Session, Depends(get_session)],
) -> MeResponse:
    logger.info("me request user_id=%s", auth.user.id)
    out = svc.build_me_response(auth, request)
    db.commit()
    return out
