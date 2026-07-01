import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from schemas.chat import ChatRequest, ChatResponse
from api.session_identity import resolve_browser_session_id, set_browser_session_cookie
from persistence import repository as chat_repository
from services.simulation_service import SimulationService
from services.agent_identity import enrich_event_agent_identity
from services.intent_router import (
    BUSINESS_IDEA,
    CASUAL_CHAT,
    REFINEMENT,
    UNKNOWN,
    casual_chat_reply,
    classify_intent,
    unknown_intent_reply,
)

logger = logging.getLogger(__name__)

router = APIRouter()
simulation_service = SimulationService()

RUN_STATUS_IDLE = "idle"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
TERMINAL_RUN_STATUSES = {RUN_STATUS_COMPLETED, RUN_STATUS_FAILED}

_run_notifications: dict[str, asyncio.Event] = {}
_run_tasks: dict[str, asyncio.Task] = {}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _notify_run(run_id: str):
    notification = _run_notifications.get(run_id)
    if notification is not None:
        notification.set()


def _run_notification(run_id: str) -> asyncio.Event:
    notification = _run_notifications.get(run_id)
    if notification is None:
        notification = asyncio.Event()
        _run_notifications[run_id] = notification
    return notification


def _stable_id(prefix: str, value: str | None) -> str:
    if value and len(value) <= 64:
        return value
    seed = value or str(uuid.uuid4())
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"genesis:{prefix}:{seed}"))


def _event_with_identity(
    event: dict,
    run_id: str,
    chat_id: str | None = None,
    client_message_id: str | None = None,
) -> dict:
    event = dict(event or {})
    event = enrich_event_agent_identity(event)
    event["run_id"] = run_id
    event["timestamp"] = float(event.get("timestamp") or time.time())
    if chat_id and not event.get("chat_id"):
        event["chat_id"] = chat_id
    if event.get("type") == "user_input" and client_message_id:
        event["client_message_id"] = client_message_id
        event["id"] = _stable_id("user", client_message_id)
    if not event.get("id"):
        event["id"] = str(uuid.uuid4())
    return event


def _role_for_event(event_type: str) -> str:
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


def _persist_stream_event(
    session_id: str | None,
    event: dict,
    title: str,
    browser_session_id: str,
) -> str | None:
    if event.get("type") in {
        "status",
        "phase",
        "info",
        "artifact",
        "agent_typing",
        "agent_delta",
        "round_started",
        "debate_needs_more",
        "section_updated",
    }:
        return event.get("chat_id") or session_id

    persisted_event = _event_for_persistence(event)
    event_type = event.get("type", "")
    event_chat_id = event.get("chat_id")
    active_session_id = event_chat_id or session_id

    if event_chat_id:
        chat_repository.create_session(
            session_id=event_chat_id,
            browser_session_id=browser_session_id,
            title=title,
        )

    if not active_session_id:
        return None

    chat_repository.save_message(
        session_id=active_session_id,
        browser_session_id=browser_session_id,
        role=_role_for_event(event_type),
        agent_name=event.get("agent"),
        phase=event.get("phase"),
        content=event.get("content", ""),
        metadata_json=persisted_event,
        message_id=event.get("id") if event.get("id") else None,
        title=title,
    )

    if event_type == "summarizer":
        chat_repository.update_session_summary(
            active_session_id,
            str(event.get("content") or ""),
            browser_session_id=browser_session_id,
        )

    return active_session_id


def _event_for_persistence(event: dict) -> dict:
    if event.get("type") != "research_complete":
        return dict(event)

    allowed = {
        "id",
        "run_id",
        "chat_id",
        "type",
        "agent",
        "agent_identity",
        "content",
        "status",
        "fallback_used",
        "fallback_reason",
        "research_quality",
        "source_count",
        "objective_count",
        "artifact_path",
        "agent_briefs_path",
        "timestamp",
    }
    return {key: value for key, value in event.items() if key in allowed}


