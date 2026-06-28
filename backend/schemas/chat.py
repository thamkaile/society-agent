from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None


class ChatResponse(BaseModel):
    chat_id: str
    status: str
    output: str