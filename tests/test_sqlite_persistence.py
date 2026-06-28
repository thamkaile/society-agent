import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from backend.runtime_bootstrap import bootstrap_runtime

bootstrap_runtime()

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import routes_chat, routes_session
from backend.services.intent_router import (
    BUSINESS_IDEA,
    CASUAL_CHAT,
    REFINEMENT,
    UNKNOWN,
    classify_intent,
)
from backend.services.project_session_service import ProjectSessionService
from persistence import repository
from persistence.database import Base, create_session_factory, create_sqlite_engine


class TempDatabaseMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "chat.sqlite3"
        self.engine = create_sqlite_engine(self.db_path)
        Base.metadata.create_all(self.engine)
        self.session_factory = create_session_factory(self.engine)
        self.original_session_local = repository.SessionLocal
        repository.SessionLocal = self.session_factory

    def tearDown(self):
        repository.SessionLocal = self.original_session_local
        self.engine.dispose()
        self.tmp.cleanup()


class RepositoryPersistenceTests(TempDatabaseMixin, unittest.TestCase):
    def test_create_save_list_get_delete_round_trip(self):
        repository.create_session(
            session_id="session-1",
            title="Build a durable chat app",
        )
        repository.save_message(
            session_id="session-1",
            role="user",
            agent_name="User",
            content="Build a durable chat app",
            metadata_json={"type": "user_input"},
        )
        repository.save_message(
            session_id="session-1",
            role="assistant",
            agent_name="Report Generator",
            phase="summary",
            content="Final report",
            metadata_json={"type": "summarizer"},
        )
        repository.update_session_summary("session-1", "Final report")

        sessions = repository.list_sessions()
        loaded = repository.get_session_with_messages("session-1")

        self.assertEqual(sessions[0]["id"], "session-1")
        self.assertEqual(loaded["summary"], "Final report")
        self.assertEqual(
            [message["role"] for message in loaded["messages"]],
            ["user", "assistant"],
        )
        self.assertEqual(loaded["messages"][1]["metadata_json"]["type"], "summarizer")

        self.assertTrue(repository.delete_session("session-1"))
        self.assertIsNone(repository.get_session_with_messages("session-1"))


class IntentRouterTests(unittest.TestCase):
    def test_classifies_casual_chat_without_workflow(self):
        self.assertEqual(classify_intent("Hey, how are you?").intent, CASUAL_CHAT)

    def test_classifies_business_idea(self):
        self.assertEqual(
            classify_intent("I want to build an AI platform for clinics").intent,
            BUSINESS_IDEA,
        )

    def test_classifies_refinement_with_existing_chat(self):
        self.assertEqual(
            classify_intent("Refine the pricing strategy", has_existing_chat=True).intent,
            REFINEMENT,
        )

    def test_classifies_ambiguous_as_unknown(self):
        self.assertEqual(classify_intent("maybe").intent, UNKNOWN)


class FakeSimulationService:
    def __init__(self):
        self.called = False

    async def run_stream(self, message: str, chat_id: str | None = None):
        self.called = True
        active_chat_id = chat_id or "fake-session"
        if chat_id:
            yield {
                "type": "session_loaded",
                "chat_id": active_chat_id,
                "content": f"Loaded project session {active_chat_id}",
            }
        else:
            yield {
                "type": "session_created",
                "chat_id": active_chat_id,
                "content": f"Created project session {active_chat_id}",
            }
            yield {
                "type": "user_input",
                "agent": "User",
                "content": message,
            }

        yield {
            "type": "research_complete",
            "agent": "Research Agent",
            "content": "Research Agent summary\nSources:\n- Example: https://example.com",
            "status": "success",
            "research_quality": "moderate",
            "source_count": 1,
            "objective_count": 1,
            "artifact_path": "/tmp/research_brief.json",
            "agent_briefs_path": "/tmp/agent_briefs.json",
            "research": {"objectives": [{"raw": "x" * 5000}]},
            "research_brief": "{\"objectives\": [{\"raw\": \"huge\"}]}",
        }
        yield {
            "type": "phase",
            "phase": "debate",
            "content": "Debate Phase",
        }
        yield {
            "type": "agent_response",
            "agent": "Business Analyst",
            "content": "Validate pricing first.",
        }
        yield {
            "type": "summarizer",
            "agent": "Report Generator",
            "content": "Final report: validate pricing first.",
        }
        yield {
            "type": "session_saved",
            "chat_id": active_chat_id,
            "content": f"Saved project session {active_chat_id}",
        }
        await asyncio.sleep(0)


