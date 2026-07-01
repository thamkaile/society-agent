import tempfile
import os
import sys
import types
import unittest
import time
import asyncio
import json
import tempfile
from pathlib import Path


def install_engine_import_stubs():
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv)

    camel = types.ModuleType("camel")
    camel_agents = types.ModuleType("camel.agents")
    camel_models = types.ModuleType("camel.models")
    camel_messages = types.ModuleType("camel.messages")
    camel_memories = types.ModuleType("camel.memories")
    camel_types = types.ModuleType("camel.types")

    class DummyChatAgent:
        instances = []

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.model = kwargs.get("model")
            DummyChatAgent.instances.append(self)

        def reset(self):
            pass

    class DummyModelFactory:
        calls = []

        @staticmethod
        def create(*args, **kwargs):
            DummyModelFactory.calls.append({"args": args, "kwargs": kwargs})
            return types.SimpleNamespace(
                model_type=kwargs.get("model_type"),
                model_platform=kwargs.get("model_platform"),
                kwargs=kwargs,
            )

    class DummyBaseMessage:
        @staticmethod
        def make_user_message(role_name, meta_dict, content):
            return types.SimpleNamespace(role_name=role_name, content=content)

        @staticmethod
        def make_assistant_message(role_name, meta_dict, content):
            return types.SimpleNamespace(role_name=role_name, content=content)

    class DummyChatHistoryBlock:
        def __init__(self):
            self.records = []

        def write_records(self, records):
            self.records.extend(records)

        def retrieve(self):
            return [
                types.SimpleNamespace(memory_record=record)
                for record in self.records
            ]

    class DummyMemoryRecord:
        def __init__(self, message, role_at_backend):
            self.message = message
            self.role_at_backend = role_at_backend

    camel_agents.ChatAgent = DummyChatAgent
    camel_agents.DummyChatAgent = DummyChatAgent
    camel_models.ModelFactory = DummyModelFactory
    camel_models.DummyModelFactory = DummyModelFactory
    camel_messages.BaseMessage = DummyBaseMessage
    camel_memories.ChatHistoryBlock = DummyChatHistoryBlock
    camel_memories.MemoryRecord = DummyMemoryRecord
    camel_types.ModelPlatformType = types.SimpleNamespace(
        OPENAI_COMPATIBLE_MODEL="openai_compatible"
    )
    camel_types.OpenAIBackendRole = types.SimpleNamespace(
        USER="user",
        ASSISTANT="assistant",
    )

    sys.modules.setdefault("camel", camel)
    sys.modules.setdefault("camel.agents", camel_agents)
    sys.modules.setdefault("camel.models", camel_models)
    sys.modules.setdefault("camel.messages", camel_messages)
    sys.modules.setdefault("camel.memories", camel_memories)
    sys.modules.setdefault("camel.types", camel_types)


install_engine_import_stubs()

from backend.dynamic_engine.core.engine import DynamicStreamingEngine
from backend.dynamic_engine.config import load_engine_config
from backend.dynamic_engine.config.schema import normalize_new_config
from backend.dynamic_engine.agents.model_factory import ConfiguredModelFactory
from backend.dynamic_engine.core.research_flow import ResearchOrchestrator, ResearchRunResult
from backend.dynamic_engine.models.models import CANONICAL_SECTIONS, ImpactAssessment
from backend.dynamic_engine.models.models import Message
from backend.dynamic_engine.models.research import StructuredResearch
from backend.dynamic_engine.session_store import SessionStore
from backend.research.tavily_research import TavilyResearch


class SessionStoreTests(unittest.TestCase):
    def test_create_load_save_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create("Build a smart pantry assistant")
            session.sections["business_plan"] = {"content": "Freemium plan"}
            path = store.save(session)

            loaded = store.load(session.chat_id)

            self.assertTrue(path.exists())
            self.assertEqual(loaded.chat_id, session.chat_id)
            self.assertEqual(loaded.user_idea, "Build a smart pantry assistant")
            self.assertEqual(
                loaded.sections["market_analysis"]["content"],
                "Freemium plan",
            )
            self.assertEqual(set(CANONICAL_SECTIONS), set(loaded.sections.keys()))


