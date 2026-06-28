import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from schemas.chat import ChatRequest, ChatResponse
from persistence import repository as chat_repository
from services.simulation_service import SimulationService
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
    }:
        return "assistant"
    return "system"


def _persist_stream_event(
    session_id: str | None,
    event: dict,
    title: str,
) -> str | None:
    persisted_event = _event_for_persistence(event)
    event_type = event.get("type", "")
    event_chat_id = event.get("chat_id")
    active_session_id = event_chat_id or session_id

    if event_chat_id:
        chat_repository.create_session(
            session_id=event_chat_id,
            title=title,
        )

    if not active_session_id:
        return None

    chat_repository.save_message(
        session_id=active_session_id,
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
        )

    return active_session_id


def _event_for_persistence(event: dict) -> dict:
    if event.get("type") != "research_complete":
        return dict(event)

    allowed = {
        "type",
        "agent",
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
    user_message: str,
    assistant_reply: str,
    assistant_event_type: str,
    intent: str,
) -> str:
    session = chat_repository.create_session(
        session_id=session_id,
        title=user_message,
    )
    active_session_id = session["id"]
    timestamp = time.time()
    chat_repository.save_message(
        session_id=active_session_id,
        role="user",
        agent_name="User",
        content=user_message,
        metadata_json={
            "type": "user_input",
            "agent": "User",
            "content": user_message,
            "intent": intent,
        },
        created_at=timestamp,
        title=user_message,
    )
    chat_repository.save_message(
        session_id=active_session_id,
        role="assistant",
        agent_name="Genesis",
        content=assistant_reply,
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


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def start_chat(request: ChatRequest):
    """
    Temporary test endpoint.
    Real agent engine uses /api/chat/stream.
    """
    try:
        return ChatResponse(
            chat_id=request.chat_id or "streaming-endpoint-required",
            status="completed",
            output="Use /api/chat/stream for the real agent engine.",
        )

    except Exception:
        logger.exception("Chat test endpoint failed")
        raise HTTPException(
            status_code=500,
            detail="Chat test endpoint failed. Check backend logs.",
        )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Real streaming endpoint for DynamicStreamingEngine.

    New project:
    {
      "message": "Simulate an online car parts business",
      "chat_id": null
    }

    Refinement:
    {
      "message": "Refine the pricing strategy",
      "chat_id": "existing-chat-id"
    }
    """

    async def event_generator():
        active_chat_id = request.chat_id
        intent_result = classify_intent(
            request.message,
            has_existing_chat=bool(request.chat_id),
        )

        if intent_result.intent in {CASUAL_CHAT, UNKNOWN}:
            reply = (
                casual_chat_reply(request.message)
                if intent_result.intent == CASUAL_CHAT
                else unknown_intent_reply()
            )
            assistant_event_type = (
                "casual_chat" if intent_result.intent == CASUAL_CHAT else "clarification"
            )
            try:
                active_chat_id = _persist_direct_exchange(
                    active_chat_id,
                    request.message,
                    reply,
                    assistant_event_type,
                    intent_result.intent,
                )
            except Exception:
                logger.exception("Failed to persist direct intent exchange")

            if not request.chat_id and active_chat_id:
                yield f"data: {json.dumps({'type': 'session_created', 'chat_id': active_chat_id, 'content': f'Created chat session {active_chat_id}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'user_input', 'agent': 'User', 'chat_id': active_chat_id, 'content': request.message, 'intent': intent_result.intent}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': assistant_event_type, 'agent': 'Genesis', 'chat_id': active_chat_id, 'content': reply, 'intent': intent_result.intent}, ensure_ascii=False)}\n\n"
            return

        if intent_result.intent not in {BUSINESS_IDEA, REFINEMENT}:
            logger.info("Unhandled intent %s; falling back to full workflow", intent_result)

        if active_chat_id:
            try:
                chat_repository.create_session(
                    session_id=active_chat_id,
                    title=request.message,
                )
                chat_repository.save_message(
                    session_id=active_chat_id,
                    role="user",
                    agent_name="User",
                    content=request.message,
                    metadata_json={
                        "type": "user_input",
                        "agent": "User",
                        "content": request.message,
                    },
                    title=request.message,
                )
            except Exception:
                logger.exception("Failed to persist incoming user message")

        try:
            async for event in simulation_service.run_stream(
                message=request.message,
                chat_id=request.chat_id,
            ):
                try:
                    active_chat_id = _persist_stream_event(
                        active_chat_id,
                        event,
                        request.message,
                    )
                except Exception:
                    logger.exception("Failed to persist stream event")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.exception("Streaming chat failed")

            error_event = {
                "type": "error",
                "content": "Streaming chat failed. Check backend logs.",
                "detail": str(e),
            }

            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
