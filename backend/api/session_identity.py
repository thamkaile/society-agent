import os
import uuid

from fastapi import Request, Response


SESSION_COOKIE_NAME = "session_id"
SESSION_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 180


def resolve_browser_session_id(request: Request) -> tuple[str, bool]:
    raw = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    try:
        return str(uuid.UUID(raw)), False
    except (TypeError, ValueError):
        return str(uuid.uuid4()), True


def set_browser_session_cookie(response: Response, browser_session_id: str) -> None:
    environment = (
        os.getenv("GENESIS_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("ENV")
        or ""
    ).lower()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=browser_session_id,
        max_age=SESSION_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=environment == "production",
        samesite="lax",
        path="/",
    )
