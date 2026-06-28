import time
import uuid

from sqlalchemy import Column, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(64), primary_key=True)
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
