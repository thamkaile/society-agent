import logging

from fastapi import APIRouter, HTTPException
from services.project_session_service import ProjectSessionService

logger = logging.getLogger(__name__)

router = APIRouter()
session_service = ProjectSessionService()


@router.get("/sessions/{chat_id}")
def get_project_session(chat_id: str):
    try:
        return session_service.get_session(chat_id)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    except Exception:
        logger.exception("Failed to load session")
        raise HTTPException(
            status_code=500,
            detail="Failed to load session. Check backend logs.",
        )
@router.get("/sessions")
def list_sessions():
    return session_service.list_sessions()


@router.delete("/sessions/{chat_id}")
def delete_project_session(chat_id: str):
    try:
        result = session_service.delete_session(chat_id)
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
