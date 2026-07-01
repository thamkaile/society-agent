import time
import uuid

from sqlalchemy import Boolean, Column, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(64), primary_key=True)
    browser_session_id = Column(String(64), nullable=True, index=True)
    title = Column(String(255), nullable=False, default="Untitled Session")
    summary = Column(Text, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=False, default=time.time)

    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at, ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(32), nullable=False)
    agent_name = Column(String(255), nullable=True)
    phase = Column(String(64), nullable=True)
    content = Column(Text, nullable=False, default="")
    created_at = Column(Float, nullable=False, default=time.time)
    metadata_json = Column(JSON, nullable=False, default=dict)

    session = relationship("ChatSession", back_populates="messages")


Index("ix_chat_messages_session_created", ChatMessage.session_id, ChatMessage.created_at)


class ChatRun(Base):
    __tablename__ = "chat_runs"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    browser_session_id = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="idle")
    intent = Column(String(64), nullable=True)
    message = Column(Text, nullable=False, default="")
    client_message_id = Column(String(128), nullable=True, index=True)
    has_business_context = Column(Boolean, nullable=False, default=False)
    error = Column(Text, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=False, default=time.time)
    completed_at = Column(Float, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)

    events = relationship(
        "ChatStreamEvent",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ChatStreamEvent.sequence, ChatStreamEvent.created_at",
    )


class ChatStreamEvent(Base):
    __tablename__ = "chat_stream_events"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(
        String(64),
        ForeignKey("chat_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    browser_session_id = Column(String(64), nullable=True, index=True)
    sequence = Column(Integer, nullable=False)
    type = Column(String(64), nullable=False)
    role = Column(String(32), nullable=False, default="system")
    agent_name = Column(String(255), nullable=True)
    phase = Column(String(64), nullable=True)
    content = Column(Text, nullable=False, default="")
    created_at = Column(Float, nullable=False, default=time.time)
    visible = Column(Boolean, nullable=False, default=True)
    payload_json = Column(JSON, nullable=False, default=dict)

    run = relationship("ChatRun", back_populates="events")


Index("ix_chat_stream_events_run_sequence", ChatStreamEvent.run_id, ChatStreamEvent.sequence)
Index("ix_chat_runs_session_created", ChatRun.session_id, ChatRun.created_at)
Index("ix_chat_sessions_browser_updated", ChatSession.browser_session_id, ChatSession.updated_at)
Index("ix_chat_runs_browser_created", ChatRun.browser_session_id, ChatRun.created_at)
