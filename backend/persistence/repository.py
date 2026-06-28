import json
import time
import uuid
from contextlib import contextmanager
from typing import Any

from .database import SessionLocal
from .models import ChatMessage, ChatSession


def _now() -> float:
    return time.time()


def _title_from(value: str | None) -> str:
    title = " ".join(str(value or "").split())
    return (title[:80] if title else "Untitled Session")


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


@contextmanager
def _session_scope(db=None, session_factory=None):
    if db is not None:
        yield db
        return

    factory = session_factory or SessionLocal
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_session(db, session_id: str, title: str | None = None) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None:
        now = _now()
        session = ChatSession(
            id=session_id,
            title=_title_from(title),
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        db.flush()
    elif title and session.title == "Untitled Session":
        session.title = _title_from(title)
    return session


def create_session(
    session_id: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    created_at: float | None = None,
    updated_at: float | None = None,
    db=None,
    session_factory=None,
) -> dict:
    session_id = session_id or str(uuid.uuid4())
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(ChatSession, session_id)
        now = _now()
        if session is None:
            session = ChatSession(
                id=session_id,
                title=_title_from(title),
                summary=summary,
                created_at=created_at or now,
                updated_at=updated_at or created_at or now,
            )
            scoped.add(session)
            scoped.flush()
        else:
            if title and session.title == "Untitled Session":
                session.title = _title_from(title)
            if summary is not None:
                session.summary = summary
            if updated_at is not None:
                session.updated_at = updated_at
        return session_to_dict(session)


def list_sessions(db=None, session_factory=None) -> list[dict]:
    with _session_scope(db, session_factory) as scoped:
        sessions = (
            scoped.query(ChatSession)
            .order_by(ChatSession.updated_at.desc())
            .all()
        )
        return [session_to_dict(session) for session in sessions]


def get_session_with_messages(
    session_id: str,
    db=None,
    session_factory=None,
) -> dict | None:
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(ChatSession, session_id)
        if session is None:
            return None
        return session_to_dict(session, include_messages=True)


def save_message(
    session_id: str,
    role: str,
    content: Any,
    agent_name: str | None = None,
    phase: str | None = None,
    metadata_json: dict | None = None,
    message_id: str | None = None,
    created_at: float | None = None,
    title: str | None = None,
    db=None,
    session_factory=None,
) -> dict:
    with _session_scope(db, session_factory) as scoped:
        session = _ensure_session(scoped, session_id, title=title)
        message = ChatMessage(
            id=message_id or str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            agent_name=agent_name,
            phase=phase,
            content=_content_text(content),
            created_at=created_at or _now(),
            metadata_json=metadata_json or {},
        )
        scoped.add(message)
        session.updated_at = message.created_at
        scoped.flush()
        return message_to_dict(message)


def update_session_summary(
    session_id: str,
    summary: str,
    title: str | None = None,
    db=None,
    session_factory=None,
) -> dict | None:
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(ChatSession, session_id)
        if session is None:
            return None
        session.summary = summary
        if title:
            session.title = _title_from(title)
        session.updated_at = _now()
        scoped.flush()
        return session_to_dict(session)


def delete_session(session_id: str, db=None, session_factory=None) -> bool:
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(ChatSession, session_id)
        if session is None:
            return False
        scoped.delete(session)
        return True


def session_to_dict(session: ChatSession, include_messages: bool = False) -> dict:
    data = {
        "id": session.id,
        "chat_id": session.id,
        "title": session.title,
        "summary": session.summary,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }
    if include_messages:
        data["messages"] = [message_to_dict(message) for message in session.messages]
    return data


def message_to_dict(message: ChatMessage) -> dict:
    metadata = message.metadata_json or {}
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "agent_name": message.agent_name,
        "phase": message.phase,
        "content": message.content,
        "created_at": message.created_at,
        "timestamp": message.created_at,
        "metadata_json": metadata,
        "event": metadata,
    }
