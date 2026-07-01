from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    client_message_id: Optional[str] = None
    run_id: Optional[str] = None
    last_event_id: Optional[str] = None


class ChatResponse(BaseModel):
    chat_id: str
    status: str
    output: str
