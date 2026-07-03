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
from backend.api.session_identity import LEGACY_SESSION_COOKIE_NAME, SESSION_COOKIE_NAME
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
    def test_browser_session_create_touch_and_reference_detection(self):
        self.assertIsNone(repository.get_browser_session("11111111-1111-1111-1111-111111111111"))

        created = repository.create_browser_session("11111111-1111-1111-1111-111111111111")
        touched = repository.touch_browser_session("11111111-1111-1111-1111-111111111111")

        self.assertEqual(created["id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(touched["id"], created["id"])
        self.assertFalse(repository.browser_session_has_references(created["id"]))

        repository.create_session(
            session_id="session-refs-browser",
            browser_session_id=created["id"],
            title="Referenced session",
        )
        self.assertTrue(repository.browser_session_has_references(created["id"]))

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

    def test_project_state_persists_blueprint_sections(self):
        browser_session_id = "22222222-2222-2222-2222-222222222222"
        repository.create_browser_session(browser_session_id)
        repository.create_session(
            session_id="project-session",
            browser_session_id=browser_session_id,
            title="Build a project",
        )

        repository.apply_project_section_update(
            "project-session",
            "market_analysis",
            {"content": "Market evidence", "metadata": {"confidence": "high"}},
            browser_session_id=browser_session_id,
        )
        repository.save_project_state(
            "project-session",
            browser_session_id=browser_session_id,
            user_idea="Build a project",
            sections={
                "market_analysis": {"content": "Canonical market evidence"},
                "financial_plan": {"content": "Pricing"},
            },
            decision_log=[{"summary": "Proceed"}],
        )

        loaded = repository.get_session_with_messages(
            "project-session",
            browser_session_id=browser_session_id,
        )
        self.assertEqual(
            loaded["project_state"]["sections"]["market_analysis"]["content"],
            "Canonical market evidence",
        )
        self.assertEqual(loaded["project_state"]["decision_log"][0]["summary"], "Proceed")


class IntentRouterTests(unittest.TestCase):
    def test_classifies_casual_chat_without_workflow(self):
        self.assertEqual(classify_intent("Hey, how are you?").intent, CASUAL_CHAT)

    def test_classifies_business_idea(self):
        self.assertEqual(
            classify_intent("I want to build an AI platform for clinics").intent,
            BUSINESS_IDEA,
        )

    def test_classifies_guided_business_examples(self):
        prompts = [
            "I want to build an AI logistics platform for small businesses that reduces delivery costs.",
            "I want to create a meal planning app for university students that helps them eat on a budget.",
            "I want to start a cybersecurity consultancy for SMEs in Malaysia.",
            "I want to build a SaaS tool for HR teams that automates employee onboarding.",
        ]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(classify_intent(prompt).intent, BUSINESS_IDEA)

    def test_classifies_compact_structured_business_input(self):
        prompt = (
            "Product: AI logistics platform\n"
            "Target customer: small businesses\n"
            "Problem: high delivery costs\n"
            "Market: Southeast Asia"
        )
        self.assertEqual(classify_intent(prompt).intent, BUSINESS_IDEA)

    def test_classifies_quick_start_template(self):
        self.assertEqual(
            classify_intent("I want to build a FinTech for [target users] that solves [problem].").intent,
            BUSINESS_IDEA,
        )

    def test_classifies_natural_business_intention_with_location(self):
        self.assertEqual(
            classify_intent("I want to start a logistics company in England").intent,
            BUSINESS_IDEA,
        )

    def test_classifies_refinement_with_existing_chat(self):
        self.assertEqual(
            classify_intent("Refine the pricing strategy", has_existing_chat=True).intent,
            REFINEMENT,
        )

    def test_classifies_follow_up_with_existing_business_context(self):
        self.assertEqual(
            classify_intent("What licenses do I need?", has_existing_chat=True).intent,
            REFINEMENT,
        )

    def test_classifies_ambiguous_as_unknown(self):
        self.assertEqual(classify_intent("maybe").intent, UNKNOWN)


class FakeSimulationService:
    def __init__(self):
        self.called = False

    async def run_stream(
        self,
        message: str,
        chat_id: str | None = None,
        browser_session_id: str = "",
    ):
        self.called = True
        active_chat_id = chat_id or f"fake-session-{browser_session_id[:8] or 'legacy'}"
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
        if chat_id:
            yield {
                "type": "coordinator_routing",
                "agent": "Root Coordinator",
                "coordinator_selected_agent": "Business Analyst",
                "reason": "User asked for a commercial refinement.",
                "content": "Root Coordinator selected Business Analyst.",
            }
        yield {
            "type": "agent_response",
            "agent": "Business Analyst",
            "content": "Validate pricing first.",
        }
        yield {
            "type": "section_updated",
            "section": "market_analysis",
            "after": {
                "content": "Market analysis from stream",
                "metadata": {"validated_by": "Business Analyst"},
            },
            "content": "Updated section market_analysis",
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

    def stream_events_from_response(self, response):
        events = []
        for chunk in response.text.split("\n\n"):
            chunk = chunk.strip()
            if not chunk.startswith("data:"):
                continue
            events.append(json.loads(chunk.removeprefix("data:").strip()))
        return events

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
        self.assertIn(SESSION_COOKIE_NAME, self.client.cookies)
        self.assertIn("session_created", response.text)
        events = self.stream_events_from_response(response)
        chat_id = next(event["chat_id"] for event in events if event["type"] == "session_created")
        self.assertTrue(all(event.get("id") for event in events))
        self.assertTrue(all("run_id" in event for event in events))
        self.assertTrue(all("sequence" in event for event in events if event["type"] != "ping"))

        session_response = self.client.get(f"/api/sessions/{chat_id}")
        self.assertEqual(session_response.status_code, 200)
        session = session_response.json()

        self.assertEqual(session["id"], chat_id)
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
        self.assertEqual(
            session["sections"]["market_analysis"]["content"],
            "Market analysis from stream",
        )

        run_id = events[0]["run_id"]
        replay_response = self.client.get(
            f"/api/chat/runs/{run_id}/events",
            params={"after_sequence": events[0]["sequence"]},
        )
        self.assertEqual(replay_response.status_code, 200)
        replayed = replay_response.json()["events"]
        self.assertTrue(replayed)
        self.assertGreater(replayed[0]["sequence"], events[0]["sequence"])

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

    def test_client_message_id_prevents_duplicate_user_message(self):
        response = self.client.post(
            "/api/chat/stream",
            json={
                "message": "I want to start a logistics company in England",
                "chat_id": None,
                "client_message_id": "client-message-1",
            },
        )
        self.assertEqual(response.status_code, 200)
        events = self.stream_events_from_response(response)
        chat_id = next(event["chat_id"] for event in events if event["type"] == "session_created")
        session_response = self.client.get(f"/api/sessions/{chat_id}")
        self.assertEqual(session_response.status_code, 200)
        messages = session_response.json()["messages"]
        user_messages = [
            message
            for message in messages
            if message["metadata_json"].get("type") == "user_input"
        ]
        self.assertEqual(len(user_messages), 1)
        self.assertEqual(user_messages[0]["id"], "client-message-1")

    def test_existing_business_session_continues_with_same_chat_id(self):
        first_response = self.client.post(
            "/api/chat/stream",
            json={"message": "Build a pricing tool", "chat_id": None},
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertIn("session_created", first_response.text)
        first_events = self.stream_events_from_response(first_response)
        chat_id = next(event["chat_id"] for event in first_events if event["type"] == "session_created")

        self.fake_simulation_service.called = False
        follow_up_response = self.client.post(
            "/api/chat/stream",
            json={
                "message": "Refine the pricing strategy",
                "chat_id": chat_id,
            },
        )
        self.assertEqual(follow_up_response.status_code, 200)
        follow_up_events = self.stream_events_from_response(follow_up_response)

        self.assertTrue(self.fake_simulation_service.called)
        self.assertTrue(
            any(
                event.get("type") == "session_loaded"
                and event.get("chat_id") == chat_id
                for event in follow_up_events
            )
        )
        self.assertTrue(
            any(
                event.get("type") == "coordinator_routing"
                and event.get("coordinator_selected_agent") == "Business Analyst"
                for event in follow_up_events
            )
        )
        self.assertTrue(
            any(
                event.get("type") == "session_saved"
                and event.get("chat_id") == chat_id
                for event in follow_up_events
            )
        )

        browser_session_id = self.client.cookies.get(SESSION_COOKIE_NAME)
        loaded = repository.get_session_with_messages(
            chat_id,
            browser_session_id=browser_session_id,
        )
        user_messages = [
            message
            for message in loaded["messages"]
            if message["metadata_json"].get("type") == "user_input"
        ]
        self.assertEqual([message["content"] for message in user_messages], [
            "Build a pricing tool",
            "Refine the pricing strategy",
        ])

    def test_browser_cookie_scopes_session_lists_and_session_access(self):
        first_response = self.client.post(
            "/api/chat/stream",
            json={"message": "Build a pricing tool", "chat_id": None},
        )
        self.assertEqual(first_response.status_code, 200)
        first_cookie = self.client.cookies.get(SESSION_COOKIE_NAME)
        first_events = self.stream_events_from_response(first_response)
        first_chat_id = next(
            event["chat_id"] for event in first_events if event["type"] == "session_created"
        )

        second_client = TestClient(self.app)
        second_list = second_client.get("/api/sessions")
        self.assertEqual(second_list.status_code, 200)
        second_cookie = second_client.cookies.get(SESSION_COOKIE_NAME)

        self.assertIsNotNone(first_cookie)
        self.assertIsNotNone(second_cookie)
        self.assertNotEqual(first_cookie, second_cookie)
        self.assertEqual(second_list.json(), [])
        self.assertEqual(second_client.get(f"/api/sessions/{first_chat_id}").status_code, 404)
        self.assertEqual(second_client.delete(f"/api/sessions/{first_chat_id}").status_code, 404)
        self.assertEqual(
            second_client.get(f"/api/chat/runs/{first_events[0]['run_id']}/events").status_code,
            404,
        )

        refreshed_list = self.client.get("/api/sessions")
        self.assertEqual(refreshed_list.status_code, 200)
        self.assertEqual(self.client.cookies.get(SESSION_COOKIE_NAME), first_cookie)
        self.assertEqual([session["id"] for session in refreshed_list.json()], [first_chat_id])

    def test_stale_cookie_is_replaced_after_database_reset(self):
        stale_browser_session_id = "33333333-3333-3333-3333-333333333333"
        self.client.cookies.set(
            SESSION_COOKIE_NAME,
            stale_browser_session_id,
            domain="testserver.local",
        )

        response = self.client.get("/api/sessions")

        self.assertEqual(response.status_code, 200)
        replacement = self.client.cookies.get(SESSION_COOKIE_NAME)
        self.assertIsNotNone(replacement)
        self.assertNotEqual(replacement, stale_browser_session_id)
        self.assertIsNotNone(repository.get_browser_session(replacement))

    def test_legacy_cookie_is_registered_when_it_owns_data(self):
        legacy_browser_session_id = "44444444-4444-4444-4444-444444444444"
        repository.create_session(
            session_id="legacy-owned-chat",
            browser_session_id=legacy_browser_session_id,
            title="Legacy owned chat",
        )
        legacy_client = TestClient(self.app)
        legacy_client.cookies.set(
            LEGACY_SESSION_COOKIE_NAME,
            legacy_browser_session_id,
            domain="testserver.local",
        )

        response = legacy_client.get("/api/sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [session["id"] for session in response.json()],
            ["legacy-owned-chat"],
        )
        self.assertEqual(legacy_client.cookies.get(SESSION_COOKIE_NAME), legacy_browser_session_id)

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
        self.client.get("/api/health")
        browser_session_id = self.client.cookies.get(SESSION_COOKIE_NAME)
        repository.create_session(
            "delete-me",
            browser_session_id=browser_session_id,
            title="Delete me",
        )
        repository.save_message(
            session_id="delete-me",
            browser_session_id=browser_session_id,
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
                    "browser_session_id": browser_session_id,
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
