from pydantic import BaseModel, Field

from api.projects.constants import PROJECT_TITLE_MAX_LENGTH


class ProjectOut(BaseModel):
    id: str
    title: str
    description: str | None
    is_default: bool
    status: int
    num_sources: int
    created_at: str
    updated_at: str


class ProjectListOut(BaseModel):
    projects: list[ProjectOut]


class CreateProjectBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=PROJECT_TITLE_MAX_LENGTH)
    description: str | None = None


class PatchProjectBody(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=PROJECT_TITLE_MAX_LENGTH)
    description: str | None = None
