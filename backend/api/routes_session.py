import logging

from fastapi import APIRouter, HTTPException, Request, Response
from api.session_identity import resolve_browser_session_id, set_browser_session_cookie
from services.project_session_service import ProjectSessionService

logger = logging.getLogger(__name__)

router = APIRouter()
session_service = ProjectSessionService()


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
        raise HTTPException(status_code=404, detail="Session not found")

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
            raise HTTPException(status_code=404, detail="Session not found")
        return {"ok": True, "deleted_chat_id": chat_id}

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to delete session")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete session. Check backend logs.",
        )