class EndpointPersistenceTests(TempDatabaseMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.original_simulation_service = routes_chat.simulation_service
        self.original_session_service = routes_session.session_service
        self.fake_simulation_service = FakeSimulationService()
        routes_chat.simulation_service = self.fake_simulation_service
        self.sessions_root = Path(self.tmp.name) / "sessions"
        routes_session.session_service = ProjectSessionService(self.sessions_root)
        self.app = FastAPI()
        self.app.include_router(routes_chat.router, prefix="/api")
        self.app.include_router(routes_session.router, prefix="/api")
        self.client = TestClient(self.app)

    def tearDown(self):
        routes_chat.simulation_service = self.original_simulation_service
        routes_session.session_service = self.original_session_service
        super().tearDown()

    def test_streamed_events_are_saved_and_reopened_chronologically(self):
        response = self.client.post(
            "/api/chat/stream",
            json={"message": "Build a pricing tool", "chat_id": None},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("session_created", response.text)

        session_response = self.client.get("/api/sessions/fake-session")
        self.assertEqual(session_response.status_code, 200)
        session = session_response.json()

        self.assertEqual(session["id"], "fake-session")
        event_types = [
            message["metadata_json"].get("type")
            for message in session["messages"]
        ]
        self.assertEqual(
            event_types,
            [
                "session_created",
                "user_input",
                "research_complete",
                "phase",
                "agent_response",
                "summarizer",
                "session_saved",
            ],
        )
        self.assertEqual(session["messages"][1]["role"], "user")
        research_message = session["messages"][2]
        self.assertLess(len(research_message["content"]), 3000)
        self.assertIn("https://example.com", research_message["content"])
        self.assertEqual(
            research_message["metadata_json"]["artifact_path"],
            "/tmp/research_brief.json",
        )
        self.assertEqual(research_message["metadata_json"]["source_count"], 1)
        self.assertNotIn("research", research_message["metadata_json"])
        self.assertNotIn("research_brief", research_message["metadata_json"])
        self.assertEqual(session["summary"], "Final report: validate pricing first.")

    def test_casual_chat_is_persisted_without_agent_workflow(self):
        response = self.client.post(
            "/api/chat/stream",
            json={"message": "Hello", "chat_id": None},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("casual_chat", response.text)
        self.assertNotIn("research_complete", response.text)
        self.assertFalse(self.fake_simulation_service.called)

        sessions = repository.list_sessions()
        self.assertEqual(len(sessions), 1)
        loaded = repository.get_session_with_messages(sessions[0]["id"])
        self.assertEqual(
            [message["metadata_json"].get("type") for message in loaded["messages"]],
            ["user_input", "casual_chat"],
        )

    def test_unknown_intent_asks_for_clarification_without_agent_workflow(self):
        response = self.client.post(
            "/api/chat/stream",
            json={"message": "maybe", "chat_id": None},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("clarification", response.text)
        self.assertNotIn("research_complete", response.text)
        self.assertFalse(self.fake_simulation_service.called)

    def test_delete_session_removes_database_and_artifacts(self):
        repository.create_session("delete-me", title="Delete me")
        repository.save_message(
            session_id="delete-me",
            role="user",
            agent_name="User",
            content="Delete me",
            metadata_json={"type": "user_input"},
        )
        session_dir = self.sessions_root / "delete-me"
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text(
            json.dumps(
                {
                    "chat_id": "delete-me",
                    "user_idea": "Delete me",
                    "created_at": 1,
                    "updated_at": 2,
                    "decision_log": [],
                }
            ),
            encoding="utf-8",
        )

        response = self.client.delete("/api/sessions/delete-me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "deleted_chat_id": "delete-me"})
        self.assertIsNone(repository.get_session_with_messages("delete-me"))
        self.assertFalse(session_dir.exists())
        self.assertNotIn(
            "delete-me",
            [session["id"] for session in self.client.get("/api/sessions").json()],
        )
        self.assertEqual(self.client.get("/api/sessions/delete-me").status_code, 404)

    def test_delete_missing_session_returns_404(self):
        response = self.client.delete("/api/sessions/missing-session")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
