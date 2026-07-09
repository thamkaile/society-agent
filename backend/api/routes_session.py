import logging

from fastapi import APIRouter, HTTPException, Request, Response
from api.session_identity import SESSION_COOKIE_NAME, resolve_browser_session_id, set_browser_session_cookie
from services.project_session_service import ProjectSessionService

logger = logging.getLogger(__name__)

router = APIRouter()
session_service = ProjectSessionService()


def _session_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "SESSION_NOT_FOUND",
            "message": "Session not found",
        },
    )


@router.get("/sessions/current")
def get_current_project_session(request: Request, response: Response):
    browser_session_id, _ = resolve_browser_session_id(request)
    set_browser_session_cookie(response, browser_session_id)
    try:
        session = session_service.get_current_session(browser_session_id=browser_session_id)
        sanitized_session = dict(session) if session else None
        if sanitized_session is not None:
            sanitized_session.pop("browser_session_id", None)
        return {
            "chat_id": sanitized_session.get("chat_id") if sanitized_session else None,
            "session": sanitized_session,
            "browser_session_cookie_present": bool(request.cookies.get(SESSION_COOKIE_NAME)),
        }

    except Exception:
        logger.exception("Failed to load current session")
        raise HTTPException(
            status_code=500,
            detail="Failed to load current session. Check backend logs.",
        )


@router.get("/sessions/{chat_id}")
def get_project_session(chat_id: str, request: Request, response: Response):
    browser_session_id, _ = resolve_browser_session_id(request)
    set_browser_session_cookie(response, browser_session_id)
    try:
        return session_service.get_session(
            chat_id,
            browser_session_id=browser_session_id,
        )

    except FileNotFoundError:
        raise _session_not_found()

    except Exception:
        logger.exception("Failed to load session")
        raise HTTPException(
            status_code=500,
            detail="Failed to load session. Check backend logs.",
        )


@router.get("/sessions")
def list_sessions(request: Request, response: Response):
    browser_session_id, _ = resolve_browser_session_id(request)
    set_browser_session_cookie(response, browser_session_id)
    return session_service.list_sessions(browser_session_id=browser_session_id)


@router.delete("/sessions/{chat_id}")
def delete_project_session(chat_id: str, request: Request, response: Response):
    browser_session_id, _ = resolve_browser_session_id(request)
    set_browser_session_cookie(response, browser_session_id)
    try:
        result = session_service.delete_session(
            chat_id,
            browser_session_id=browser_session_id,
        )
        if not result["deleted"]:
            raise _session_not_found()
        return {"ok": True, "deleted_chat_id": chat_id}

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to delete session")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete session. Check backend logs.",
        )