def _persist_direct_exchange(
    session_id: str | None,
    browser_session_id: str,
    user_message: str,
    assistant_reply: str,
    assistant_event_type: str,
    intent: str,
    client_message_id: str | None = None,
) -> str:
    session = chat_repository.create_session(
        session_id=session_id,
        browser_session_id=browser_session_id,
        title=user_message,
    )
    active_session_id = session["id"]
    timestamp = time.time()

    chat_repository.save_message(
        session_id=active_session_id,
        browser_session_id=browser_session_id,
        role="user",
        agent_name="User",
        content=user_message,
        message_id=_stable_id("user", client_message_id) if client_message_id else None,
        metadata_json={
            "type": "user_input",
            "agent": "User",
            "content": user_message,
            "intent": intent,
            "client_message_id": client_message_id,
        },
        created_at=timestamp,
        title=user_message,
    )

    chat_repository.save_message(
        session_id=active_session_id,
        browser_session_id=browser_session_id,
        role="assistant",
        agent_name="Genesis",
        content=assistant_reply,
        message_id=_stable_id("assistant", f"{active_session_id}:{client_message_id}:{assistant_event_type}"),
        metadata_json={
            "type": assistant_event_type,
            "agent": "Genesis",
            "content": assistant_reply,
            "intent": intent,
        },
        created_at=timestamp + 0.001,
        title=user_message,
    )

    return active_session_id


def _has_existing_business_context(chat_id: str | None, browser_session_id: str) -> bool:
    if not chat_id:
        return False
    if chat_repository.session_has_business_context(
        chat_id,
        browser_session_id=browser_session_id,
    ):
        return True
    try:
        from dynamic_engine.session_store import SessionStore

        store = SessionStore()
        store.load(chat_id, browser_session_id=browser_session_id)
        return True
    except Exception:
        return False


def _owned_chat_session_exists(chat_id: str | None, browser_session_id: str) -> bool:
    if not chat_id:
        return True
    if chat_repository.get_session_with_messages(
        chat_id,
        browser_session_id=browser_session_id,
    ):
        return True
    try:
        from dynamic_engine.session_store import SessionStore

        SessionStore().load(chat_id, browser_session_id=browser_session_id)
        return True
    except Exception:
        return False


def _classify_for_request(request: ChatRequest, browser_session_id: str) -> tuple[object, bool]:
    has_business_context = _has_existing_business_context(request.chat_id, browser_session_id)
    intent_result = classify_intent(
        request.message,
        has_existing_chat=has_business_context,
    )
    if has_business_context and intent_result.intent not in {CASUAL_CHAT, UNKNOWN}:
        intent_result = type(intent_result)(
            REFINEMENT,
            max(intent_result.confidence, 0.75),
            "active_business_context",
        )
    return intent_result, has_business_context


def _persist_and_record_event(
    run_id: str,
    event: dict,
    session_id: str | None,
    title: str,
    browser_session_id: str,
    client_message_id: str | None = None,
) -> str | None:
    event = _event_with_identity(
        event,
        run_id,
        chat_id=session_id,
        client_message_id=client_message_id,
    )
    active_session_id = _persist_stream_event(
        session_id,
        event,
        title,
        browser_session_id,
    )
    if active_session_id and not event.get("chat_id"):
        event["chat_id"] = active_session_id
    chat_repository.save_stream_event(
        run_id=run_id,
        event=event,
        session_id=active_session_id or session_id,
        browser_session_id=browser_session_id,
        visible=event.get("type") not in {"status", "artifact", "agent_typing", "agent_delta", "ping"},
    )
    if active_session_id:
        chat_repository.update_run(
            run_id,
            session_id=active_session_id,
            browser_session_id=browser_session_id,
        )
    _notify_run(run_id)
    return active_session_id or session_id


def _record_stream_event_only(
    run_id: str,
    event: dict,
    session_id: str | None,
    browser_session_id: str,
    client_message_id: str | None = None,
) -> dict:
    event = _event_with_identity(
        event,
        run_id,
        chat_id=session_id,
        client_message_id=client_message_id,
    )
    saved = chat_repository.save_stream_event(
        run_id=run_id,
        event=event,
        session_id=session_id,
        browser_session_id=browser_session_id,
        visible=event.get("type") not in {"status", "artifact", "agent_typing", "agent_delta", "ping"},
    )
    if session_id:
        chat_repository.update_run(
            run_id,
            session_id=session_id,
            browser_session_id=browser_session_id,
        )
    _notify_run(run_id)
    return saved


