# session_store.py
import json
from pathlib import Path

from .models.models import ChatSession


class SessionStore:
    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = (
                Path(__file__).resolve().parents[1]
                / "run_artifacts"
                / "sessions"
            )
        self.base_dir = Path(base_dir)

    def session_dir(self, chat_id: str) -> Path:
        chat_id = str(chat_id).strip()
        if not chat_id:
            raise ValueError("chat_id is required")
        return self.base_dir / chat_id

    def create(self, user_idea: str) -> ChatSession:
        session = ChatSession(user_idea=user_idea)
        self.save(session)
        return session

    def load(self, chat_id: str) -> ChatSession:
        path = self.session_dir(chat_id) / "session.json"
        if not path.exists():
            raise FileNotFoundError(f"No session found for chat_id {chat_id}")

        with path.open("r", encoding="utf-8") as f:
            return ChatSession.from_dict(json.load(f))

    def save(self, session: ChatSession) -> Path:
        session.ensure_sections()
        session.touch()
        path = self.session_dir(session.chat_id) / "session.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        return path
