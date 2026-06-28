# memory_store.py
from typing import List, Dict

try:
    from backend.runtime_bootstrap import bootstrap_runtime
except ImportError:
    from runtime_bootstrap import bootstrap_runtime

bootstrap_runtime()

from ..models.models import Message


def _camel_memory_types():
    from camel.memories import ChatHistoryBlock, MemoryRecord
    from camel.messages import BaseMessage
    from camel.types import OpenAIBackendRole

    return ChatHistoryBlock, MemoryRecord, BaseMessage, OpenAIBackendRole


class ChatHistoryMemory:
    """Per‑agent short‑term memory (unchanged)."""
    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self.messages: List[str] = []

    def add_user_message(self, text: str):
        self.messages.append(f"User: {text}")

    def add_agent_message(self, text: str):
        self.messages.append(f"Assistant: {text}")

    def get_recent(self, limit: int = 10) -> str:
        return "\n".join(self.messages[-limit:])

    def clear(self):
        self.messages.clear()


class MemoryStore:
    def __init__(self, persist_dir: str = ""):
        # Use only CAMEL's ChatHistoryBlock (no vector DB, no embeddings)
        ChatHistoryBlock, _, _, _ = _camel_memory_types()
        self.chat_history = ChatHistoryBlock()
        self.agent_memories: Dict[str, ChatHistoryMemory] = {}

    def get_agent_memory(self, agent_name: str) -> ChatHistoryMemory:
        if agent_name not in self.agent_memories:
            self.agent_memories[agent_name] = ChatHistoryMemory(
                session_id=f"agent_{agent_name}"
            )
        return self.agent_memories[agent_name]

    def add_agent_memory(self, agent_name: str, label: str, content: str):
        memory = self.get_agent_memory(agent_name)
        memory.add_agent_message(f"{label}: {content}")

    def get_agent_context(self, agent_name: str, limit: int = 8) -> str:
        return self.get_agent_memory(agent_name).get_recent(limit=limit)

    def clear_agent_memories(self):
        self.agent_memories.clear()

    def add_message(self, msg: Message):
        _, MemoryRecord, BaseMessage, OpenAIBackendRole = _camel_memory_types()
        if msg.agent == "User":
            base_msg = BaseMessage.make_user_message(
                role_name="User",
                meta_dict=None,
                content=msg.content,
            )
            backend_role = OpenAIBackendRole.USER
        else:
            base_msg = BaseMessage.make_assistant_message(
                role_name=msg.agent,
                meta_dict=None,
                content=msg.content,
            )
            backend_role = OpenAIBackendRole.ASSISTANT

        record = MemoryRecord(message=base_msg, role_at_backend=backend_role)
        # Write to CAMEL's chat history (no embeddings)
        self.chat_history.write_records([record])

    def retrieve_relevant(self, query: str, limit: int = 5) -> List[Message]:
        # Retrieve all records from the chat history block
        # Note: retrieve() returns a list of ContextRecord objects, NOT MemoryRecord.
        all_records = self.chat_history.retrieve()
        recent = all_records[-limit:] if all_records else []
        msgs = []
        for record in recent:
            # Access the actual MemoryRecord via .memory_record, then get the message
            base_msg = record.memory_record.message   # <-- FIXED
            msgs.append(Message(
                agent=base_msg.role_name,
                content=base_msg.content,
            ))
        return msgs
