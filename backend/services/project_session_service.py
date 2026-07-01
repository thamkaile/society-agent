from pathlib import Path
import json
import shutil

from persistence import repository as chat_repository
from services.agent_identity import enrich_event_agent_identity


class ProjectSessionService:
    def __init__(self, sessions_root: Path | None = None):
        self.sessions_root = Path(sessions_root) if sessions_root else None

    def list_sessions(self, browser_session_id: str | None = None):
        sessions = chat_repository.list_sessions(browser_session_id=browser_session_id)
        seen_ids = {session["id"] for session in sessions}
        sessions.extend(
            session
            for session in self._list_json_sessions(browser_session_id=browser_session_id)
            if session["id"] not in seen_ids
        )

        sessions.sort(
            key=lambda x: x.get("updated_at") or 0,
            reverse=True,
        )

        return sessions

    def _list_json_sessions(self, browser_session_id: str | None = None):
        sessions_root = self._sessions_root()
        if not sessions_root.exists():
            return []

        sessions = []

        for session_dir in sessions_root.iterdir():

            if not session_dir.is_dir():
                continue

            session_file = session_dir / "session.json"

            if not session_file.exists():
                continue

            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if (
                    browser_session_id is not None
                    and data.get("browser_session_id") != browser_session_id
                ):
                    continue

                sessions.append(
                    {
                        "id": data["chat_id"],
                        "chat_id": data["chat_id"],
                        "title": data.get("user_idea", "Untitled Session")[:80],
                        "summary": self._latest_summary(data),
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                    }
                )

            except Exception:
                continue

        sessions.sort(
            key=lambda x: x["updated_at"],
            reverse=True,
        )

        return sessions

    def get_session(self, chat_id: str, browser_session_id: str | None = None):
        from dynamic_engine.session_store import SessionStore
        store = SessionStore()
        db_session = chat_repository.get_session_with_messages(
            chat_id,
            browser_session_id=browser_session_id,
        )

        try:
            session = store.load(chat_id, browser_session_id=browser_session_id)
            data = session.to_dict()
        except (FileNotFoundError, PermissionError):
            if db_session is None:
                raise FileNotFoundError(f"No session found for chat_id {chat_id}")
            data = {
                "chat_id": db_session["id"],
                "created_at": db_session["created_at"],
                "updated_at": db_session["updated_at"],
                "user_idea": db_session["title"],
                "research_brief": {},
                "agent_briefs": {},
                "sections": {},
                "decision_log": [],
                "change_history": [],
            }

        if db_session is not None:
            data.update(
                {
                    "id": db_session["id"],
                    "chat_id": db_session["id"],
                    "title": db_session["title"],
                    "summary": db_session.get("summary"),
                    "created_at": db_session["created_at"],
                    "updated_at": db_session["updated_at"],
                    "messages": db_session.get("messages", []),
                    "latest_running_run": chat_repository.get_latest_running_run_for_session(
                        db_session["id"],
                        browser_session_id=browser_session_id,
                    ),
                }
            )
        else:
            data.update(
                {
                    "id": data["chat_id"],
                    "title": data.get("user_idea", "Untitled Session")[:80],
                    "summary": self._latest_summary(data),
                    "messages": self._messages_from_json_session(data),
                }
            )

        return data

    def delete_session(self, chat_id: str, browser_session_id: str | None = None):
        db_deleted = chat_repository.delete_session(
            chat_id,
            browser_session_id=browser_session_id,
        )
        json_deleted = self._delete_json_session(
            chat_id,
            browser_session_id=browser_session_id,
        )
        deleted = bool(db_deleted or json_deleted)
        return {
            "deleted": deleted,
            "ok": deleted,
            "deleted_chat_id": chat_id,
            "id": chat_id,
            "chat_id": chat_id,
        }

    def _sessions_root(self):
        if self.sessions_root is not None:
            return self.sessions_root
        return (
            Path(__file__).resolve().parents[1]
            / "run_artifacts"
            / "sessions"
        )

    def _delete_json_session(
        self,
        chat_id: str,
        browser_session_id: str | None = None,
    ) -> bool:
        from dynamic_engine.session_store import SessionStore

        store = SessionStore(self._sessions_root())
        root = store.base_dir.resolve()
        session_dir = store.session_dir(chat_id).resolve()
        if root not in session_dir.parents and session_dir != root:
            raise ValueError("Refusing to delete session outside run_artifacts")
        if not session_dir.exists():
            return False
        if browser_session_id is not None:
            try:
                session = store.load(chat_id, browser_session_id=browser_session_id)
            except (FileNotFoundError, PermissionError):
                return False
            if session.browser_session_id != browser_session_id:
                return False
        shutil.rmtree(session_dir)
        return True

    def _latest_summary(self, data: dict) -> str | None:
        decisions = data.get("decision_log") or []
        if not decisions:
            return None
        latest = decisions[-1] or {}
        summary = latest.get("summary")
        return str(summary) if summary else None

    def _messages_from_json_session(self, data: dict) -> list[dict]:
        messages = []
        chat_id = data.get("chat_id")
        created_at = float(data.get("created_at") or 0)
        user_idea = data.get("user_idea")
        if user_idea:
            messages.append(
                {
                    "id": f"{chat_id}:user",
                    "session_id": chat_id,
                    "role": "user",
                    "agent_name": "User",
                    "phase": None,
                    "content": user_idea,
                    "created_at": created_at,
                    "timestamp": created_at,
                    "metadata_json": {
                        "type": "user_input",
                        "agent": "User",
                        "content": user_idea,
                    },
                    "event": {
                        "type": "user_input",
                        "agent": "User",
                        "content": user_idea,
                    },
                }
            )

        for decision_index, decision in enumerate(data.get("decision_log") or []):
            base_time = float(decision.get("timestamp") or data.get("updated_at") or created_at)
            for round_item in decision.get("debate_rounds") or []:
                phase = round_item.get("stage")
                for response_index, response in enumerate(round_item.get("responses") or []):
                    event = {
                        "type": "agent_response",
                        "agent": response.get("agent"),
                        "content": response.get("content", ""),
                        "phase": phase,
                    }
                    event = enrich_event_agent_identity(event)
                    messages.append(
                        {
                            "id": f"{chat_id}:decision:{decision_index}:{phase}:{response_index}",
                            "session_id": chat_id,
                            "role": "assistant",
                            "agent_name": response.get("agent"),
                            "phase": phase,
                            "content": response.get("content", ""),
                            "created_at": base_time + response_index / 1000,
                            "timestamp": base_time + response_index / 1000,
                            "metadata_json": event,
                            "event": event,
                        }
                    )
            if decision.get("summary"):
                event = {
                    "type": "summarizer",
                    "agent": "Report Generator",
                    "content": decision.get("summary"),
                    "phase": "summary",
                }
                event = enrich_event_agent_identity(event)
                messages.append(
                    {
                        "id": f"{chat_id}:decision:{decision_index}:summary",
                        "session_id": chat_id,
                        "role": "assistant",
                        "agent_name": "Report Generator",
                        "phase": "summary",
                        "content": decision.get("summary"),
                        "created_at": base_time + 0.999,
                        "timestamp": base_time + 0.999,
                        "metadata_json": event,
                        "event": event,
                    }
                )

        messages.sort(key=lambda item: item.get("created_at") or 0)
        return messages
