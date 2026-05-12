from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth.deps import CurrentUser, get_current_user, get_settings_dep
from api.config import Settings
from api.projects.repository import ProjectRepository
from api.projects.responses import (
    CreateProjectBody,
    PatchProjectBody,
    ProjectListOut,
    ProjectOut,
)
from api.projects.services import ProjectService
from api.shared.db import get_session

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_repository(
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ProjectRepository:
    return ProjectRepository(db, settings)


def get_project_service(
    repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ProjectService:
    return ProjectService(repo, settings)


@router.post("", response_model=ProjectOut)
def create_project(
    body: CreateProjectBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[ProjectService, Depends(get_project_service)],
    db: Annotated[Session, Depends(get_session)],
) -> ProjectOut:
    out = svc.create_project(user.id, body)
    db.commit()
    return out


@router.get("", response_model=ProjectListOut)
def list_projects(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectListOut:
    return svc.list_projects(user.id)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectOut:
    return svc.get_project(user.id, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def patch_project(
    project_id: UUID,
    body: PatchProjectBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[ProjectService, Depends(get_project_service)],
    db: Annotated[Session, Depends(get_session)],
) -> ProjectOut:
    out = svc.patch_project(user.id, project_id, body)
    db.commit()
    return out


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    svc: Annotated[ProjectService, Depends(get_project_service)],
    db: Annotated[Session, Depends(get_session)],
) -> None:
    svc.delete_project(user.id, project_id)
    db.commit()