async def _execute_chat_run(
    run_id: str,
    request: ChatRequest,
    intent_result,
    has_business_context: bool,
    browser_session_id: str,
):
    active_chat_id = request.chat_id
    try:
        _persist_and_record_event(
            run_id,
            {
                "type": "status",
                "agent": "Genesis",
                "content": "Stream started",
                "status": RUN_STATUS_RUNNING,
            },
            active_chat_id,
            request.message,
            browser_session_id,
        )
        _persist_and_record_event(
            run_id,
            {
                "type": "status",
                "agent": "Genesis",
                "content": "Intent classified",
                "intent": intent_result.intent,
                "reason": intent_result.reason,
                "confidence": intent_result.confidence,
            },
            active_chat_id,
            request.message,
            browser_session_id,
        )

        if intent_result.intent in {CASUAL_CHAT, UNKNOWN}:
            reply = (
                casual_chat_reply(request.message)
                if intent_result.intent == CASUAL_CHAT
                else unknown_intent_reply()
            )
            assistant_event_type = (
                "casual_chat"
                if intent_result.intent == CASUAL_CHAT
                else "clarification"
            )
            session = chat_repository.create_session(
                session_id=active_chat_id,
                browser_session_id=browser_session_id,
                title=request.message,
            )
            active_chat_id = session["id"]
            if not request.chat_id and active_chat_id:
                _record_stream_event_only(
                    run_id,
                    {
                        "type": "session_created",
                        "chat_id": active_chat_id,
                        "content": f"Created chat session {active_chat_id}",
                    },
                    active_chat_id,
                    browser_session_id,
                )
            _persist_and_record_event(
                run_id,
                {
                    "type": "user_input",
                    "agent": "User",
                    "chat_id": active_chat_id,
                    "content": request.message,
                    "intent": intent_result.intent,
                },
                active_chat_id,
                request.message,
                browser_session_id,
                client_message_id=request.client_message_id,
            )
            _persist_and_record_event(
                run_id,
                {
                    "type": assistant_event_type,
                    "agent": "Genesis",
                    "chat_id": active_chat_id,
                    "content": reply,
                    "intent": intent_result.intent,
                },
                active_chat_id,
                request.message,
                browser_session_id,
            )
            chat_repository.update_run(
                run_id,
                status=RUN_STATUS_COMPLETED,
                session_id=active_chat_id,
                intent=intent_result.intent,
                has_business_context=has_business_context,
                browser_session_id=browser_session_id,
            )
            _notify_run(run_id)
            return

        workflow_chat_id = active_chat_id if intent_result.intent == REFINEMENT else None
        if workflow_chat_id:
            _persist_and_record_event(
                run_id,
                {
                    "type": "user_input",
                    "agent": "User",
                    "chat_id": workflow_chat_id,
                    "content": request.message,
                    "intent": intent_result.intent,
                },
                workflow_chat_id,
                request.message,
                browser_session_id,
                client_message_id=request.client_message_id,
            )

        _persist_and_record_event(
            run_id,
            {
                "type": "status",
                "agent": "Genesis",
                "chat_id": workflow_chat_id,
                "content": "Starting agent simulation",
            },
            workflow_chat_id,
            request.message,
            browser_session_id,
        )

        async for event in simulation_service.run_stream(
            message=request.message,
            chat_id=workflow_chat_id,
            browser_session_id=browser_session_id,
        ):
            active_chat_id = _persist_and_record_event(
                run_id,
                event,
                active_chat_id,
                request.message,
                browser_session_id,
                client_message_id=request.client_message_id,
            )

        chat_repository.update_run(
            run_id,
            status=RUN_STATUS_COMPLETED,
            session_id=active_chat_id,
            intent=intent_result.intent,
            has_business_context=True,
            browser_session_id=browser_session_id,
        )
        _notify_run(run_id)

    except Exception as e:
        logger.exception("Chat run failed")
        _persist_and_record_event(
            run_id,
            {
                "type": "error",
                "agent": "Genesis",
                "chat_id": active_chat_id,
                "content": "Streaming chat failed.",
                "detail": str(e),
            },
            active_chat_id,
            request.message,
            browser_session_id,
        )
        chat_repository.update_run(
            run_id,
            status=RUN_STATUS_FAILED,
            session_id=active_chat_id,
            error=str(e),
            browser_session_id=browser_session_id,
        )
        _notify_run(run_id)


def _start_run_task(request: ChatRequest, browser_session_id: str) -> dict:
    if request.chat_id and not _owned_chat_session_exists(
        request.chat_id,
        browser_session_id,
    ):
        raise HTTPException(status_code=404, detail="Session not found")
    intent_result, has_business_context = _classify_for_request(request, browser_session_id)
    run_id = request.run_id or str(uuid.uuid4())
    run = chat_repository.create_run(
        run_id=run_id,
        session_id=request.chat_id,
        browser_session_id=browser_session_id,
        message=request.message,
        intent=intent_result.intent,
        client_message_id=request.client_message_id,
        has_business_context=has_business_context or intent_result.intent in {BUSINESS_IDEA, REFINEMENT},
        status=RUN_STATUS_RUNNING,
        metadata_json={
            "intent_reason": intent_result.reason,
            "intent_confidence": intent_result.confidence,
        },
    )
    task = _run_tasks.get(run_id)
    if task is None or task.done():
        task = asyncio.create_task(
            _execute_chat_run(
                run_id,
                request,
                intent_result,
                has_business_context,
                browser_session_id,
            )
        )
        _run_tasks[run_id] = task
    return run


