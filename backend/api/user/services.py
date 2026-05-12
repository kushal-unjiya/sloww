import hashlib

from fastapi import Request

from api.auth.clerk import claims_profile, fetch_clerk_user_profile
from api.auth.deps import AuthState
from api.config import Settings
from api.projects.repository import ProjectRepository
from api.user.repository import UserRepository
from api.user.responses import MeResponse


class UserService:
    def __init__(self, repo: UserRepository, settings: Settings, project_repo: ProjectRepository | None = None) -> None:
        self._repo = repo
        self._settings = settings
        self._project_repo = project_repo

    def build_me_response(self, auth: AuthState, request: Request) -> MeResponse:
        user = auth.user
        ua = request.headers.get("user-agent")
        raw_ip = request.client.host if request.client else None
        ip_hash = (
            hashlib.sha256(raw_ip.encode("utf-8")).hexdigest() if raw_ip else None
        )
        session_id = auth.jwt_payload.get("sid")
        if session_id is not None and not isinstance(session_id, str):
            session_id = None

        self._repo.insert_sign_in_event(
            user_id=user.id,
            session_id=session_id,
            user_agent=ua,
            ip_hash=ip_hash,
        )

        em, dn, av = claims_profile(auth.jwt_payload)
        if not em or not dn or not av:
            api_em, api_dn, api_av = fetch_clerk_user_profile(
                user.clerk_user_id, self._settings
            )
            em = em or api_em
            dn = dn or api_dn
            av = av or api_av

        self._repo.update_user_after_login(
            user_id=user.id,
            email=em,
            display_name=dn,
            avatar_url=av,
        )

        if self._project_repo:
            self._project_repo.get_or_create_default_project(user.id)

        row = self._repo.get_user_by_id(user.id)
        return MeResponse(
            id=str(row["id"]),
            clerk_user_id=row["clerk_user_id"],
            email=row["email"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
        )
