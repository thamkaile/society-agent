# engine.py
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List

try:
    from backend.runtime_bootstrap import bootstrap_runtime
except ImportError:
    from runtime_bootstrap import bootstrap_runtime

bootstrap_runtime()

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from ..agents import AgentFactoryMixin
from ..config import ConfigLoader
from ..memory.memory_store import MemoryStore
from ..models.models import CANONICAL_SECTIONS, ChatSession, ImpactAssessment, Message
from ..parallel_debate_engine import ParallelDebateEngine
from ..session_store import SessionStore
from ..storage.session_projector import SessionProjectorMixin
from .debate import DebateMixin
from .fallback import FallbackPolicy
from .prompt_renderer import PromptRenderer
from .research import ResearchMixin
from .research_flow import ResearchOrchestrator, ResearchRunResult
from .router import Router


logger = logging.getLogger(__name__)


class DynamicStreamingEngine(
    AgentFactoryMixin,
    ResearchMixin,
    DebateMixin,
    SessionProjectorMixin,
):
    DEFAULT_DEBATE_ROUNDS = 3
    MIN_DEBATE_ROUNDS = 2
    DEBATE_CONCURRENCY = max(1, int(os.getenv("DYNAMIC_ENGINE_DEBATE_CONCURRENCY", "2")))
    DEBATE_MODE = os.getenv(
        "DEBATE_ENGINE_MODE",
        os.getenv("DYNAMIC_ENGINE_DEBATE_MODE", "parallel"),
    ).lower()
    RESEARCH_EVERY_ROUND = os.getenv("DYNAMIC_ENGINE_RESEARCH_EVERY_ROUND", "0") == "1"
    RESEARCH_ON_EVERY_REFINEMENT = (
        os.getenv("DYNAMIC_ENGINE_RESEARCH_ON_EVERY_REFINEMENT", "1") == "1"
    )
    DEFAULT_CONFLICT_ROLES = ("Technical Lead", "Business Analyst", "MVP Scope Guard")

    def __init__(self, config: dict):
        self.config = ConfigLoader().normalize(config)
        self.prompt_renderer = PromptRenderer(self.config.get("prompts_config", {}))
        self.research_config = self.config.get("research_config", {})
        self.fallback_policy = FallbackPolicy(self.prompt_renderer, self.research_config)

        research_timeouts = self.research_config.get("timeouts", {})
        self.PM_RESEARCH_PLAN_TIMEOUT = max(
            10,
            int(
                os.getenv(
                    "DYNAMIC_ENGINE_PM_RESEARCH_PLAN_TIMEOUT",
                    str(research_timeouts.get("pm_plan_seconds", 120)),
                )
            ),
        )
        self.ROOT_COORDINATOR_TIMEOUT = max(
            5,
            int(
                os.getenv(
                    "DYNAMIC_ENGINE_ROOT_COORDINATOR_TIMEOUT",
                    str(research_timeouts.get("root_coordinator_seconds", 25)),
                )
            ),
        )
        self.COORDINATOR_ROLE = self.config.get("coordinator_role", "Root Coordinator")
        self.PRODUCT_MANAGER_ROLE = self.config.get(
            "product_manager_role",
            "Product Manager",
        )
        self.RESEARCH_AGENT_ID = self.config.get("research_agent", {}).get(
            "id",
            "research_agent",
        )

        self._init_model_factory()
        self.model = self._build_model()
        self.research_agent = None
        self.current_task = ""
        self.root_coordination_plan = ""
        self.pm_research_plan = ""
        self.research_brief = ""
        self.research_artifact_payload: Dict[str, Any] = {}
        self.research_artifact_path = ""
        self.agent_briefs_artifact_path = ""
        self.structured_research: Dict[str, Any] = {}
        self.research_findings: List[Dict] = []
        self.debate_round_history: List[Dict] = []
        self.generated_blueprint_sections: Dict[str, Dict] = {}
        self.selected_standby_specialists: List[Dict[str, str]] = []
        self.active_debate_agent_roles: List[str] = []
        self.run_artifact_dir = Path(__file__).resolve().parents[1] / "run_artifacts"
        self.session_store = SessionStore()
        self.current_session: ChatSession | None = None
        self._closed = False

        self.agents: Dict[str, object] = {}
        self._build_agents()
        self._setup_research_agent()

        self.memory_store = MemoryStore()
        self.router = Router(list(self.agents.keys()))
        self.research_orchestrator = ResearchOrchestrator(self)
        self.parallel_debate_engine = ParallelDebateEngine(self)
        self._log_legacy_config_ignored()

    async def aclose(self):
        """Mark the engine closed before the event loop shuts down."""
        if self._closed:
            return

        self._closed = True

    async def run_stream(
        self,
        task: str,
        max_rounds: int = DEFAULT_DEBATE_ROUNDS,
    ) -> AsyncGenerator[Dict, None]:
        try:
            async for event in self._run_stream_impl(task, max_rounds):
                yield event
        finally:
            await self.aclose()

    async def run_project_stream(
        self,
        task: str,
        chat_id: str | None = None,
        browser_session_id: str = "",
        max_rounds: int = DEFAULT_DEBATE_ROUNDS,
    ) -> AsyncGenerator[Dict, None]:
        try:
            async for event in self._run_project_stream_impl(
                task,
                chat_id,
                browser_session_id,
                max_rounds,
            ):
                yield event
        finally:
            await self.aclose()

    async def _run_project_stream_impl(
        self,
        task: str,
        chat_id: str | None,
        browser_session_id: str,
        max_rounds: int,
    ) -> AsyncGenerator[Dict, None]:
        if chat_id:
            async for event in self._run_refinement_stream(
                task,
                chat_id,
                browser_session_id,
            ):
                yield event
            return

        session = self.session_store.create(
            task,
            browser_session_id=browser_session_id,
        )
        self.current_session = session
        self.run_artifact_dir = self.session_store.session_dir(session.chat_id)
        yield {
            "type": "session_created",
            "chat_id": session.chat_id,
            "content": f"Created project session {session.chat_id}",
            "path": str(self.run_artifact_dir / "session.json"),
        }

        fresh_max_rounds = max(
            int(max_rounds or self.DEFAULT_DEBATE_ROUNDS),
            self.MIN_DEBATE_ROUNDS,
        )
        summary_text = ""
        async for event in self._run_stream_impl(task, fresh_max_rounds):
            if event.get("type") == "summarizer":
                summary_text = event.get("content", "")
            yield event

        session.research_brief = {
            "task": task,
            "pm_research_plan": self.pm_research_plan,
            "research_brief": self.research_brief,
            "research": getattr(self, "structured_research", {}),
        }
        session.agent_briefs = self._findings_to_agent_briefs(self.research_findings)
        new_sections = self._build_initial_sections(task, summary_text)
        for section, after in new_sections.items():
            before = session.sections.get(section, {})
            after = self._merge_section_update(before, after)
            session.sections[section] = after
            yield {
                "type": "section_updated",
                "section": section,
                "before": before,
                "after": after,
                "content": f"Updated section {section}",
            }

        session.decision_log.append(
            {
                "timestamp": time.time(),
                "request": task,
                "type": "initial_decision",
                "summary": summary_text,
                "debate_rounds": self.debate_round_history,
            }
        )
        session.change_history.append(
            {
                "timestamp": time.time(),
                "request": task,
                "agents_used": self._agents_used_for_initial_run(),
                "research_used": bool(self.research_brief),
                "sections_changed": list(CANONICAL_SECTIONS),
            }
        )
        path = self.session_store.save(session)
        yield {
            "type": "session_saved",
            "chat_id": session.chat_id,
            "path": str(path),
            "content": f"Saved project session {session.chat_id}",
        }

    async def _run_refinement_stream(
        self,
        task: str,
        chat_id: str,
        browser_session_id: str = "",
    ) -> AsyncGenerator[Dict, None]:
        session = self.session_store.load(
            chat_id,
            browser_session_id=browser_session_id,
        )
        self.current_session = session
        self.current_task = task
        self.run_artifact_dir = self.session_store.session_dir(session.chat_id)
        self.research_artifact_payload = (
            dict(session.research_brief)
            if isinstance(session.research_brief, dict)
            else {}
        )
        self.research_artifact_path = ""
        self.agent_briefs_artifact_path = ""
        if isinstance(session.research_brief, dict):
            self.structured_research = session.research_brief.get("research", {}) or {}
            self.research_brief = session.research_brief.get("research_brief", "")
        else:
            self.structured_research = {}
            self.research_brief = str(session.research_brief or "")
        self.debate_round_history = []
        self.generated_blueprint_sections = {}
        self.selected_standby_specialists = []
        self.active_debate_agent_roles = []
        self.memory_store.clear_agent_memories()
        self.memory_store.add_message(Message(agent="User", content=session.user_idea))
        self.memory_store.add_message(Message(agent="User", content=task))
        self._hydrate_session_memory(session)

        yield {
            "type": "session_loaded",
            "chat_id": session.chat_id,
            "content": f"Loaded project session {session.chat_id}",
            "path": str(self.run_artifact_dir / "session.json"),
        }

        impact = await self._run_product_manager_impact_assessment(session, task)
        if self.RESEARCH_ON_EVERY_REFINEMENT and not impact.need_research:
            impact.need_research = True
            impact.research_questions = impact.research_questions or [task]
            note = (
                "Research Agent runs on every refinement by default to verify "
                "whether the requested change needs fresh evidence."
            )
            impact.rationale = f"{impact.rationale} {note}".strip() if impact.rationale else note
        yield {
            "type": "impact_assessment",
            "agent": self.COORDINATOR_ROLE,
            "content": impact.to_dict(),
        }

        findings = self._findings_from_session(session, impact.agents_needed)
        research_used = False
        if impact.need_research:
            yield {
                "type": "phase",
                "phase": "research",
                "round": 1,
                "content": "Targeted Research Phase",
            }
            result = await self._research_orchestrator().run_targeted(session, task, impact)
            self._apply_research_result(result)
            findings = result.findings
            session.research_brief = result.artifact_payload
            session.agent_briefs.update(self._findings_to_agent_briefs(findings))
            research_used = True
            if result.fallback_used:
                yield self._research_warning_event(
                    result,
                    "Targeted research failed; continuing with a fallback evidence brief",
                )
            artifact = self._write_json_artifact(
                f"research_update_{len(session.change_history) + 1}.json",
                session.research_brief,
            )
            self.research_artifact_path = artifact
            yield {
                "type": "artifact",
                "content": f"Targeted research update written to {artifact}",
            }
            yield self._research_complete_event(result)
        else:
            yield {
                "type": "research_skipped",
                "content": "Impact assessment did not require new research; reusing prior session evidence.",
            }

        debate_responses = []
        async for event in self._run_refinement_debate(session, task, impact, findings):
            if event.get("type") == "agent_response":
                debate_responses.append(
                    {
                        "agent": event.get("agent", "Agent"),
                        "content": event.get("content", ""),
                    }
                )
            yield event

        summary_text = self._compress_text(
            " ".join(f"{item['agent']}: {item['content']}" for item in debate_responses),
            3000,
        )
        affected_blueprint_sections = [
            section
            for section in self._normalize_sections(impact.affected_sections)
            if section in CANONICAL_SECTIONS
        ]
        if affected_blueprint_sections:
            self.generated_blueprint_sections = await self._generate_blueprint_sections(
                section_keys=affected_blueprint_sections,
            )
        changed_sections = []
        updates = self._build_refinement_section_updates(session, task, impact, summary_text)
        for section, after in updates.items():
            before = session.sections.get(section, {})
            after = self._merge_section_update(before, after)
            session.sections[section] = after
            changed_sections.append(section)
            yield {
                "type": "section_updated",
                "section": section,
                "before": before,
                "after": after,
                "content": f"Updated section {section}",
            }

        session.decision_log.append(
            {
                "timestamp": time.time(),
                "request": task,
                "type": "refinement_decision",
                "impact_assessment": impact.to_dict(),
                "summary": summary_text,
                "debate_rounds": self.debate_round_history,
            }
        )
        session.change_history.append(
            {
                "timestamp": time.time(),
                "request": task,
                "agents_used": self._agents_used_for_refinement(impact),
                "research_used": research_used,
                "sections_changed": changed_sections,
            }
        )
        path = self.session_store.save(session)
        yield {
            "type": "session_saved",
            "chat_id": session.chat_id,
            "path": str(path),
            "content": f"Saved project session {session.chat_id}",
        }

    async def _run_stream_impl(
        self,
        task: str,
        max_rounds: int,
    ) -> AsyncGenerator[Dict, None]:
        user_msg = Message(agent="User", content=task)
        self.current_task = task
        self.root_coordination_plan = ""
        self.pm_research_plan = ""
        self.research_brief = ""
        self.research_artifact_payload = {}
        self.research_artifact_path = ""
        self.agent_briefs_artifact_path = ""
        self.structured_research = {}
        self.research_findings = []
        self.debate_round_history = []
        self.generated_blueprint_sections = {}
        self.memory_store.clear_agent_memories()
        self.memory_store.add_message(user_msg)
        yield {
            "type": "user_input",
            "agent": "User",
            "content": task,
            "id": user_msg.id,
        }

        async for event in self._run_root_coordinator_phase(task):
            yield event

        yield {
            "type": "phase",
            "phase": "research",
            "round": 1,
            "content": "Research Phase",
        }
        yield {
            "type": "info",
            "content": "Product Manager defining research needs...",
        }
        try:
            self.pm_research_plan = await self._run_product_manager_research_plan(task)
        except asyncio.TimeoutError:
            self.pm_research_plan = self._create_minimal_pm_research_plan(
                task,
                "Product Manager planning timed out; continuing so the Research Agent can gather evidence.",
            )
            yield {
                "type": "warning",
                "agent": self.PRODUCT_MANAGER_ROLE,
                "content": (
                    "Research planning timed out, so the engine created "
                    "a compact research-plan scaffold and will continue "
                    "to Research Agent Tavily research."
                ),
            }
        except Exception as e:
            self.pm_research_plan = self._create_minimal_pm_research_plan(
                task,
                f"Product Manager planning failed: {self._error_text(e)}",
            )
            yield {
                "type": "warning",
                "agent": self.PRODUCT_MANAGER_ROLE,
                "content": (
                    "Research planning failed, so the engine created a "
                    "compact research-plan scaffold and will continue "
                    "to Research Agent Tavily research."
                ),
            }

        self.memory_store.add_agent_memory(
            self.PRODUCT_MANAGER_ROLE,
            "Research Plan",
            self.pm_research_plan,
        )
        yield {
            "type": "pm_research_plan",
            "agent": self.PRODUCT_MANAGER_ROLE,
            "content": self.pm_research_plan,
        }

        yield {"type": "info", "content": "Starting Research Agent Tavily research..."}
        result = await self._research_orchestrator().run_initial(task, 0)
        self._apply_research_result(result)
        if result.fallback_used:
            yield self._research_warning_event(
                result,
                "Tavily research is unavailable or failed; continuing with a fallback evidence brief",
            )

        research_path = self._write_json_artifact(
            "research_brief.json",
            result.artifact_payload,
        )
        self.research_artifact_path = research_path
        yield {
            "type": "artifact",
            "content": f"Research brief written to {research_path}",
        }
        briefs_path = self._write_json_artifact(
            "agent_briefs.json",
            {
                "task": task,
                "agent_briefs": self._findings_to_agent_briefs(result.findings),
                "research": result.structured.to_dict(),
            },
        )
        self.agent_briefs_artifact_path = briefs_path
        yield {
            "type": "artifact",
            "content": f"Agent briefs written to {briefs_path}",
        }
        yield self._research_complete_event(result)

        for finding in result.findings:
            finding["content"] = self._compress_text(finding["content"], 1800)
            self.memory_store.add_message(
                Message(agent=finding["agent"], content=finding["content"])
            )
            self._store_research_in_agent_memory(finding)

        async for event in self._run_agent_planner_phase(task, result):
            yield event

        if self._use_parallel_debate_engine():
            async for event in self._run_parallel_debate_rounds(
                task,
                result.findings,
                max_rounds,
            ):
                yield event
        else:
            async for event in self._run_sequential_debate_rounds(
                result.findings,
                max_rounds,
            ):
                yield event

        yield {
            "type": "phase",
            "phase": "summary",
            "round": max_rounds,
            "content": "Summary Phase",
        }

        try:
            async for event in self._summarize():
                yield event
        except Exception as e:
            yield {
                "type": "error",
                "agent": "Summarizer",
                "content": f"Summarization failed: {self._error_text(e)}",
            }

    async def _run_agent_planner_phase(
        self,
        task: str,
        result: ResearchRunResult,
    ) -> AsyncGenerator[Dict, None]:
        yield {
            "type": "phase",
            "phase": "agent_planning",
            "round": 1,
            "content": "Agent Planner Phase",
        }
        logger.info("selected phase: agent_planning")
        logger.info("core agents included: %s", ", ".join(self._core_debate_agent_roles()))

        self.selected_standby_specialists = await self._select_standby_specialists(
            task,
            result.brief,
        )
        selected_ids = [item["id"] for item in self.selected_standby_specialists]
        logger.info("standby specialists selected: %s", ", ".join(selected_ids) or "none")
        yield {
            "type": "agent_selection",
            "phase": "agent_planning",
            "core_agents": self._core_debate_agent_roles(),
            "standby_specialists": self.selected_standby_specialists,
            "content": (
                "Selected standby specialists: "
                + (", ".join(selected_ids) if selected_ids else "none")
            ),
        }

    async def _run_parallel_debate_rounds(
        self,
        task: str,
        findings: List[Dict],
        max_rounds: int,
    ) -> AsyncGenerator[Dict, None]:
        research_context = self._build_debate_context(findings)
        async for event in self._parallel_debate_engine().run_rounds(
            user_idea=task,
            research_brief=research_context,
            max_rounds=max_rounds,
            selected_agents_for_round=self._select_debate_agents_for_round,
            min_rounds=self.MIN_DEBATE_ROUNDS,
        ):
            if event.get("type") == "round_started":
                yield {
                    "type": "phase",
                    "phase": "debate",
                    "round": event.get("round"),
                    "content": f"Debate Phase - Round {event.get('round')}",
                }
            yield event

    async def _run_sequential_debate_rounds(
        self,
        findings: List[Dict],
        max_rounds: int,
    ) -> AsyncGenerator[Dict, None]:
        for round_idx in range(max_rounds):
            round_num = round_idx + 1

            yield {
                "type": "phase",
                "phase": "debate",
                "round": round_num,
                "content": f"Debate Phase - Round {round_num}",
            }

            debate_context = self._build_debate_context(findings)
            debate_msg = Message(agent="System", content=debate_context)
            self.memory_store.add_message(debate_msg)

            yield {"type": "info", "content": "Starting debate..."}

            selected_agents = self._select_debate_agents_for_round(round_num)
            debate_stage = self._debate_stage(round_num)
            if not selected_agents:
                yield {"type": "warning", "content": "No debate speakers selected."}
                continue

            current_round_responses = []
            async for event in self._run_debate_agents(
                selected_agents,
                debate_msg,
                debate_stage,
                round_num,
            ):
                yield event
                if event.get("type") == "agent_response":
                    current_round_responses.append(
                        {
                            "agent": event.get("agent", "Agent"),
                            "content": event.get("content", ""),
                        }
                    )

            self.debate_round_history.append(
                {
                    "round": round_num,
                    "stage": debate_stage,
                    "responses": current_round_responses,
                }
            )

    def _debate_engine_mode(self) -> str:
        return str(getattr(self, "DEBATE_MODE", "parallel") or "parallel").lower()

    def _use_parallel_debate_engine(self) -> bool:
        return self._debate_engine_mode() == "parallel"

    def _parallel_debate_engine(self) -> ParallelDebateEngine:
        engine = getattr(self, "parallel_debate_engine", None)
        if engine is None:
            self.parallel_debate_engine = ParallelDebateEngine(self)
        return self.parallel_debate_engine

    async def _select_standby_specialists(
        self,
        task: str,
        research_summary: str,
    ) -> List[Dict[str, str]]:
        planner = getattr(self, "agent_planner", None)
        if planner is None:
            return []

        available = [
            {
                "id": agent.get("id"),
                "role": agent.get("role"),
                "description": agent.get("description"),
                "tools": agent.get("tools", []),
            }
            for agent in self.config.get("standby_specialists", [])
        ]
        if not available:
            return []

        prompt = self._render_prompt(
            "agent_planner.select_standby",
            task=task,
            pm_research_plan=self.pm_research_plan,
            research_summary=self._compress_text(research_summary, 2400),
            standby_specialists=json.dumps(available, ensure_ascii=False),
        )
        if not prompt:
            return []

        try:
            planner.reset()
            response = await asyncio.wait_for(planner.astep(prompt), timeout=45.0)
            raw = response.msgs[0].content if response and response.msgs else ""
            data = self._extract_json_object(raw)
            return self._validate_standby_selection(data)
        except Exception as e:
            logger.warning(
                "Agent Planner failed; using core team only: %s",
                self._error_text(e),
            )
            return []

    def _validate_standby_selection(self, data: Any) -> List[Dict[str, str]]:
        if not isinstance(data, dict):
            logger.warning("Agent Planner output was not JSON object; using core team only")
            return []

        items = data.get("selected_specialists", [])
        if not isinstance(items, list):
            logger.warning("Agent Planner output missing selected_specialists list")
            return []

        selected = []
        seen_ids = set()
        seen_roles = set()
        vague = {"expert", "specialist", "advisor", "consultant", "agent", "analyst"}
        standby = getattr(self, "standby_agent_configs", {})
        for item in items:
            if len(selected) >= 5:
                break
            if isinstance(item, str):
                agent_id = item
                reason = ""
                requested_tools = []
            elif isinstance(item, dict):
                agent_id = str(item.get("id") or "").strip()
                reason = str(item.get("reason") or "").strip()
                requested_tools = item.get("tools", [])
            else:
                continue

            config = standby.get(agent_id)
            if not config:
                logger.warning("Rejected unknown standby specialist: %s", agent_id)
                continue

            role = str(config.get("role") or "").strip()
            if agent_id in seen_ids or role.lower() in seen_roles:
                logger.warning("Rejected duplicate standby specialist: %s", agent_id)
                continue
            if not role or role.lower() in vague:
                logger.warning("Rejected vague standby specialist role: %s", role)
                continue
            if requested_tools and not config.get("allow_tools", False):
                logger.warning("Rejected tool request for standby specialist: %s", agent_id)
                continue

            seen_ids.add(agent_id)
            seen_roles.add(role.lower())
            selected.append(
                {
                    "id": agent_id,
                    "role": role,
                    "reason": reason or "Selected by Agent Planner.",
                }
            )

        return selected

    def _log_legacy_config_ignored(self):
        ignored = self.config.get("legacy_config_ignored", [])
        if ignored:
            logger.info("removed legacy config usage: %s", ", ".join(ignored))

    async def _run_root_coordinator_phase(
        self,
        task: str,
    ) -> AsyncGenerator[Dict, None]:
        yield {
            "type": "phase",
            "phase": "orchestration",
            "round": 1,
            "content": "Root Coordinator Planning Phase",
        }
        logger.info("selected phase: orchestration")
        agent = self.agents.get(self.COORDINATOR_ROLE)
        if agent is None:
            self.root_coordination_plan = (
                "Root Coordinator unavailable; continuing with the fixed hybrid flow."
            )
            yield {
                "type": "warning",
                "agent": self.COORDINATOR_ROLE,
                "content": self.root_coordination_plan,
            }
            return

        prompt = self._render_prompt("orchestration.root_plan", task=task)
        if not prompt:
            self.root_coordination_plan = "Use the configured hybrid flow."
            return

        try:
            agent.reset()
            response = await asyncio.wait_for(
                agent.astep(prompt),
                timeout=float(getattr(self, "ROOT_COORDINATOR_TIMEOUT", 25)),
            )
            self.root_coordination_plan = self._compress_text(
                response.msgs[0].content if response and response.msgs else "",
                1400,
            )
        except asyncio.TimeoutError:
            timeout_seconds = int(getattr(self, "ROOT_COORDINATOR_TIMEOUT", 25))
            self.root_coordination_plan = (
                "Root Coordinator planning timed out; continuing with the fixed "
                f"hybrid flow after {timeout_seconds} seconds."
            )
            yield {
                "type": "warning",
                "agent": self.COORDINATOR_ROLE,
                "content": self.root_coordination_plan,
            }
        except Exception as e:
            self.root_coordination_plan = (
                "Root Coordinator planning failed; continuing with the fixed hybrid flow. "
                f"Reason: {self._error_text(e)}"
            )

        if self.root_coordination_plan:
            self.memory_store.add_agent_memory(
                self.COORDINATOR_ROLE,
                "Orchestration Plan",
                self.root_coordination_plan,
            )
            yield {
                "type": "orchestration_plan",
                "agent": self.COORDINATOR_ROLE,
                "content": self.root_coordination_plan,
            }

    def _research_orchestrator(self) -> ResearchOrchestrator:
        config = getattr(self, "config", None)
        if not config:
            config = ConfigLoader().load()
            self.config = config
        if not hasattr(self, "prompt_renderer"):
            self.prompt_renderer = PromptRenderer(
                config.get("prompts_config", {})
            )
        if not hasattr(self, "research_config"):
            self.research_config = config.get("research_config", {})
        if not hasattr(self, "fallback_policy"):
            self.fallback_policy = FallbackPolicy(self.prompt_renderer, self.research_config)
        orchestrator = getattr(self, "research_orchestrator", None)
        if orchestrator is None:
            self.research_orchestrator = ResearchOrchestrator(self)
        return self.research_orchestrator

    def _apply_research_result(self, result: ResearchRunResult):
        self.research_brief = result.brief
        self.research_artifact_payload = dict(result.artifact_payload or {})
        self.structured_research = result.structured.to_dict()
        self.research_findings = [dict(finding) for finding in result.findings]

    def _research_complete_event(self, result: ResearchRunResult) -> Dict[str, Any]:
        structured = result.structured.to_dict()
        public_summary = self.build_public_research_summary(
            result.artifact_payload or structured or result.brief
        )
        return {
            "type": "research_complete",
            "agent": "Research Agent",
            "content": public_summary,
            "status": structured["status"],
            "fallback_used": structured["fallback_used"],
            "fallback_reason": structured["fallback_reason"],
            "research_quality": structured.get("research_quality"),
            "source_count": len(structured.get("sources", []) or []),
            "objective_count": len(structured.get("objectives", []) or []),
            "artifact_path": getattr(self, "research_artifact_path", ""),
            "agent_briefs_path": getattr(self, "agent_briefs_artifact_path", ""),
        }

    def _research_warning_event(
        self,
        result: ResearchRunResult,
        prefix: str,
    ) -> Dict[str, Any]:
        reason = result.fallback_reason or "unknown reason"
        return {
            "type": "warning",
            "agent": "Research Agent",
            "content": self._compress_text(f"{prefix}: {reason}", 600),
        }

    def _compress_research_result(self, research_result, max_chars: int = 1800) -> str:
        return self._compress_text(str(research_result), max_chars=max_chars)

    def _compress_text(self, text: Any, max_chars: int = 1800) -> str:
        compact = str(text)
        compact = re.sub(
            r"<longcat_tool_call>.*?</longcat_tool_call>",
            "[tool call removed]",
            compact,
            flags=re.IGNORECASE | re.DOTALL,
        )
        compact = re.sub(
            r"<tool_call>.*?</tool_call>",
            "[tool call removed]",
            compact,
            flags=re.IGNORECASE | re.DOTALL,
        )
        compact = re.sub(
            r"\b(?:snapshot|dom|html|text_content)\s*[:=]\s*.{800,}",
            "[research output compressed]",
            compact,
            flags=re.IGNORECASE | re.DOTALL,
        )
        compact = " ".join(compact.split())
        if len(compact) <= max_chars:
            return compact

        head = compact[: max_chars // 2].rstrip()
        tail = compact[-max_chars // 3 :].lstrip()
        return f"{head} ... [compressed {len(compact)} chars] ... {tail}"

    def _write_json_artifact(self, filename: str, payload: Dict) -> str:
        self.run_artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self.run_artifact_dir / filename
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(path)

    def _error_text(self, error: Exception, max_chars: int = 600) -> str:
        text = self._compress_text(str(error), max_chars)
        return text or error.__class__.__name__