async def _stream_run_events(
    run_id: str,
    browser_session_id: str,
    after_sequence: int | None = None,
    last_event_id: str | None = None,
):
    current_sequence = int(after_sequence or 0)
    notification = _run_notification(run_id)
    while True:
        events = chat_repository.list_stream_events(
            run_id,
            browser_session_id=browser_session_id,
            after_sequence=current_sequence,
            after_event_id=last_event_id,
        )
        last_event_id = None
        for item in events:
            current_sequence = max(current_sequence, int(item["sequence"]))
            yield _sse(item["event"])

        run = chat_repository.get_run(run_id, browser_session_id=browser_session_id)
        if run is None:
            yield _sse({
                "type": "error",
                "run_id": run_id,
                "content": "Run not found.",
                "timestamp": time.time(),
            })
            return
        if run["status"] in TERMINAL_RUN_STATUSES:
            return

        try:
            await asyncio.wait_for(notification.wait(), timeout=12.0)
            notification.clear()
        except asyncio.TimeoutError:
            ping = {
                "id": str(uuid.uuid4()),
                "type": "ping",
                "run_id": run_id,
                "timestamp": time.time(),
                "status": run["status"],
            }
            saved = chat_repository.save_stream_event(
                run_id=run_id,
                event=ping,
                session_id=run.get("chat_id"),
                browser_session_id=browser_session_id,
                visible=False,
            )
            current_sequence = max(current_sequence, int(saved["sequence"]))
            yield _sse(saved["event"])


@router.get("/health")
def health_check(request: Request, response: Response):
    browser_session_id, _ = resolve_browser_session_id(request)
    set_browser_session_cookie(response, browser_session_id)
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def start_chat(request: Request, response: Response, payload: ChatRequest):
    browser_session_id, _ = resolve_browser_session_id(request)
    set_browser_session_cookie(response, browser_session_id)
    try:
        return ChatResponse(
            chat_id=payload.chat_id or "streaming-endpoint-required",
            status="completed",
            output="Use /api/chat/stream for the real agent engine.",
        )
    except Exception:
        logger.exception("Chat test endpoint failed")
        raise HTTPException(
            status_code=500,
            detail="Chat test endpoint failed. Check backend logs.",
        )


@router.post("/chat/runs")
async def create_chat_run(request: Request, response: Response, payload: ChatRequest):
    browser_session_id, _ = resolve_browser_session_id(request)
    set_browser_session_cookie(response, browser_session_id)
    run = _start_run_task(payload, browser_session_id)
    return run


@router.get("/chat/runs/{run_id}")
def get_chat_run(run_id: str, request: Request, response: Response):
    browser_session_id, _ = resolve_browser_session_id(request)
    set_browser_session_cookie(response, browser_session_id)
    run = chat_repository.get_run(run_id, browser_session_id=browser_session_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/chat/runs/{run_id}/events")
def get_chat_run_events(
    run_id: str,
    request: Request,
    response: Response,
    after_sequence: int | None = Query(default=None),
    last_event_id: str | None = Query(default=None),
):
    browser_session_id, _ = resolve_browser_session_id(request)
    set_browser_session_cookie(response, browser_session_id)
    if chat_repository.get_run(run_id, browser_session_id=browser_session_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "events": chat_repository.list_stream_events(
            run_id,
            browser_session_id=browser_session_id,
            after_sequence=after_sequence,
            after_event_id=last_event_id,
        ),
    }


@router.get("/chat/runs/{run_id}/stream")
async def stream_chat_run(
    run_id: str,
    request: Request,
    after_sequence: int | None = Query(default=None),
    last_event_id: str | None = Query(default=None),
):
    browser_session_id, _ = resolve_browser_session_id(request)
    if chat_repository.get_run(run_id, browser_session_id=browser_session_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    response = StreamingResponse(
        _stream_run_events(run_id, browser_session_id, after_sequence, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    set_browser_session_cookie(response, browser_session_id)
    return response


@router.post("/chat/stream")
async def chat_stream(request: Request, payload: ChatRequest):
    browser_session_id, _ = resolve_browser_session_id(request)
    run = _start_run_task(payload, browser_session_id)
    response = StreamingResponse(
        _stream_run_events(
            run["run_id"],
            browser_session_id,
            after_sequence=None,
            last_event_id=payload.last_event_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    set_browser_session_cookie(response, browser_session_id)
    return response
