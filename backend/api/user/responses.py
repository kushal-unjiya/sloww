from pydantic import BaseModel


class MeResponse(BaseModel):
    id: str
    clerk_user_id: str
    email: str
    display_name: str | None
    avatar_url: str | None
