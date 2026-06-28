from uuid import uuid4

_sessions = {}


def create_or_get_session(chat_id: str | None):
    if chat_id is None:
        chat_id = str(uuid4())
        _sessions[chat_id] = []

    if chat_id not in _sessions:
        _sessions[chat_id] = []

    return chat_id, _sessions[chat_id]


def add_message(chat_id: str, role: str, content: str):
    _sessions.setdefault(chat_id, [])
    _sessions[chat_id].append({
        "role": role,
        "content": content
    })


def get_session(chat_id: str):
    return _sessions.get(chat_id)