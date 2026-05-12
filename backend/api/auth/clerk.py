from functools import lru_cache

import httpx
import jwt
from fastapi import HTTPException
from jwt import PyJWKClient

from api.config import Settings


def claims_profile(payload: dict) -> tuple[str | None, str | None, str | None]:
    email = payload.get("email")
    if not isinstance(email, str) or not email:
        email = None
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        name = None
    image = payload.get("image_url") or payload.get("picture")
    if not isinstance(image, str) or not image:
        image = None
    return email, name, image


@lru_cache
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url)


def verify_clerk_session_token(token: str, settings: Settings) -> dict:
    try:
        client = _jwks_client(settings.clerk_jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        options: dict = {"verify_aud": settings.clerk_verify_audience}
        kwargs: dict = {
            "algorithms": ["RS256"],
            "issuer": settings.clerk_jwt_issuer,
        }
        if settings.clerk_verify_audience and settings.clerk_jwt_audience:
            kwargs["audience"] = settings.clerk_jwt_audience
        return jwt.decode(
            token,
            signing_key.key,
            options=options,
            **kwargs,
        )
    except jwt.exceptions.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="invalid token") from e


def fetch_clerk_user_profile(
    clerk_user_id: str,
    settings: Settings,
) -> tuple[str | None, str | None, str | None]:
    if not settings.clerk_secret_key:
        return None, None, None
    try:
        r = httpx.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError:
        return None, None, None

    emails = data.get("email_addresses") or []
    primary_id = data.get("primary_email_address_id")
    email: str | None = None
    for e in emails:
        if e.get("id") == primary_id:
            email = e.get("email_address")
            break
    if email is None and emails:
        email = emails[0].get("email_address")

    first = (data.get("first_name") or "").strip()
    last = (data.get("last_name") or "").strip()
    name = (first + " " + last).strip() or None
    image = data.get("image_url")
    return email, name, image
