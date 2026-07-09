import json
import time
import uuid
from contextlib import contextmanager
from typing import Any

from sqlalchemy import func

from .database import SessionLocal
from .models import BrowserSession, ChatMessage, ChatProjectState, ChatRun, ChatSession, ChatStreamEvent


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


def _json_object(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _json_list(value: Any) -> list:
    return value if isinstance(value, list) else []


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


def _matches_browser_session(row, browser_session_id: str | None) -> bool:
    if browser_session_id is None:
        return True
    return getattr(row, "browser_session_id", None) == browser_session_id


def get_browser_session(
    browser_session_id: str,
    db=None,
    session_factory=None,
) -> dict | None:
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(BrowserSession, browser_session_id)
        return browser_session_to_dict(session) if session is not None else None


def create_browser_session(
    browser_session_id: str,
    db=None,
    session_factory=None,
) -> dict:
    now = _now()
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(BrowserSession, browser_session_id)
        if session is None:
            session = BrowserSession(
                id=browser_session_id,
                created_at=now,
                last_seen_at=now,
            )
            scoped.add(session)
        else:
            session.last_seen_at = now
        scoped.flush()
        return browser_session_to_dict(session)


def touch_browser_session(
    browser_session_id: str,
    db=None,
    session_factory=None,
) -> dict | None:
    now = _now()
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(BrowserSession, browser_session_id)
        if session is None:
            return None
        session.last_seen_at = now
        scoped.flush()
        return browser_session_to_dict(session)


def browser_session_has_references(
    browser_session_id: str,
    db=None,
    session_factory=None,
) -> bool:
    with _session_scope(db, session_factory) as scoped:
        session_exists = (
            scoped.query(ChatSession.id)
            .filter(ChatSession.browser_session_id == browser_session_id)
            .first()
            is not None
        )
        if session_exists:
            return True
        run_exists = (
            scoped.query(ChatRun.id)
            .filter(ChatRun.browser_session_id == browser_session_id)
            .first()
            is not None
        )
        if run_exists:
            return True
        state_exists = (
            scoped.query(ChatProjectState.session_id)
            .filter(ChatProjectState.browser_session_id == browser_session_id)
            .first()
            is not None
        )
        return bool(state_exists)


def _ensure_session(
    db,
    session_id: str,
    title: str | None = None,
    browser_session_id: str | None = None,
) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None:
        now = _now()
        session = ChatSession(
            id=session_id,
            browser_session_id=browser_session_id,
            title=_title_from(title),
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        db.flush()
    elif browser_session_id is not None and session.browser_session_id not in {None, browser_session_id}:
        raise PermissionError("Session belongs to a different browser session")
    else:
        if browser_session_id is not None and session.browser_session_id is None:
            session.browser_session_id = browser_session_id
    if title and session.title == "Untitled Session":
        session.title = _title_from(title)
    return session


def create_session(
    session_id: str | None = None,
    browser_session_id: str | None = None,
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
                browser_session_id=browser_session_id,
                title=_title_from(title),
                summary=summary,
                created_at=created_at or now,
                updated_at=updated_at or created_at or now,
            )
            scoped.add(session)
            scoped.flush()
        else:
            if browser_session_id is not None and session.browser_session_id not in {None, browser_session_id}:
                raise PermissionError("Session belongs to a different browser session")
            if browser_session_id is not None and session.browser_session_id is None:
                session.browser_session_id = browser_session_id
            if title and session.title == "Untitled Session":
                session.title = _title_from(title)
            if summary is not None:
                session.summary = summary
            if updated_at is not None:
                session.updated_at = updated_at
        return session_to_dict(session)


def save_project_state(
    session_id: str,
    browser_session_id: str | None = None,
    user_idea: str | None = None,
    research_brief: dict | None = None,
    agent_briefs: dict | None = None,
    sections: dict | None = None,
    decision_log: list | None = None,
    change_history: list | None = None,
    created_at: float | None = None,
    updated_at: float | None = None,
    title: str | None = None,
    db=None,
    session_factory=None,
) -> dict:
    now = _now()
    with _session_scope(db, session_factory) as scoped:
        session = _ensure_session(
            scoped,
            session_id,
            title=title or user_idea,
            browser_session_id=browser_session_id,
        )
        state = scoped.get(ChatProjectState, session_id)
        if state is None:
            state = ChatProjectState(
                session_id=session_id,
                browser_session_id=browser_session_id or session.browser_session_id,
                user_idea=str(user_idea or session.title or ""),
                research_brief=_json_object(research_brief),
                agent_briefs=_json_object(agent_briefs),
                sections=_json_object(sections),
                decision_log=_json_list(decision_log),
                change_history=_json_list(change_history),
                created_at=created_at or session.created_at or now,
                updated_at=updated_at or now,
            )
            scoped.add(state)
        else:
            if browser_session_id is not None and state.browser_session_id not in {None, browser_session_id}:
                raise PermissionError("Project state belongs to a different browser session")
            if browser_session_id is not None and state.browser_session_id is None:
                state.browser_session_id = browser_session_id
            if user_idea is not None:
                state.user_idea = str(user_idea)
            if research_brief is not None:
                state.research_brief = _json_object(research_brief)
            if agent_briefs is not None:
                state.agent_briefs = _json_object(agent_briefs)
            if sections is not None:
                state.sections = _json_object(sections)
            if decision_log is not None:
                state.decision_log = _json_list(decision_log)
            if change_history is not None:
                state.change_history = _json_list(change_history)
            state.updated_at = updated_at or now
        if title and session.title == "Untitled Session":
            session.title = _title_from(title)
        session.updated_at = max(session.updated_at or 0, state.updated_at or now)
        scoped.flush()
        return project_state_to_dict(state)


def apply_project_section_update(
    session_id: str,
    section: str,
    section_value: dict,
    browser_session_id: str | None = None,
    title: str | None = None,
    db=None,
    session_factory=None,
) -> dict:
    now = _now()
    with _session_scope(db, session_factory) as scoped:
        session = _ensure_session(
            scoped,
            session_id,
            title=title,
            browser_session_id=browser_session_id,
        )
        state = scoped.get(ChatProjectState, session_id)
        if state is None:
            state = ChatProjectState(
                session_id=session_id,
                browser_session_id=browser_session_id or session.browser_session_id,
                user_idea=session.title,
                sections={},
                created_at=session.created_at or now,
                updated_at=now,
            )
            scoped.add(state)
            scoped.flush()
        elif browser_session_id is not None and state.browser_session_id not in {None, browser_session_id}:
            raise PermissionError("Project state belongs to a different browser session")
        elif browser_session_id is not None and state.browser_session_id is None:
            state.browser_session_id = browser_session_id

        sections = dict(state.sections or {})
        sections[str(section)] = _json_object(section_value)
        state.sections = sections
        state.updated_at = now
        session.updated_at = now
        scoped.flush()
        return project_state_to_dict(state)


def get_project_state(
    session_id: str,
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> dict | None:
    with _session_scope(db, session_factory) as scoped:
        state = scoped.get(ChatProjectState, session_id)
        if state is None:
            return None
        if not _matches_browser_session(state, browser_session_id):
            return None
        return project_state_to_dict(state)


def list_sessions(
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> list[dict]:
    with _session_scope(db, session_factory) as scoped:
        query = scoped.query(ChatSession)
        if browser_session_id is not None:
            query = query.filter(ChatSession.browser_session_id == browser_session_id)
        sessions = query.order_by(ChatSession.updated_at.desc()).all()
        return [session_to_dict(session) for session in sessions]


def get_latest_session(
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> dict | None:
    with _session_scope(db, session_factory) as scoped:
        query = scoped.query(ChatSession)
        if browser_session_id is not None:
            query = query.filter(ChatSession.browser_session_id == browser_session_id)
        session = query.order_by(ChatSession.updated_at.desc()).first()
        return session_to_dict(session) if session is not None else None


def get_session_access_status(
    session_id: str,
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> str:
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(ChatSession, session_id)
        if session is None:
            return "missing"
        if not _matches_browser_session(session, browser_session_id):
            return "forbidden"
        return "owned"


def get_session_with_messages(
    session_id: str,
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> dict | None:
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(ChatSession, session_id)
        if session is None:
            return None
        if not _matches_browser_session(session, browser_session_id):
            return None
        return session_to_dict(session, include_messages=True)


def save_message(
    session_id: str,
    role: str,
    content: Any,
    browser_session_id: str | None = None,
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
        session = _ensure_session(
            scoped,
            session_id,
            title=title,
            browser_session_id=browser_session_id,
        )
        if message_id:
            existing = scoped.get(ChatMessage, message_id)
            if existing is not None and existing.session_id == session_id:
                return message_to_dict(existing)
            if existing is not None:
                message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"genesis:message:{session_id}:{message_id}"))
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


def create_run(
    run_id: str | None = None,
    session_id: str | None = None,
    browser_session_id: str | None = None,
    message: str | None = None,
    intent: str | None = None,
    client_message_id: str | None = None,
    has_business_context: bool = False,
    status: str = "running",
    metadata_json: dict | None = None,
    db=None,
    session_factory=None,
) -> dict:
    run_id = run_id or str(uuid.uuid4())
    now = _now()
    with _session_scope(db, session_factory) as scoped:
        run = scoped.get(ChatRun, run_id)
        if run is None:
            run = ChatRun(
                id=run_id,
                session_id=session_id,
                browser_session_id=browser_session_id,
                status=status,
                intent=intent,
                message=str(message or ""),
                client_message_id=client_message_id,
                has_business_context=bool(has_business_context),
                created_at=now,
                updated_at=now,
                metadata_json=metadata_json or {},
            )
            scoped.add(run)
        else:
            if browser_session_id is not None and run.browser_session_id not in {None, browser_session_id}:
                raise PermissionError("Run belongs to a different browser session")
            if browser_session_id is not None and run.browser_session_id is None:
                run.browser_session_id = browser_session_id
            run.session_id = session_id or run.session_id
            run.status = status or run.status
            run.intent = intent or run.intent
            run.updated_at = now
            if metadata_json is not None:
                run.metadata_json = metadata_json
        scoped.flush()
        return run_to_dict(run)


def update_run(
    run_id: str,
    status: str | None = None,
    session_id: str | None = None,
    intent: str | None = None,
    has_business_context: bool | None = None,
    error: str | None = None,
    metadata_json: dict | None = None,
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> dict | None:
    now = _now()
    with _session_scope(db, session_factory) as scoped:
        run = scoped.get(ChatRun, run_id)
        if run is None:
            return None
        if browser_session_id is not None and run.browser_session_id not in {None, browser_session_id}:
            return None
        if browser_session_id is not None and run.browser_session_id is None:
            run.browser_session_id = browser_session_id
        if status:
            run.status = status
            if status in {"completed", "failed"}:
                run.completed_at = now
        if session_id:
            run.session_id = session_id
        if intent:
            run.intent = intent
        if has_business_context is not None:
            run.has_business_context = bool(has_business_context)
        if error is not None:
            run.error = error
        if metadata_json is not None:
            run.metadata_json = metadata_json
        run.updated_at = now
        scoped.flush()
        return run_to_dict(run)


def get_run(
    run_id: str,
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> dict | None:
    with _session_scope(db, session_factory) as scoped:
        run = scoped.get(ChatRun, run_id)
        if run is not None and not _matches_browser_session(run, browser_session_id):
            return None
        return run_to_dict(run) if run is not None else None


def get_latest_running_run_for_session(
    session_id: str,
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> dict | None:
    with _session_scope(db, session_factory) as scoped:
        query = scoped.query(ChatRun).filter(
            ChatRun.session_id == session_id,
            ChatRun.status == "running",
        )
        if browser_session_id is not None:
            query = query.filter(ChatRun.browser_session_id == browser_session_id)
        run = query.order_by(ChatRun.created_at.desc()).first()
        return run_to_dict(run) if run is not None else None


def session_has_business_context(
    session_id: str | None,
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> bool:
    if not session_id:
        return False
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(ChatSession, session_id)
        if session is not None and not _matches_browser_session(session, browser_session_id):
            return False
        run_query = scoped.query(ChatRun).filter(
            ChatRun.session_id == session_id,
            ChatRun.has_business_context.is_(True),
            ChatRun.status != "failed",
        )
        if browser_session_id is not None:
            run_query = run_query.filter(ChatRun.browser_session_id == browser_session_id)
        run = run_query.first()
        if run is not None:
            return True

        message = (
            scoped.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .all()
        )
        for item in message:
            metadata = item.metadata_json or {}
            if metadata.get("intent") in {"business_idea", "refinement"}:
                return True
        return False


def save_stream_event(
    run_id: str,
    event: dict,
    session_id: str | None = None,
    browser_session_id: str | None = None,
    visible: bool = True,
    message_id: str | None = None,
    db=None,
    session_factory=None,
) -> dict:
    event = dict(event or {})
    event_id = str(event.get("id") or message_id or uuid.uuid4())
    now = float(event.get("timestamp") or _now())
    event_type = str(event.get("type") or "message")
    with _session_scope(db, session_factory) as scoped:
        existing = scoped.get(ChatStreamEvent, event_id)
        if existing is not None and existing.run_id == run_id:
            return stream_event_to_dict(existing)
        if existing is not None:
            event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"genesis:event:{run_id}:{event_id}"))

        run = scoped.get(ChatRun, run_id)
        if run is None:
            run = ChatRun(
                id=run_id,
                session_id=session_id,
                browser_session_id=browser_session_id,
                status="running",
                message="",
                created_at=now,
                updated_at=now,
            )
            scoped.add(run)
            scoped.flush()
        elif browser_session_id is not None and run.browser_session_id not in {None, browser_session_id}:
            raise PermissionError("Run belongs to a different browser session")
        elif browser_session_id is not None and run.browser_session_id is None:
            run.browser_session_id = browser_session_id

        current_max = (
            scoped.query(func.max(ChatStreamEvent.sequence))
            .filter(ChatStreamEvent.run_id == run_id)
            .scalar()
            or 0
        )
        sequence = current_max + 1
        payload = {
            **event,
            "id": event_id,
            "run_id": run_id,
            "sequence": sequence,
            "timestamp": now,
        }
        if browser_session_id or run.browser_session_id:
            payload["browser_session_id"] = browser_session_id or run.browser_session_id
        if session_id:
            payload["chat_id"] = session_id

        stream_event = ChatStreamEvent(
            id=event_id,
            run_id=run_id,
            session_id=session_id,
            browser_session_id=browser_session_id or run.browser_session_id,
            sequence=sequence,
            type=event_type,
            role=payload.get("role") or _role_for_event_type(event_type),
            agent_name=payload.get("agent"),
            phase=payload.get("phase"),
            content=_content_text(payload.get("content", "")),
            created_at=now,
            visible=visible,
            payload_json=payload,
        )
        scoped.add(stream_event)
        run.session_id = session_id or run.session_id
        run.browser_session_id = browser_session_id or run.browser_session_id
        run.updated_at = now
        scoped.flush()
        return stream_event_to_dict(stream_event)


def list_stream_events(
    run_id: str,
    browser_session_id: str | None = None,
    after_sequence: int | None = None,
    after_event_id: str | None = None,
    db=None,
    session_factory=None,
) -> list[dict]:
    with _session_scope(db, session_factory) as scoped:
        run = scoped.get(ChatRun, run_id)
        if run is None or not _matches_browser_session(run, browser_session_id):
            return []
        query = scoped.query(ChatStreamEvent).filter(ChatStreamEvent.run_id == run_id)
        if browser_session_id is not None:
            query = query.filter(ChatStreamEvent.browser_session_id == browser_session_id)
        if after_event_id:
            marker = scoped.get(ChatStreamEvent, after_event_id)
            if marker is not None and marker.run_id == run_id:
                after_sequence = max(after_sequence or 0, marker.sequence)
        if after_sequence is not None:
            query = query.filter(ChatStreamEvent.sequence > int(after_sequence))
        events = query.order_by(ChatStreamEvent.sequence.asc()).all()
        return [stream_event_to_dict(event) for event in events]


def update_session_summary(
    session_id: str,
    summary: str,
    browser_session_id: str | None = None,
    title: str | None = None,
    db=None,
    session_factory=None,
) -> dict | None:
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(ChatSession, session_id)
        if session is None:
            return None
        if not _matches_browser_session(session, browser_session_id):
            return None
        session.summary = summary
        if title:
            session.title = _title_from(title)
        session.updated_at = _now()
        scoped.flush()
        return session_to_dict(session)


def delete_session(
    session_id: str,
    browser_session_id: str | None = None,
    db=None,
    session_factory=None,
) -> bool:
    with _session_scope(db, session_factory) as scoped:
        session = scoped.get(ChatSession, session_id)
        if session is None:
            return False
        if not _matches_browser_session(session, browser_session_id):
            return False
        scoped.delete(session)
        return True


def browser_session_to_dict(session: BrowserSession) -> dict:
    return {
        "id": session.id,
        "browser_session_id": session.id,
        "created_at": session.created_at,
        "last_seen_at": session.last_seen_at,
    }


def project_state_to_dict(state: ChatProjectState) -> dict:
    return {
        "session_id": state.session_id,
        "chat_id": state.session_id,
        "browser_session_id": state.browser_session_id,
        "user_idea": state.user_idea,
        "research_brief": state.research_brief or {},
        "agent_briefs": state.agent_briefs or {},
        "sections": state.sections or {},
        "decision_log": state.decision_log or [],
        "change_history": state.change_history or [],
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def session_to_dict(session: ChatSession, include_messages: bool = False) -> dict:
    data = {
        "id": session.id,
        "chat_id": session.id,
        "browser_session_id": session.browser_session_id,
        "title": session.title,
        "summary": session.summary,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }
    if include_messages:
        data["messages"] = [message_to_dict(message) for message in session.messages]
    if session.project_state is not None:
        data["project_state"] = project_state_to_dict(session.project_state)
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


def run_to_dict(run: ChatRun) -> dict:
    return {
        "id": run.id,
        "run_id": run.id,
        "session_id": run.session_id,
        "chat_id": run.session_id,
        "browser_session_id": run.browser_session_id,
        "status": run.status,
        "intent": run.intent,
        "message": run.message,
        "client_message_id": run.client_message_id,
        "has_business_context": run.has_business_context,
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "completed_at": run.completed_at,
        "metadata_json": run.metadata_json or {},
    }


def stream_event_to_dict(event: ChatStreamEvent) -> dict:
    payload = dict(event.payload_json or {})
    payload.setdefault("id", event.id)
    payload.setdefault("run_id", event.run_id)
    payload.setdefault("chat_id", event.session_id)
    payload.setdefault("sequence", event.sequence)
    payload.setdefault("timestamp", event.created_at)
    payload.setdefault("type", event.type)
    return {
        "id": event.id,
        "run_id": event.run_id,
        "session_id": event.session_id,
        "chat_id": event.session_id,
        "browser_session_id": event.browser_session_id,
        "sequence": event.sequence,
        "type": event.type,
        "role": event.role,
        "agent_name": event.agent_name,
        "phase": event.phase,
        "content": event.content,
        "created_at": event.created_at,
        "timestamp": event.created_at,
        "visible": event.visible,
        "payload_json": payload,
        "event": payload,
    }


def _role_for_event_type(event_type: str) -> str:
    if event_type == "user_input":
        return "user"
    if event_type in {
        "agent_response",
        "agent_completed",
        "orchestration_plan",
        "pm_research_plan",
        "research_complete",
        "round_consensus",
        "summarizer",
        "casual_chat",
        "clarification",
        "coordinator_routing",
    }:
        return "assistant"
    return "system"