class ImpactParserTests(unittest.TestCase):
    def make_engine(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.agents = {
            "Product Manager": object(),
            "Technical Lead": object(),
            "Business Analyst": object(),
            "UX Researcher": object(),
            "MVP Agent": object(),
        }
        engine.COORDINATOR_ROLE = "Product Manager"
        return engine

    def test_parse_valid_impact_assessment(self):
        engine = self.make_engine()
        impact = engine._parse_impact_assessment(
            """
            ```json
            {
              "affected_sections": ["business", "finance"],
              "agents_needed": ["Business Analyst"],
              "need_research": false,
              "research_questions": [],
              "rationale": "Pricing only"
            }
            ```
            """,
            "Refine pricing",
        )

        self.assertEqual(
            impact.affected_sections,
            ["market_analysis", "financial_plan"],
        )
        self.assertEqual(
            impact.agents_needed,
            ["Business Analyst", "Product Manager"],
        )
        self.assertFalse(impact.need_research)

    def test_malformed_impact_assessment_uses_conservative_fallback(self):
        engine = self.make_engine()
        impact = engine._parse_impact_assessment("not json", "Can this work in Japan?")

        self.assertEqual(impact.affected_sections, list(CANONICAL_SECTIONS))
        self.assertIn("Product Manager", impact.agents_needed)
        self.assertTrue(impact.need_research)
        self.assertEqual(impact.research_questions, ["Can this work in Japan?"])


class HybridConfigTests(unittest.TestCase):
    def setUp(self):
        from camel.agents import DummyChatAgent
        from camel.models import DummyModelFactory

        DummyChatAgent.instances.clear()
        DummyModelFactory.calls.clear()

    def test_loaded_config_uses_core_and_standby_without_legacy_keys(self):
        config = load_engine_config(Path("backend"))

        self.assertIn("core_team", config)
        self.assertIn("standby_specialists", config)
        self.assertIn("agent_planner", config)
        self.assertNotIn("workers", config)
        self.assertNotIn("workforce_config", config)
        self.assertNotIn("task_agent", config)
        self.assertNotIn("workflow_agent", config)

        core_ids = {agent["id"] for agent in config["core_team"]}
        self.assertIn("root_coordinator", core_ids)
        self.assertIn("research_agent", core_ids)
        self.assertIn("report_generator", core_ids)
        self.assertTrue(config["standby_specialists"])

    def test_top_level_agents_json_fallback_is_removed(self):
        self.assertFalse(Path("backend/agents.json").exists())

    def test_loaded_config_preserves_models_json_registry(self):
        config = load_engine_config(Path("backend"))
        models = config["models_config"]["models"]

        self.assertEqual(config["models_config"]["default_model_id"], "default")
        self.assertIn("default", models)
        self.assertEqual(config["model_config"]["model_id"], "default")
        self.assertEqual(config["model_config"]["model_type"], "xiaomi/mimo-v2-pro")
        self.assertEqual(models["default"]["platform"], "openai_compatible")

    def test_configured_model_factory_passes_models_json_values_to_camel(self):
        from camel.models import DummyModelFactory

        previous_key = os.environ.get("ACME_API_KEY")
        previous_openai_key = os.environ.get("OPENAI_API_KEY")
        os.environ["ACME_API_KEY"] = "acme-secret"
        os.environ["OPENAI_API_KEY"] = "do-not-change"
        try:
            factory = ConfiguredModelFactory(
                {
                    "default_model_id": "default",
                    "models": {
                        "default": {
                            "provider": "acme",
                            "platform": "openai_compatible",
                            "model_type": "acme/text-large",
                            "api_url": "https://models.example.test/v1",
                            "api_key_env": "ACME_API_KEY",
                            "timeout": 42,
                            "max_retries": 5,
                            "temperature": 0.2,
                            "model_config": {"top_p": 0.9},
                            "client_options": {"organization": "org_123"},
                        }
                    },
                }
            )

            model = factory.get_model()
            call = DummyModelFactory.calls[-1]["kwargs"]

            self.assertEqual(model.model_type, "acme/text-large")
            self.assertEqual(call["model_platform"], "openai-compatible-model")
            self.assertEqual(call["url"], "https://models.example.test/v1")
            self.assertEqual(call["api_key"], "acme-secret")
            self.assertEqual(call["timeout"], 42)
            self.assertEqual(call["max_retries"], 5)
            self.assertEqual(call["organization"], "org_123")
            self.assertEqual(
                call["model_config_dict"],
                {"top_p": 0.9, "temperature": 0.2},
            )
            self.assertEqual(os.environ.get("OPENAI_API_KEY"), "do-not-change")
        finally:
            if previous_key is None:
                os.environ.pop("ACME_API_KEY", None)
            else:
                os.environ["ACME_API_KEY"] = previous_key
            if previous_openai_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_openai_key

    def test_configured_model_factory_uses_provider_env_convention(self):
        from camel.models import DummyModelFactory

        previous_key = os.environ.get("DASHSCOPE_API_KEY")
        os.environ["DASHSCOPE_API_KEY"] = "dashscope-secret"
        try:
            factory = ConfiguredModelFactory(
                {
                    "default_model_id": "default",
                    "models": {
                        "default": {
                            "provider": "dashscope",
                            "platform": "openai_compatible",
                            "model_type": "dashscope-model",
                            "api_url": "https://dashscope.example.test/v1",
                        }
                    },
                }
            )

            factory.get_model()
            call = DummyModelFactory.calls[-1]["kwargs"]

            self.assertEqual(call["api_key"], "dashscope-secret")
            self.assertEqual(call["model_platform"], "openai-compatible-model")
        finally:
            if previous_key is None:
                os.environ.pop("DASHSCOPE_API_KEY", None)
            else:
                os.environ["DASHSCOPE_API_KEY"] = previous_key

    def test_configured_model_factory_reports_missing_api_key_env(self):
        os.environ.pop("MISSING_PROVIDER_API_KEY", None)
        factory = ConfiguredModelFactory(
            {
                "default_model_id": "default",
                "models": {
                    "default": {
                        "provider": "missing-provider",
                        "platform": "openai_compatible",
                        "model_type": "missing-model",
                        "api_url": "https://missing.example.test/v1",
                    }
                },
            }
        )

        with self.assertRaisesRegex(RuntimeError, "MISSING_PROVIDER_API_KEY"):
            factory.get_model()

    def test_agent_model_id_selects_configured_model(self):
        from camel.agents import DummyChatAgent

        previous_default = os.environ.get("DEFAULT_MODEL_API_KEY")
        previous_planner = os.environ.get("PLANNER_MODEL_API_KEY")
        os.environ["DEFAULT_MODEL_API_KEY"] = "default-secret"
        os.environ["PLANNER_MODEL_API_KEY"] = "planner-secret"
        try:
            config = normalize_new_config(
                {
                    "version": "test",
                    "coordinator_agent_id": "root_coordinator",
                    "core_team": [
                        {
                            "id": "root_coordinator",
                            "role": "Root Coordinator",
                            "model_id": "planner",
                        },
                        {
                            "id": "research_agent",
                            "role": "Research Agent",
                            "model_id": "default",
                        },
                    ],
                    "planner": {
                        "id": "agent_planner",
                        "role": "Agent Planner",
                        "model_id": "default",
                    },
                },
                {},
                {"version": "test", "prompts": {}},
                {
                    "version": "test",
                    "default_model_id": "default",
                    "models": {
                        "default": {
                            "provider": "default-model",
                            "platform": "openai_compatible",
                            "model_type": "default-model",
                            "api_url": "https://default.example.test/v1",
                            "api_key_env": "DEFAULT_MODEL_API_KEY",
                        },
                        "planner": {
                            "provider": "planner-model",
                            "platform": "openai_compatible",
                            "model_type": "planner-model",
                            "api_url": "https://planner.example.test/v1",
                            "api_key_env": "PLANNER_MODEL_API_KEY",
                        },
                    },
                },
            )
            engine = object.__new__(DynamicStreamingEngine)
            engine.config = config
            engine.prompt_renderer = None
            engine.agents = {}
            engine._init_model_factory()
            engine.model = engine._build_model()
            engine._build_agents()

            self.assertEqual(engine.model.model_type, "default-model")
            self.assertTrue(
                any(
                    instance.model.model_type == "planner-model"
                    for instance in DummyChatAgent.instances
                )
            )
        finally:
            if previous_default is None:
                os.environ.pop("DEFAULT_MODEL_API_KEY", None)
            else:
                os.environ["DEFAULT_MODEL_API_KEY"] = previous_default
            if previous_planner is None:
                os.environ.pop("PLANNER_MODEL_API_KEY", None)
            else:
                os.environ["PLANNER_MODEL_API_KEY"] = previous_planner

    def test_unknown_agent_model_id_fails_config_normalization(self):
        with self.assertRaisesRegex(ValueError, "unknown model_id"):
            normalize_new_config(
                {
                    "version": "test",
                    "core_team": [
                        {
                            "id": "root_coordinator",
                            "role": "Root Coordinator",
                            "model_id": "missing",
                        }
                    ],
                },
                {},
                {"version": "test", "prompts": {}},
                {
                    "version": "test",
                    "default_model_id": "default",
                    "models": {
                        "default": {
                            "provider": "default-model",
                            "platform": "openai_compatible",
                            "model_type": "default-model",
                            "api_url": "https://default.example.test/v1",
                        }
                    },
                },
            )

    def test_backend_source_does_not_reintroduce_old_model_fallbacks(self):
        banned = ("openrouter/owl-alpha", "https://openrouter.ai/api/v1")
        violations = []
        for path in Path("backend").rglob("*.py"):
            if ".python_deps" in path.parts or ".sqlalchemy_deps" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for value in banned:
                if value in text:
                    violations.append(f"{path}:{value}")

        self.assertEqual([], violations)


class TavilyResearchContractTests(unittest.TestCase):
    def test_research_prompts_use_tavily_not_ui_navigation(self):
        config = load_engine_config(Path("backend"))
        prompts = config["prompts_config"]["prompts"]

        self.assertFalse(
            any(key.startswith("research.") and "discipline" in key for key in prompts)
        )
        self.assertIn("Tavily Search", prompts["research.initial_task"]["template"])
        self.assertIn("Tavily Extract", prompts["research.initial_task"]["template"])
        self.assertNotIn("steps", prompts["research.initial_task"]["template"])

    def test_research_config_exposes_tavily_basic_defaults(self):
        config = load_engine_config(Path("backend"))
        tavily = config["research_config"]["tavily"]

        self.assertEqual(tavily["search_depth"], "basic")
        self.assertEqual(tavily["extract_depth"], "basic")
        self.assertGreaterEqual(tavily["max_search_queries"], 5)
        self.assertLessEqual(tavily["max_search_queries"], 8)
        self.assertGreaterEqual(tavily["max_sources_per_objective"], 1)
        self.assertLessEqual(tavily["max_sources_per_objective"], 3)
        self.assertGreaterEqual(tavily["max_total_sources"], 8)
        self.assertLessEqual(tavily["max_total_sources"], 12)

    def test_tavily_research_builds_structured_evidence_with_fake_client(self):
        class FakeTavilyClient:
            def search(self, query, **kwargs):
                self.search_kwargs = kwargs
                return {
                    "results": [
                        {
                            "title": "Official market source",
                            "url": "https://example.com/market",
                            "content": "Market demand and pricing evidence.",
                            "score": 0.9,
                        }
                    ]
                }

            def extract(self, urls, **kwargs):
                self.extract_kwargs = kwargs
                return {
                    "results": [
                        {
                            "url": "https://example.com/market",
                            "raw_content": "Detailed extracted source evidence for demand, pricing, and risk.",
                        }
                    ],
                    "failed_results": [],
                }

        client = FakeTavilyClient()
        research = TavilyResearch(
            {
                "max_search_queries": 1,
                "max_sources_per_objective": 1,
                "max_total_sources": 1,
            },
            client=client,
        )

        structured = research.build_structured_evidence(
            "smart pantry assistant",
            "Research pricing and market demand.",
            ["Product Manager", "Business Analyst"],
        )

        self.assertEqual(client.search_kwargs["search_depth"], "basic")
        self.assertEqual(client.extract_kwargs["extract_depth"], "basic")
        self.assertEqual(structured["research_quality"], "weak")
        self.assertEqual(structured["objectives"][0]["status"], "complete")
        self.assertIn("https://example.com/market", structured["sources"])

    def test_production_tavily_config_generates_multiple_queries(self):
        class FakeTavilyClient:
            def __init__(self):
                self.queries = []

            def search(self, query, **kwargs):
                self.queries.append(query)
                return {"results": []}

            def extract(self, urls, **kwargs):
                return {"results": [], "failed_results": []}

        config = load_engine_config(Path("backend"))
        client = FakeTavilyClient()
        research = TavilyResearch(config["research_config"]["tavily"], client=client)

        structured = research.build_structured_evidence(
            "online car parts store in Malaysia",
            "Research competitors, pricing, regulations, and risks.",
            ["Product Manager"],
        )

        self.assertGreater(len(client.queries), 1)
        self.assertEqual(len(client.queries), len(structured["search_queries"]))
        self.assertEqual(structured["sources"], [])
        self.assertTrue(structured["failed_sources"])
        self.assertIn("evidence is missing", structured["research_summary"].lower())

    def test_single_query_limit_requires_explicit_opt_in(self):
        class FakeTavilyClient:
            def __init__(self):
                self.queries = []

            def search(self, query, **kwargs):
                self.queries.append(query)
                return {"results": []}

            def extract(self, urls, **kwargs):
                return {"results": [], "failed_results": []}

        client = FakeTavilyClient()
        research = TavilyResearch({"max_search_queries": 1}, client=client)
        research.build_structured_evidence("online car parts store in Malaysia")

        self.assertGreater(len(client.queries), 1)

        opt_in_client = FakeTavilyClient()
        opt_in = TavilyResearch(
            {"max_search_queries": 1, "allow_single_search_query": True},
            client=opt_in_client,
        )
        opt_in.build_structured_evidence("online car parts store in Malaysia")

        self.assertEqual(len(opt_in_client.queries), 1)


class StructuredResearchTests(unittest.TestCase):
    def test_json_research_rejects_search_result_and_blank_sources(self):
        raw = json.dumps(
            {
                "research_summary": "Penang tuition demand needs source-backed validation.",
                "research_quality": "strong",
                "search_queries": ["online tuition centre Penang competitors"],
                "objectives": [
                    {
                        "name": "Competitors",
                        "status": "complete",
                        "evidence": [
                            {
                                "objective": "Competitors",
                                "claim": "Established operators list centres in Malaysia.",
                                "source_title": "Kumon Malaysia centre finder",
                                "source_url": "https://www.kumon.com.my/find-a-centre/",
                                "summary": "The official centre finder shows existing tuition/enrichment operators.",
                                "confidence": "medium",
                            }
                        ],
                    },
                    {
                        "name": "Pricing",
                        "status": "complete",
                        "evidence": [
                            {
                                "objective": "Pricing",
                                "claim": "Search result pages are not pricing evidence.",
                                "source_title": "Search result page",
                                "source_url": "https://www.bing.com/search?q=Penang+tuition",
                                "summary": "Search results page.",
                                "confidence": "low",
                            },
                            {
                                "objective": "Pricing",
                                "claim": "Blank pages are not evidence.",
                                "source_title": "Blank",
                                "source_url": "about:blank",
                                "summary": "<empty>",
                                "confidence": "low",
                            },
                        ],
                    },
                ],
                "missing_information": [],
                "recommended_next_searches": ["Penang tuition centre fees"],
                "failed_sources": [],
                "sources": [
                    "https://www.kumon.com.my/find-a-centre/",
                    "https://www.bing.com/search?q=Penang+tuition",
                ],
            }
        )

        structured = StructuredResearch.from_brief(
            task="online tuition centre in Penang",
            raw_brief=raw,
            findings=[],
        )

        statuses = {item["name"]: item["status"] for item in structured.objectives}
        self.assertEqual(statuses["Competitors"], "complete")
        self.assertEqual(statuses["Pricing"], "incomplete")
        self.assertIn("https://www.kumon.com.my/find-a-centre/", structured.sources)
        self.assertFalse(any("bing.com/search" in url for url in structured.sources))
        self.assertFalse(any("about:blank" in url for url in structured.sources))
        self.assertTrue(any("bing.com/search" in item for item in structured.failed_sources))
        self.assertTrue(any("about:blank" in item for item in structured.failed_sources))
        self.assertIn("Pricing: no valid source evidence collected.", structured.missing_information)
        self.assertEqual(structured.research_quality, "weak")

    def test_penang_tuition_sample_structures_core_objectives_with_sources(self):
        raw = json.dumps(
            {
                "research_summary": "Online tuition in Penang has demand, competitor, pricing, and regulatory questions with initial evidence.",
                "research_quality": "strong",
                "search_queries": [
                    "Penang online tuition centre competitors",
                    "Malaysia private education institution registration tuition centre",
                    "Penang tuition centre fees",
                ],
                "objectives": [
                    {
                        "name": "Demand",
                        "status": "complete",
                        "evidence": [
                            {
                                "objective": "Demand",
                                "claim": "Penang has a school-age population base relevant to tuition demand.",
                                "source_title": "Department of Statistics Malaysia",
                                "source_url": "https://www.dosm.gov.my/portal-main/release-content/current-population-estimates-malaysia-2024",
                                "summary": "Official demographic data can support demand sizing for local education services.",
                                "confidence": "medium",
                            }
                        ],
                    },
                    {
                        "name": "Competitors",
                        "status": "complete",
                        "evidence": [
                            {
                                "objective": "Competitors",
                                "claim": "Tuition and enrichment competitors operate through searchable centre networks.",
                                "source_title": "Kumon Malaysia centre finder",
                                "source_url": "https://www.kumon.com.my/find-a-centre/",
                                "summary": "Official centre listings help identify competitor presence and locations.",
                                "confidence": "medium",
                            }
                        ],
                    },
                    {
                        "name": "Pricing",
                        "status": "complete",
                        "evidence": [
                            {
                                "objective": "Pricing",
                                "claim": "Published tuition pages can be used to benchmark fees.",
                                "source_title": "A tuition provider fees page",
                                "source_url": "https://www.superprof.com.my/lessons/academic-tutoring/penang/",
                                "summary": "Provider listings can support initial pricing benchmarks, though confidence is lower than official pricing.",
                                "confidence": "low",
                            }
                        ],
                    },
                    {
                        "name": "Regulations",
                        "status": "complete",
                        "evidence": [
                            {
                                "objective": "Regulations",
                                "claim": "Private education operations should verify Ministry of Education registration requirements.",
                                "source_title": "Ministry of Education Malaysia",
                                "source_url": "https://www.moe.gov.my/en/faq/pendaftaran-institusi-pendidikan-swasta",
                                "summary": "Official education ministry guidance is the preferred source for registration constraints.",
                                "confidence": "high",
                            }
                        ],
                    },
                    {
                        "name": "Technical feasibility",
                        "status": "complete",
                        "evidence": [],
                    },
                ],
                "missing_information": [],
                "recommended_next_searches": ["Penang parent tuition pain points"],
                "failed_sources": [],
                "sources": [],
            }
        )

        structured = StructuredResearch.from_brief(
            task="online tuition centre in Penang",
            raw_brief=raw,
            findings=[],
        )

        objectives = {item["name"]: item for item in structured.objectives}
        for name in ("Demand", "Competitors", "Pricing", "Regulations"):
            self.assertEqual(objectives[name]["status"], "complete")
            self.assertTrue(objectives[name]["evidence"][0]["source_url"].startswith("https://"))

        self.assertEqual(objectives["Technical feasibility"]["status"], "incomplete")
        self.assertTrue(
            any("Technical feasibility" in item for item in structured.missing_information)
        )
        self.assertGreaterEqual(len(structured.sources), 4)
        self.assertIn("Penang parent tuition pain points", structured.recommended_next_searches)


class ResearchOrchestratorProjectionTests(unittest.IsolatedAsyncioTestCase):
    def make_engine(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.agents = {
            "Product Manager": object(),
            "Business Analyst": object(),
        }
        engine.current_task = "online car parts store in Malaysia"
        engine._compress_text = lambda text, max_chars=1800: str(text)[:max_chars]
        engine._error_text = lambda error, max_chars=600: str(error)[:max_chars]
        return engine

    def make_orchestrator(self, engine, tavily_research, fallback_policy=None):
        orchestrator = object.__new__(ResearchOrchestrator)
        orchestrator.engine = engine
        orchestrator.tavily_research = tavily_research
        orchestrator.fallback_policy = fallback_policy
        return orchestrator

    async def test_orchestrator_preserves_full_structured_tavily_fields(self):
        class FakeTavilyResearch:
            def build_structured_evidence(self, task, research_task, role_names):
                return {
                    "research_summary": "Structured Tavily evidence.",
                    "research_quality": "weak",
                    "search_queries": [
                        "online car parts store Malaysia competitors",
                        "online car parts store Malaysia pricing",
                    ],
                    "objectives": [
                        {
                            "name": "Competitors",
                            "status": "complete",
                            "evidence": [
                                {
                                    "objective": "Competitors",
                                    "claim": "Marketplace listings show competitors.",
                                    "source_title": "Example competitor",
                                    "source_url": "https://example.com/competitor",
                                    "summary": "A real source summary.",
                                    "confidence": "medium",
                                }
                            ],
                        }
                    ],
                    "missing_information": [],
                    "recommended_next_searches": [],
                    "failed_sources": ["https://example.com/blocked: blocked"],
                    "sources": ["https://example.com/competitor"],
                }

        engine = self.make_engine()
        orchestrator = self.make_orchestrator(engine, FakeTavilyResearch())

        result = await orchestrator._run_research(
            task="online car parts store in Malaysia",
            research_task="research task",
            timeout=10,
            fallback_prefix="Research Agent Tavily research",
        )

        self.assertFalse(result.fallback_used)
        self.assertIn("search_queries", result.artifact_payload["research_brief"])
        self.assertNotIn("[compressed", result.artifact_payload["research_brief"])
        self.assertEqual(
            result.artifact_payload["research"]["sources"],
            ["https://example.com/competitor"],
        )
        agent_briefs = engine._findings_to_agent_briefs(result.findings)
        self.assertIn("Search Queries:", agent_briefs["Product Manager"])
        self.assertIn("https://example.com/competitor", agent_briefs["Product Manager"])

    async def test_orchestrator_marks_no_source_tavily_result_as_missing_evidence(self):
        class FakeTavilyResearch:
            def build_structured_evidence(self, task, research_task, role_names):
                return {
                    "research_summary": "Tavily research evidence is missing.",
                    "research_quality": "weak",
                    "search_queries": ["online car parts store Malaysia competitors"],
                    "objectives": [
                        {
                            "name": "Competitors",
                            "status": "incomplete",
                            "evidence": [],
                        }
                    ],
                    "missing_information": ["Competitors: no valid Tavily evidence collected."],
                    "recommended_next_searches": [
                        "online car parts store Malaysia competitors"
                    ],
                    "failed_sources": [
                        "online car parts store Malaysia competitors: no Tavily results returned"
                    ],
                    "sources": [],
                }

        engine = self.make_engine()
        orchestrator = self.make_orchestrator(engine, FakeTavilyResearch())

        result = await orchestrator._run_research(
            task="online car parts store in Malaysia",
            research_task="research task",
            timeout=10,
            fallback_prefix="Research Agent Tavily research",
        )

        self.assertEqual(result.structured.status, "missing_evidence")
        self.assertFalse(result.fallback_used)
        self.assertEqual(result.structured.sources, [])
        self.assertTrue(
            any("Research evidence is missing" in item for item in result.structured.missing_information)
        )
        self.assertIn("Research Evidence Missing", result.findings[0]["content"])

    async def test_tavily_exception_sets_fallback_used(self):
        class RaisingTavilyResearch:
            def build_structured_evidence(self, task, research_task, role_names):
                raise RuntimeError("tavily-python is not installed in the backend runtime.")

        class FakeFallbackPolicy:
            def research_brief(self, task, reason, agents):
                return (
                    "Research Summary: Tavily research did not complete. "
                    f"Reason: {reason}\nSources: None."
                )

            def structured_result(self, task, reason, agents, findings, raw_brief):
                return StructuredResearch.from_brief(
                    task=task,
                    raw_brief=raw_brief,
                    findings=findings,
                    status="fallback",
                    fallback_reason=reason,
                )

        engine = self.make_engine()
        orchestrator = self.make_orchestrator(
            engine,
            RaisingTavilyResearch(),
            FakeFallbackPolicy(),
        )

        result = await orchestrator._run_research(
            task="online car parts store in Malaysia",
            research_task="research task",
            timeout=10,
            fallback_prefix="Research Agent Tavily research",
        )

        self.assertTrue(result.fallback_used)
        self.assertIn("tavily-python is not installed", result.fallback_reason)


class PlannerValidatorTests(unittest.TestCase):
    def make_engine(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.standby_agent_configs = {
            "legal_advisor": {
                "id": "legal_advisor",
                "role": "Legal Advisor",
                "allow_tools": False,
            },
            "regulatory_analyst": {
                "id": "regulatory_analyst",
                "role": "Regulatory Analyst",
                "allow_tools": False,
            },
            "vague_agent": {
                "id": "vague_agent",
                "role": "Specialist",
                "allow_tools": False,
            },
        }
        return engine

    def test_validator_accepts_known_unique_standby_specialists(self):
        engine = self.make_engine()

        selected = engine._validate_standby_selection(
            {
                "selected_specialists": [
                    {
                        "id": "legal_advisor",
                        "reason": "Contracts and liability matter.",
                    }
                ]
            }
        )

        self.assertEqual(
            selected,
            [
                {
                    "id": "legal_advisor",
                    "role": "Legal Advisor",
                    "reason": "Contracts and liability matter.",
                }
            ],
        )

    def test_validator_rejects_malformed_duplicates_vague_and_tools(self):
        engine = self.make_engine()

        self.assertEqual(engine._validate_standby_selection("not-json"), [])
        selected = engine._validate_standby_selection(
            {
                "selected_specialists": [
                    {"id": "legal_advisor"},
                    {"id": "legal_advisor"},
                    {"id": "unknown_agent"},
                    {"id": "vague_agent"},
                    {"id": "regulatory_analyst", "tools": ["tavily"]},
                ]
            }
        )

        self.assertEqual(
            selected,
            [
                {
                    "id": "legal_advisor",
                    "role": "Legal Advisor",
                    "reason": "Selected by Agent Planner.",
                }
            ],
        )


class DebateExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_debate_agents_run_as_live_sequential_chain(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.DEBATE_MODE = "sequential"
        engine.DEBATE_CONCURRENCY = 2
        engine.current_task = "Plan a clinic booking app"
        engine.active_debate_agent_roles = []
        engine._prior_debate_context_for_round = lambda round_num: []
        engine._compress_text = lambda text, max_chars=1800: str(text)[:max_chars]
        captured = []

        async def fake_run(agent, agent_name, message, prior_responses=None, debate_stage="proposal"):
            captured.append(
                {
                    "agent": agent_name,
                    "prior": [dict(item) for item in (prior_responses or [])],
                }
            )
            return {
                "type": "agent_response",
                "agent": agent_name,
                "content": f"{agent_name} done",
            }

        engine._run_debate_step = fake_run
        selected = [
            ("Product Manager", object()),
            ("Business Analyst", object()),
            ("Finance Analyst", object()),
            ("UX Researcher", object()),
            ("Technical Lead", object()),
        ]
        events = [
            event
            async for event in engine._run_debate_agents(
                selected,
                Message(agent="System", content="context"),
                "proposal",
                1,
            )
        ]

        final_events = [event for event in events if event["type"] == "agent_response"]
        self.assertEqual(len(final_events), 5)
        self.assertEqual(
            [event["agent"] for event in final_events],
            [
                "UX Researcher",
                "Finance Analyst",
                "Technical Lead",
                "Product Manager",
                "Business Analyst",
            ],
        )
        self.assertTrue(any(event["type"] == "agent_typing" for event in events))
        self.assertTrue(any(event["type"] == "agent_delta" for event in events))
        self.assertEqual(final_events[0]["type"], "agent_response")
        self.assertEqual(final_events[0]["round"], 1)
        self.assertEqual(captured[0]["prior"], [])
        self.assertEqual(captured[1]["prior"][-1]["agent"], "UX Researcher")
        self.assertEqual(captured[2]["prior"][-1]["agent"], "Finance Analyst")
        self.assertEqual(captured[3]["prior"][-1]["agent"], "Technical Lead")
        self.assertEqual(
            engine.active_debate_agent_roles,
            [
                "UX Researcher",
                "Finance Analyst",
                "Technical Lead",
                "Product Manager",
                "Business Analyst",
            ],
        )

    async def test_debate_step_receives_previous_speaker_and_last_six_messages(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.current_task = "Plan a clinic booking app"
        engine.memory_store = FakeMemoryStore()
        engine._compress_text = lambda text, max_chars=1800: str(text)[:max_chars]
        engine._error_text = lambda error, max_chars=600: str(error)[:max_chars]
        captured = {}

        class FakeRenderer:
            def render(self, prompt_id, **values):
                if prompt_id == "debate.step":
                    captured.update(values)
                    return "rendered debate prompt"
                if prompt_id == "debate.stage.proposal":
                    return "stage instruction"
                return ""

        class FakeAgent:
            def reset(self):
                pass

            async def astep(self, prompt):
                return types.SimpleNamespace(
                    msgs=[types.SimpleNamespace(content="Finance agrees with UX.")]
                )

        engine.prompt_renderer = FakeRenderer()
        prior_responses = [
            {"agent": f"Agent {idx}", "content": f"message {idx}"}
            for idx in range(8)
        ]

        event = await engine._run_debate_step(
            FakeAgent(),
            "Finance Analyst",
            Message(agent="System", content="research context"),
            prior_responses=prior_responses,
            debate_stage="proposal",
        )

        self.assertEqual(event["type"], "agent_response")
        self.assertEqual(captured["previous_speaker_name"], "Agent 7")
        self.assertEqual(captured["previous_speaker_message"], "message 7")
        recent_lines = captured["recent_conversation"].splitlines()
        self.assertEqual(len(recent_lines), 6)
        self.assertEqual(recent_lines[0], "[Agent 2]: message 2")
        self.assertEqual(recent_lines[-1], "[Agent 7]: message 7")

    async def test_summarizer_emits_structured_business_report_event(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.PRODUCT_MANAGER_ROLE = "Product Manager"
        engine.current_task = "Build a clinic booking app"
        engine.memory_store = FakeMemoryStore()
        engine.debate_round_history = []
        class FakeRenderer:
            def render(self, prompt_id, **values):
                return ""

        class FakeAgent:
            def reset(self):
                pass

            async def astep(self, prompt):
                return types.SimpleNamespace(
                    msgs=[
                        types.SimpleNamespace(
                            content="# Executive Summary\nProceed with a narrow MVP."
                        )
                    ]
                )

        engine.prompt_renderer = FakeRenderer()
        engine.agents = {
            "Report Generator": FakeAgent(),
            "Product Manager": object(),
        }

        events = [event async for event in engine._summarize()]
        content = events[0]["content"]

        self.assertEqual(events[0]["type"], "summarizer")
        self.assertEqual(events[0]["agent"], "Blueprint Synthesizer")
        for heading in (
            "Executive Summary",
            "Problem Statement",
            "Market Analysis",
            "Market Validation",
            "Product & MVP",
            "Technical Architecture",
            "Financial Plan",
            "Marketing Strategy",
            "Legal & Compliance",
            "Risk Assessment",
            "Implementation Roadmap",
            "Final Recommendation",
        ):
            self.assertIn(f"# {heading}", content)
        self.assertIn("Launch Confidence:", content)
        self.assertNotIn("[Product Manager]:", content)

    def test_final_report_normalization_rejects_raw_chat_logs(self):
        engine = object.__new__(DynamicStreamingEngine)

        report = engine._normalize_final_report(
            "[Product Manager]: We should validate pricing.\n"
            "[Technical Lead]: Keep the build small.",
            [
                Message(agent="Product Manager", content="Validate pricing."),
                Message(agent="Technical Lead", content="Keep scope small."),
            ],
        )

        self.assertNotIn("[Product Manager]:", report)
        self.assertNotIn("[Technical Lead]:", report)
        for heading in engine.FINAL_REPORT_SECTIONS:
            self.assertIn(f"# {heading}", report)

    def test_missing_report_sections_are_handled_gracefully(self):
        engine = object.__new__(DynamicStreamingEngine)

        report = engine._normalize_final_report(
            "# Executive Summary\nSource-backed demand exists."
        )

        self.assertIn("# Financial Analysis", report)
        self.assertIn("# Agent Debate Summary", report)
        self.assertIn("## Key Agreements", report)
        self.assertIn("## Phase 1: MVP", report)
        self.assertIn("Insufficient information from the discussion.", report)

    def test_public_research_summary_is_compact_and_keeps_sources(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.current_task = "Build a clinic booking app"
        engine.research_findings = []

        summary = engine.build_public_research_summary(self._sample_research_payload())

        self.assertLess(len(summary), 3000)
        self.assertIn("Research quality: moderate", summary)
        self.assertIn("https://example.com/finance", summary)
        self.assertNotIn('"objectives"', summary)

    def test_research_complete_event_does_not_stream_raw_json(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.current_task = "Build a clinic booking app"
        engine.research_findings = []
        engine.research_artifact_path = "/tmp/research_brief.json"
        engine.agent_briefs_artifact_path = "/tmp/agent_briefs.json"
        payload = self._sample_research_payload()
        raw = json.dumps(payload)
        structured = StructuredResearch.from_brief("Build app", raw, [])
        result = ResearchRunResult(
            brief=raw,
            findings=[],
            structured=structured,
            artifact_payload={"task": "Build app", "research_brief": raw, "research": structured.to_dict()},
        )

        event = engine._research_complete_event(result)

        self.assertEqual(event["type"], "research_complete")
        self.assertLess(len(event["content"]), 3000)
        self.assertIn("https://example.com/finance", event["content"])
        self.assertNotIn('"objectives"', event["content"])
        self.assertNotIn("research", event)
        self.assertEqual(event["artifact_path"], "/tmp/research_brief.json")

    def test_report_context_includes_full_research_all_agents_and_all_rounds(self):
        engine = self._report_context_engine()

        context = engine._build_report_context()

        self.assertIn("Full raw Tavily evidence", context["research_brief"]["research_summary"])
        agents = {item["agent"] for item in context["all_agent_messages"]}
        for expected in (
            "Product Manager",
            "Research Agent",
            "Finance Analyst",
            "Technical Lead",
            "Marketing Strategist",
            "MVP Scope Guard",
        ):
            self.assertIn(expected, agents)
        self.assertEqual(
            [item["round"] for item in context["debate_rounds"]],
            [1, 2, 3],
        )

    def test_report_normalization_uses_context_when_sections_claim_insufficient(self):
        engine = self._report_context_engine()
        context = engine._build_report_context()
        report = engine._normalize_final_report(
            "# Executive Summary\nProceed.\n\n"
            "# Financial Analysis\nInsufficient information from the discussion.\n\n"
            "# Marketing Strategy\nInsufficient information from the discussion.",
            report_context=context,
        )

        financial = engine._section_body(report, "Financial Analysis")
        marketing = engine._section_body(report, "Marketing Strategy")
        self.assertNotEqual(financial, engine.REPORT_MISSING_TEXT)
        self.assertNotEqual(marketing, engine.REPORT_MISSING_TEXT)
        self.assertIn("Finance Analyst", financial)
        self.assertIn("Marketing Strategist", marketing)

    def test_debate_research_context_is_compressed_not_raw_json(self):
        engine = self._report_context_engine()

        context = engine._research_evidence_context(engine.research_findings)
        role_brief = engine.build_agent_research_brief(
            engine.research_artifact_payload,
            "Finance Analyst",
        )

        self.assertLess(len(context), 6000)
        self.assertIn("Compressed Tavily research evidence summary", context)
        self.assertIn("https://example.com/finance", context)
        self.assertNotIn('"objectives"', context)
        self.assertNotIn("RAW_FULL_JSON_MARKER", context)
        self.assertLess(len(role_brief), 2000)
        self.assertIn("Finance Analyst", role_brief)

    def test_research_artifacts_preserve_full_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = object.__new__(DynamicStreamingEngine)
            engine.run_artifact_dir = Path(tmp)
            payload = {
                "task": "Build app",
                "research_brief": json.dumps(self._sample_research_payload()),
            }
            research_path = Path(engine._write_json_artifact("research_brief.json", payload))
            briefs_path = Path(
                engine._write_json_artifact(
                    "agent_briefs.json",
                    {"agent_briefs": {"Finance Analyst": "Finance evidence"}},
                )
            )

            self.assertTrue(research_path.exists())
            self.assertTrue(briefs_path.exists())
            saved = json.loads(research_path.read_text(encoding="utf-8"))
            self.assertIn("research_brief", saved)
            self.assertIn("Full raw Tavily evidence", saved["research_brief"])

    def _sample_research_payload(self):
        return {
            "research_summary": "Full raw Tavily evidence with RAW_FULL_JSON_MARKER",
            "research_quality": "moderate",
            "search_queries": ["clinic booking market"],
            "objectives": [
                {
                    "name": "Financial model",
                    "status": "complete",
                    "evidence": [
                        {
                            "objective": "Financial model",
                            "claim": "Clinics need clear subscription pricing.",
                            "source_title": "Finance source",
                            "source_url": "https://example.com/finance",
                            "summary": "Pricing evidence for finance analysis.",
                            "confidence": "medium",
                        }
                    ],
                },
                {
                    "name": "Marketing channels",
                    "status": "complete",
                    "evidence": [
                        {
                            "objective": "Marketing channels",
                            "claim": "Local search is a useful acquisition channel.",
                            "source_title": "Marketing source",
                            "source_url": "https://example.com/marketing",
                            "summary": "Channel evidence for marketing strategy.",
                            "confidence": "medium",
                        }
                    ],
                },
                {"name": "Regulatory risk", "status": "incomplete", "evidence": []},
            ],
            "missing_information": ["Regulatory risk needs validation."],
            "recommended_next_searches": [],
            "failed_sources": [],
            "sources": ["https://example.com/finance", "https://example.com/marketing"],
        }

    def _report_context_engine(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.current_task = "Build a clinic booking app"
        engine.root_coordination_plan = "Root Coordinator plan"
        engine.pm_research_plan = "Product Manager research plan"
        engine.PRODUCT_MANAGER_ROLE = "Product Manager"
        engine.COORDINATOR_ROLE = "Root Coordinator"
        engine.config = {
            "core_team": [
                {"id": "product_manager", "role": "Product Manager"},
                {"id": "technical_lead", "role": "Technical Lead"},
                {"id": "business_analyst", "role": "Business Analyst"},
                {"id": "finance_analyst", "role": "Finance Analyst"},
                {"id": "ux_researcher", "role": "UX Researcher"},
                {"id": "marketing_strategist", "role": "Marketing Strategist"},
                {"id": "risk_compliance", "role": "Risk & Compliance"},
                {"id": "mvp_scope_guard", "role": "MVP Scope Guard"},
            ]
        }
        engine.agents = {item["role"]: object() for item in engine.config["core_team"]}
        engine.research_findings = [
            {"agent": "Finance Analyst", "content": "Finance Analyst: subscription pricing and cost assumptions exist."},
            {"agent": "Technical Lead", "content": "Technical Lead: use a simple booking workflow first."},
            {"agent": "Marketing Strategist", "content": "Marketing Strategist: acquire clinics through local search and partnerships."},
        ]
        raw = json.dumps(self._sample_research_payload())
        structured = StructuredResearch.from_brief(engine.current_task, raw, engine.research_findings)
        engine.research_artifact_payload = {
            "task": engine.current_task,
            "research_brief": raw,
            "research": structured.to_dict(),
        }
        engine.structured_research = structured.to_dict()
        engine.research_brief = raw
        engine.selected_standby_specialists = [{"id": "legal_advisor", "role": "Legal Advisor"}]
        engine.debate_round_history = [
            {
                "round": 1,
                "stage": "parallel",
                "responses": [
                    {"agent": "Product Manager", "content": "Problem and MVP scope are clear."},
                    {"agent": "Finance Analyst", "content": "Financial model should use subscription pricing."},
                    {"agent": "Technical Lead", "content": "Architecture can start with scheduling and notifications."},
                ],
                "consensus": "Round 1 consensus",
            },
            {
                "round": 2,
                "stage": "parallel",
                "responses": [
                    {"agent": "Marketing Strategist", "content": "Marketing Strategy should focus on local search."},
                    {"agent": "MVP Scope Guard", "content": "Keep the MVP narrow."},
                ],
                "consensus": "Round 2 consensus",
            },
            {
                "round": 3,
                "stage": "parallel",
                "responses": [
                    {"agent": "MVP Scope Guard", "content": "Final recommendation: go with a narrow MVP."},
                ],
                "consensus": "Round 3 consensus",
            },
        ]
        return engine


class FakeMemoryStore:
    def clear_agent_memories(self):
        pass

    def add_message(self, message):
        pass

    def add_agent_memory(self, agent_name, label, content):
        pass

    def get_agent_context(self, agent_name, limit=8):
        return ""

    def retrieve_relevant(self, query, limit=5):
        return [
            Message(agent="Product Manager", content="Validate pricing first."),
            Message(agent="Technical Lead", content="Keep the MVP small."),
        ][:limit]


class FakeResearchOrchestrator:
    def __init__(self, engine):
        self.engine = engine

    async def run_targeted(self, session, task, impact):
        prompt = " ".join([task, *impact.research_questions])
        self.engine.targeted_research_prompt = prompt
        brief = json.dumps(
            {
                "research_summary": "Tavily dry-run evidence",
                "research_quality": "weak",
                "search_queries": impact.research_questions or [task],
                "objectives": [
                    {
                        "name": "Targeted refinement",
                        "status": "complete",
                        "evidence": [
                            {
                                "objective": "Targeted refinement",
                                "claim": "Example source supports the refinement.",
                                "source_title": "Example",
                                "source_url": "https://example.com",
                                "summary": "Dry-run source evidence for project flow tests.",
                                "confidence": "medium",
                            }
                        ],
                    }
                ],
                "missing_information": [],
                "recommended_next_searches": [],
                "failed_sources": [],
                "sources": ["https://example.com"],
            }
        )
        findings = [{"agent": "Business Analyst", "content": "Localization pricing evidence"}]
        structured = StructuredResearch.from_brief(task, brief, findings)
        return ResearchRunResult(
            brief=brief,
            findings=findings,
            structured=structured,
            artifact_payload={
                "task": task,
                "research_brief": brief,
                "research": structured.to_dict(),
                "research_questions": impact.research_questions,
            },
        )


class StubProjectEngine(DynamicStreamingEngine):
    def __init__(self, store):
        self.session_store = store
        self.run_artifact_dir = store.base_dir
        self.current_session = None
        self.current_task = ""
        self.pm_research_plan = ""
        self.research_brief = ""
        self.research_findings = []
        self.debate_round_history = []
        self.memory_store = FakeMemoryStore()
        self.COORDINATOR_ROLE = "Product Manager"
        self.agents = {
            "Product Manager": object(),
            "Technical Lead": object(),
            "Business Analyst": object(),
            "UX Researcher": object(),
            "MVP Agent": object(),
        }
        self.research_agent = object()
        self._closed = False
        self.impact = ImpactAssessment(
            affected_sections=["business_plan"],
            agents_needed=["Business Analyst", "Product Manager"],
            need_research=False,
            research_questions=[],
            rationale="Business-only refinement",
        )
        self.targeted_research_prompt = ""

    async def aclose(self):
        self._closed = True

    async def _run_stream_impl(self, task, max_rounds):
        self.current_task = task
        self.pm_research_plan = "Problem: pantry waste"
        self.research_brief = "Shared Evidence: food waste evidence"
        self.research_findings = [
            {"agent": "Business Analyst", "content": "Pricing evidence"}
        ]
        self.debate_round_history = [
            {
                "round": 1,
                "stage": "proposal",
                "responses": [
                    {
                        "agent": "Business Analyst",
                        "content": "Use a freemium plan",
                    }
                ],
            }
        ]
        yield {"type": "research_complete", "content": self.research_brief}
        yield {
            "type": "summarizer",
            "content": (
                "# Business Model\nFreemium packaging with paid household automation.\n\n"
                "# MVP Definition\n## Phase 1: MVP\nFirst testable release tracks pantry items and expiry reminders.\n\n"
                "# Risk Assessment\nRisk review should validate food-safety claims before launch."
            ),
        }

    async def _run_product_manager_impact_assessment(self, session, request):
        return self.impact

    def _research_orchestrator(self):
        return FakeResearchOrchestrator(self)

    async def _run_refinement_debate(self, session, request, impact, findings):
        yield {
            "type": "agent_response",
            "agent": "Business Analyst",
            "content": "Update pricing for the refinement",
        }
        yield {
            "type": "agent_response",
            "agent": "Product Manager",
            "content": "Consensus: update only affected sections",
        }


class ProjectEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_run_creates_session_and_all_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            engine = StubProjectEngine(store)

            events = [
                event
                async for event in engine.run_project_stream(
                    "Build a smart pantry assistant",
                    max_rounds=1,
                )
            ]

            created = next(event for event in events if event["type"] == "session_created")
            session = store.load(created["chat_id"])

            self.assertEqual(set(CANONICAL_SECTIONS), set(session.sections.keys()))
            self.assertTrue(session.change_history)
            self.assertEqual(
                session.change_history[-1]["sections_changed"],
                list(CANONICAL_SECTIONS),
            )

    async def test_final_report_headings_populate_matching_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            engine = StubProjectEngine(store)

            events = [
                event
                async for event in engine.run_project_stream(
                    "Build a smart pantry assistant",
                    max_rounds=1,
                )
            ]

            created = next(event for event in events if event["type"] == "session_created")
            session = store.load(created["chat_id"])

            self.assertIn("Freemium packaging", session.sections["market_analysis"]["content"])
            self.assertIn("Risk review", session.sections["risk_assessment"]["content"])
            self.assertIn("First testable release", session.sections["product_mvp"]["content"])

    async def test_empty_section_update_preserves_previous_content(self):
        engine = StubProjectEngine(SessionStore(Path(tempfile.gettempdir())))

        merged = engine._merge_section_update(
            {"status": "draft", "source": "initial_run", "content": "Keep this plan"},
            {"status": "updated", "source": "refinement", "content": ""},
        )

        self.assertEqual(merged["content"], "Keep this plan")

    async def test_refinement_runs_research_and_updates_only_affected_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create("Build a smart pantry assistant")
            session.agent_briefs = {"Business Analyst": "Prior pricing evidence"}
            session.sections["business_plan"] = {"content": "Old business plan"}
            session.sections["technical_architecture"] = {"content": "Keep this"}
            store.save(session)

            engine = StubProjectEngine(store)
            events = [
                event
                async for event in engine.run_project_stream(
                    "Refine the business plan",
                    chat_id=session.chat_id,
                )
            ]
            loaded = store.load(session.chat_id)

            self.assertTrue(any(event["type"] == "research_complete" for event in events))
            self.assertIn("Refine the business plan", engine.targeted_research_prompt)
            self.assertEqual(
                loaded.sections["technical_architecture"]["content"],
                "Keep this",
            )
            self.assertEqual(
                loaded.change_history[-1]["sections_changed"],
                ["market_analysis"],
            )
            self.assertTrue(loaded.change_history[-1]["research_used"])
            self.assertIn("Research Agent", loaded.change_history[-1]["agents_used"])

    async def test_refinement_runs_targeted_research_when_needed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create("Build a smart pantry assistant")
            store.save(session)

            engine = StubProjectEngine(store)
            engine.impact = ImpactAssessment(
                affected_sections=["business_plan", "go_to_market"],
                agents_needed=["Business Analyst", "Product Manager"],
                need_research=True,
                research_questions=["Japanese food waste market"],
                rationale="New market",
            )

            events = [
                event
                async for event in engine.run_project_stream(
                    "Can this work in Japan?",
                    chat_id=session.chat_id,
                )
            ]
            loaded = store.load(session.chat_id)

            self.assertIn("Japanese food waste market", engine.targeted_research_prompt)
            self.assertTrue(any(event["type"] == "research_complete" for event in events))
            self.assertTrue(loaded.change_history[-1]["research_used"])
            self.assertEqual(
                loaded.change_history[-1]["sections_changed"],
                ["market_analysis", "marketing_strategy"],
            )


if __name__ == "__main__":
    unittest.main()
