import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Dict, List

from ..models import (
    BLUEPRINT_SECTION_DEFINITIONS,
    BLUEPRINT_TEMPLATE_VERSION,
    CANONICAL_SECTIONS,
    ChatSession,
    ImpactAssessment,
    Message,
)
from services.agent_identity import agent_identity


logger = logging.getLogger(__name__)


class DebateMixin:
    LIVE_MEETING_PRIORITY = (
        "UX Researcher",
        "Finance Analyst",
        "Technical Lead",
        "Product Manager",
    )
    REPORT_MISSING_TEXT = "Insufficient information from the discussion."
    FINAL_REPORT_SECTIONS = (
        "Executive Summary",
        "Problem Statement",
        "Proposed Solution",
        "Market Analysis",
        "Customer Persona",
        "Business Model",
        "Technical Architecture",
        "UX Strategy",
        "Financial Analysis",
        "Marketing Strategy",
        "MVP Definition",
        "Risk Assessment",
        "Agent Debate Summary",
        "Implementation Roadmap",
        "Success Metrics",
        "Final Recommendation",
    )
    AGENT_DEBATE_SUBSECTIONS = (
        "Key Agreements",
        "Key Disagreements",
        "Final Resolution",
    )
    MVP_DEFINITION_SUBSECTIONS = (
        "Phase 1: MVP",
        "Phase 2: Improvements",
        "Phase 3: Future Expansion",
    )
    BLUEPRINT_REQUIRED_BODY_FIELDS = (
        "objective",
        "key_findings",
        "supporting_evidence",
        "risks",
        "mitigation_strategy",
        "recommendation",
        "launch_confidence",
        "confidence_explanation",
        "validated_by",
    )
    BLUEPRINT_BANNED_PATTERNS = (
        r"\bI agree\b",
        r"\bI disagree\b",
        r"\bthe\s+\w+(?:\s+\w+)?\s+agent\s+said\b",
        r"\bas\s+\w+(?:\s+\w+)?\s+mentioned\b",
        r"\bresearch summary\b",
        r"(?m)^\s*\[[^\]\n]{1,60}\]\s*:",
    )

    def _render_prompt(self, prompt_id: str, **values) -> str:
        renderer = getattr(self, "prompt_renderer", None)
        if renderer is None:
            return ""
        return renderer.render(prompt_id, **values)

    async def _run_refinement_debate(
        self,
        session: ChatSession,
        request: str,
        impact: ImpactAssessment,
        findings: List[Dict],
    ) -> AsyncGenerator[Dict, None]:
        yield {
            "type": "phase",
            "phase": "debate",
            "round": 1,
            "content": "Focused Debate Phase",
        }
        context = self._build_refinement_debate_context(session, request, impact, findings)
        debate_msg = Message(agent="System", content=context)
        self.memory_store.add_message(debate_msg)

        selected = [
            (name, self.agents[name])
            for name in impact.agents_needed
            if name in self.agents and name != self.COORDINATOR_ROLE
        ]
        if not selected and self.COORDINATOR_ROLE in self.agents:
            selected = [(self.COORDINATOR_ROLE, self.agents[self.COORDINATOR_ROLE])]
        selected = self._order_live_meeting_agents(selected)

        prior_responses = []
        current_round = []
        for agent_name, agent in selected:
            yield {
                "type": "coordinator_routing",
                "agent": self.COORDINATOR_ROLE,
                "coordinator_selected_agent": agent_name,
                "selected_agent_identity": agent_identity(agent_name),
                "reason": self._routing_reason_for_agent(agent_name, impact),
                "round": 1,
                "phase": "routing",
                "content": f"{self.COORDINATOR_ROLE} selected {agent_name}.",
            }
            yield {
                "type": "agent_typing",
                "agent": agent_name,
                "round": 1,
                "phase": "debate",
                "content": "",
            }
            event = await self._run_debate_step(
                agent,
                agent_name,
                debate_msg,
                prior_responses=prior_responses,
                debate_stage="proposal",
            )
            event["round"] = 1
            for stream_event in self._synthetic_debate_stream_events(event):
                yield stream_event
            if event.get("type") == "agent_response":
                record = {
                    "agent": agent_name,
                    "content": event.get("content", ""),
                }
                current_round.append(record)
                prior_responses.append(record)
        self.debate_round_history.append(
            {"round": 1, "stage": "refinement_proposal", "responses": current_round}
        )

        if self.COORDINATOR_ROLE not in self.agents:
            return

        yield {
            "type": "phase",
            "phase": "consensus",
            "round": 2,
            "content": "Focused Consensus Phase",
        }
        pm_event = await self._run_debate_step(
            self.agents[self.COORDINATOR_ROLE],
            self.COORDINATOR_ROLE,
            debate_msg,
            prior_responses=prior_responses,
            debate_stage="resolution",
        )
        pm_event["round"] = 2
        for stream_event in self._synthetic_debate_stream_events(pm_event):
            yield stream_event
        if pm_event.get("type") == "agent_response":
            self.debate_round_history.append(
                {
                    "round": 2,
                    "stage": "refinement_resolution",
                    "responses": [
                        {
                            "agent": self.COORDINATOR_ROLE,
                            "content": pm_event.get("content", ""),
                        }
                    ],
                }
            )

    def _routing_reason_for_agent(self, agent_name: str, impact: ImpactAssessment) -> str:
        sections = ", ".join(impact.affected_sections[:3])
        rationale = str(impact.rationale or "").strip()
        if sections and rationale:
            return f"{agent_name} was selected because this follow-up affects {sections}. {rationale}"
        if sections:
            return f"{agent_name} was selected because this follow-up affects {sections}."
        if rationale:
            return rationale
        return f"{agent_name} is the best available specialist for this follow-up."

    def _build_refinement_debate_context(
        self,
        session: ChatSession,
        request: str,
        impact: ImpactAssessment,
        findings: List[Dict],
    ) -> str:
        affected = {
            section: session.sections.get(section, {})
            for section in impact.affected_sections
        }
        evidence_context = self._research_evidence_context(findings, session=session)
        return self._compress_text(
            self._render_prompt(
                "debate.refinement_context",
                request=request,
                original_idea=session.user_idea,
                affected_sections=json.dumps(affected, ensure_ascii=False),
                impact_assessment=json.dumps(impact.to_dict(), ensure_ascii=False),
                findings=evidence_context,
            ),
            8000,
        )

    def _select_parallel_debate_agents(self, speakers: List[str]) -> List:
        """Keep debate role coverage stable while still allowing router hints."""
        ordered_names = []
        for name in speakers:
            if name in self.agents and name not in ordered_names:
                ordered_names.append(name)

        for name in self.agents:
            if name not in ordered_names:
                ordered_names.append(name)

        return [(name, self.agents[name]) for name in ordered_names[:8]]

    def _core_debate_agent_roles(self) -> List[str]:
        orchestration_only_ids = {
            getattr(self, "RESEARCH_AGENT_ID", "research_agent"),
            "root_coordinator",
            "agent_planner",
            "report_generator",
        }
        roles = []
        for agent in getattr(self, "config", {}).get("core_team", []):
            if agent.get("id") in orchestration_only_ids:
                continue
            role = agent.get("role")
            if role in self.agents and role not in roles:
                roles.append(role)
        if not roles:
            for role in getattr(self, "agents", {}):
                if role not in {
                    "Root Coordinator",
                    "Research Agent",
                    "Agent Planner",
                    "Report Generator",
                }:
                    roles.append(role)
        return roles

    def _active_debate_agents(self) -> List:
        selected = []
        for role in self._core_debate_agent_roles():
            selected.append((role, self.agents[role]))

        for item in getattr(self, "selected_standby_specialists", []):
            agent_id = item.get("id")
            agent = self._get_or_build_standby_agent(agent_id)
            config = getattr(self, "standby_agent_configs", {}).get(agent_id, {})
            role = config.get("role")
            if agent and role:
                selected.append((role, agent))

        deduped = []
        seen = set()
        for role, agent in selected:
            if role in seen:
                continue
            seen.add(role)
            deduped.append((role, agent))
        return self._order_live_meeting_agents(deduped)

    def _order_live_meeting_agents(self, selected_agents: List) -> List:
        """Prefer a natural live-meeting handoff without changing membership."""
        ordered = []
        seen = set()

        for preferred_role in self.LIVE_MEETING_PRIORITY:
            for role, agent in selected_agents:
                if role == preferred_role and role not in seen:
                    ordered.append((role, agent))
                    seen.add(role)
                    break

        for role, agent in selected_agents:
            if role in seen:
                continue
            ordered.append((role, agent))
            seen.add(role)

        return ordered

    def _debate_stage(self, round_num: int) -> str:
        if round_num == 1:
            return "proposal"
        if round_num == 2:
            return "conflict_response"
        return "resolution"

    def _select_debate_agents_for_round(self, round_num: int) -> List:
        if round_num in {1, 2}:
            return self._active_debate_agents()

        scope_guard = "MVP Scope Guard"
        if scope_guard in self.agents:
            return [(scope_guard, self.agents[scope_guard])]

        coordinator = self.COORDINATOR_ROLE
        if coordinator in self.agents:
            return [(coordinator, self.agents[coordinator])]

        first_name = next(iter(self.agents), None)
        return [(first_name, self.agents[first_name])] if first_name else []

    async def _run_debate_agents(
        self,
        selected_agents: List,
        debate_msg: Message,
        debate_stage: str,
        round_num: int,
    ) -> AsyncGenerator[Dict, None]:
        selected_agents = self._order_live_meeting_agents(selected_agents)
        names = [name for name, _agent in selected_agents]
        self.active_debate_agent_roles = names
        logger.info("debate agents actually executed: %s", ", ".join(names))

        prior_responses = self._prior_debate_context_for_round(round_num)
        logger.info("debate execution mode: live_sequential")
        for agent_name, agent in selected_agents:
            yield {
                "type": "agent_typing",
                "agent": agent_name,
                "round": round_num,
                "phase": "debate",
                "content": "",
            }
            event = await self._run_debate_step(
                agent,
                agent_name,
                debate_msg,
                prior_responses=prior_responses,
                debate_stage=debate_stage,
            )
            event["round"] = round_num
            for stream_event in self._synthetic_debate_stream_events(event):
                yield stream_event
            if event.get("type") == "agent_response":
                prior_responses.append(
                    {
                        "agent": agent_name,
                        "content": event.get("content", ""),
                    }
                )

    async def _run_debate_agents_batched(
        self,
        selected_agents: List,
        debate_msg: Message,
        debate_stage: str,
        round_num: int,
        prior_responses: List[Dict],
    ) -> AsyncGenerator[Dict, None]:
        batch_size = max(1, getattr(self, "DEBATE_CONCURRENCY", 2))
        yield {
            "type": "info",
            "agent": "Debate",
            "round": round_num,
            "content": "Rate limit detected; retrying debate in controlled batches.",
        }
        for idx in range(0, len(selected_agents), batch_size):
            batch = selected_agents[idx : idx + batch_size]
            events = await asyncio.gather(
                *[
                    self._run_debate_step(
                        agent,
                        agent_name,
                        debate_msg,
                        prior_responses=prior_responses,
                        debate_stage=debate_stage,
                    )
                    for agent_name, agent in batch
                ],
                return_exceptions=True,
            )
            for offset, event in enumerate(events):
                event = self._normalize_debate_event(event, batch[offset][0])
                event["round"] = round_num
                yield event
                if event.get("type") == "agent_response":
                    prior_responses.append(
                        {
                            "agent": event.get("agent", "Agent"),
                            "content": event.get("content", ""),
                        }
                    )

    def _normalize_debate_event(self, event, agent_name: str) -> Dict:
        if isinstance(event, Exception):
            return {
                "type": "error",
                "agent": agent_name,
                "content": self._compress_text(str(event), 600),
            }
        return event

    def _synthetic_debate_stream_events(self, event: Dict) -> List[Dict]:
        if event.get("type") != "agent_response":
            return [event]
        content = str(event.get("content") or "")
        words = content.split()
        streamed = []
        cumulative = []
        for index, word in enumerate(words):
            cumulative.append(word)
            streamed.append(
                {
                    **event,
                    "type": "agent_delta",
                    "delta": word + (" " if index < len(words) - 1 else ""),
                    "content": " ".join(cumulative),
                }
            )
        streamed.append(event)
        return streamed

    def _is_rate_limit_event(self, event: Dict) -> bool:
        text = str(event.get("content", "")).lower()
        return event.get("type") == "error" and any(
            marker in text
            for marker in (
                "rate limit",
                "429",
                "too many requests",
                "quota",
                "temporarily overloaded",
            )
        )

    def _detect_conflicting_agent_names(self) -> List[str]:
        if not self.debate_round_history:
            return [
                name for name in self.DEFAULT_CONFLICT_ROLES if name in self.agents
            ]

        latest = self.debate_round_history[-1].get("responses", [])
        conflict_words = (
            "conflict",
            "challenge",
            "risk",
            "tradeoff",
            "too expensive",
            "timeline",
            "cost",
            "budget",
            "cut",
            "scope",
            "feasible",
            "assumption",
            "verify",
        )

        names = []
        for item in latest:
            name = item.get("agent")
            content = item.get("content", "").lower()
            if name in self.agents and any(word in content for word in conflict_words):
                names.append(name)

        for role in self.DEFAULT_CONFLICT_ROLES:
            if role in self.agents and role not in names:
                names.append(role)

        return names[:4]

    def _prior_debate_context_for_round(self, round_num: int) -> List[Dict]:
        if round_num <= 1:
            return []

        prior = []
        for round_record in self.debate_round_history:
            prior.extend(round_record.get("responses", []))
        return prior[-8:]

    def _build_debate_context(self, findings: List[Dict]) -> str:
        """Build context message for debate phase."""
        return self._render_prompt(
            "debate.context",
            findings=self._research_evidence_context(findings),
        )

    def _research_evidence_context(
        self,
        findings: List[Dict],
        session: ChatSession | None = None,
    ) -> str:
        structured = getattr(self, "structured_research", {}) or {}
        if not structured and session is not None:
            session_research = getattr(session, "research_brief", {}) or {}
            if isinstance(session_research, dict):
                structured = session_research.get("research", {}) or {}

        canonical = self._canonical_research_payload(structured)
        public_summary = self.build_public_research_summary(canonical)
        context_parts = [
            "Compressed Tavily research evidence summary:",
            public_summary,
        ]
        if not canonical.get("sources"):
            context_parts.append(
                "Research Evidence Missing: Tavily returned no valid sources. "
                "Agents must say research evidence is missing and must not invent "
                "market, pricing, regulatory, venue, or competitor facts."
            )
        context_parts.append(
            "Evidence rule: cite and use only the compressed Tavily summary, "
            "role-specific research brief, and listed sources provided in this round."
        )

        brief_parts = [
            f"[{finding.get('agent')}]: {self._compress_text(finding.get('content'), 900)}"
            for finding in findings
        ]
        if brief_parts:
            context_parts.append("Compressed agent evidence briefs:")
            context_parts.append("\n\n".join(brief_parts))

        return self._compress_text("\n\n".join(context_parts), 5000)

    def _canonical_research_payload(self, structured: Dict) -> Dict:
        return {
            "status": structured.get("status"),
            "fallback_used": structured.get("fallback_used"),
            "fallback_reason": structured.get("fallback_reason"),
            "research_summary": structured.get("research_summary"),
            "research_quality": structured.get("research_quality"),
            "search_queries": structured.get("search_queries", []),
            "objectives": structured.get("objectives", []),
            "missing_information": structured.get("missing_information", []),
            "failed_sources": structured.get("failed_sources", []),
            "sources": structured.get("sources", []),
        }

    def _agent_memory_context(self, agent_name: str) -> str:
        memory = self.memory_store.get_agent_context(agent_name, limit=8)
        if not memory:
            return "No prior memory for this agent in this session."
        return self._compress_text(memory, 1800)

    def _debate_stage_memory_label(self, debate_stage: str) -> str:
        if debate_stage == "proposal":
            return "Round 1 Proposal"
        if debate_stage == "conflict_response":
            return "Round 2 Conflict Response"
        if debate_stage == "resolution":
            return "Round 3 Coordinator Resolution"
        return "Debate Response"

    async def _run_debate_step(
        self,
        agent: object,
        agent_name: str,
        message: Message,
        prior_responses: List[Dict] | None = None,
        debate_stage: str = "proposal",
    ) -> Dict:
        """Single debate contribution - text only, no tools."""
        agent.reset()
        prior_responses = prior_responses or []
        previous_speaker_name, previous_speaker_message = self._previous_debate_speaker(
            prior_responses
        )
        recent_conversation = self._format_recent_debate(prior_responses)
        agent_memory = self._agent_memory_context(agent_name)
        prompt = self._render_prompt(
            "debate.step",
            task=self.current_task,
            context=message.content,
            role_research_brief=self.build_agent_research_brief(
                getattr(self, "research_artifact_payload", {}) or getattr(self, "structured_research", {}),
                agent_name,
            ),
            agent_memory=agent_memory,
            previous_speaker_name=previous_speaker_name,
            previous_speaker_message=previous_speaker_message,
            recent_conversation=recent_conversation,
            prior_context=recent_conversation,
            agent_name=agent_name,
            stage_instruction=self._debate_instruction(debate_stage),
        )

        try:
            response = await asyncio.wait_for(
                agent.astep(prompt),
                timeout=90.0,
            )

            if response and response.msgs:
                text = self._compress_text(response.msgs[0].content or "", 1400)
                if "<longcat_tool_call>" in text or "<tool_call>" in text:
                    text = (
                        "I attempted to call a tool, but debate agents do not "
                        "have external research tools. I will proceed using only "
                        "the compact research brief and mark unverified claims "
                        "as assumptions."
                    )
                self.memory_store.add_message(Message(agent=agent_name, content=text))
                self.memory_store.add_agent_memory(
                    agent_name,
                    self._debate_stage_memory_label(debate_stage),
                    text,
                )
                return {
                    "type": "agent_response",
                    "agent": agent_name,
                    "content": text,
                }

            return {
                "type": "warning",
                "agent": agent_name,
                "content": "Empty debate response",
            }

        except asyncio.TimeoutError:
            return {
                "type": "error",
                "agent": agent_name,
                "content": "Response timed out",
            }
        except Exception as e:
            return {
                "type": "error",
                "agent": agent_name,
                "content": f"Error: {self._error_text(e)}",
            }

    async def _run_debate_step_limited(
        self,
        semaphore: asyncio.Semaphore,
        agent: object,
        agent_name: str,
        message: Message,
        debate_stage: str = "proposal",
    ) -> Dict:
        async with semaphore:
            return await self._run_debate_step(
                agent,
                agent_name,
                message,
                debate_stage=debate_stage,
            )

    def _debate_instruction(self, debate_stage: str) -> str:
        prompt_id = f"debate.stage.{debate_stage}"
        rendered = self._render_prompt(prompt_id)
        if rendered:
            return rendered
        return self._render_prompt("debate.stage.resolution")

    def _previous_debate_speaker(self, prior_responses: List[Dict]) -> tuple[str, str]:
        if not prior_responses:
            return "User", self.current_task

        previous = prior_responses[-1]
        return (
            previous.get("agent", "Agent"),
            self._compress_text(previous.get("content", ""), 700),
        )

    def _format_prior_debate(self, prior_responses: List[Dict]) -> str:
        return self._format_recent_debate(prior_responses)

    def _format_recent_debate(self, prior_responses: List[Dict]) -> str:
        conversation = [{"agent": "User", "content": self.current_task}]
        conversation.extend(prior_responses)

        recent = conversation[-6:]
        if not prior_responses:
            rendered = self._render_prompt("debate.no_prior", task=self.current_task)
            if rendered:
                return rendered

        parts = []
        for item in recent:
            speaker = item.get("agent", "Agent")
            content = self._compress_text(item.get("content", ""), 500)
            parts.append(f"[{speaker}]: {content}")
        return "\n".join(parts)

    def _build_report_context(self) -> Dict:
        research_brief = self._full_research_brief_for_report()
        agent_briefs = self._findings_to_agent_briefs(
            getattr(self, "research_findings", []) or []
        )
        debate_rounds = self._report_debate_rounds()
        all_agent_messages = self._all_report_agent_messages(
            research_brief=research_brief,
            debate_rounds=debate_rounds,
        )
        structured = getattr(self, "structured_research", {}) or {}
        if isinstance(research_brief, dict):
            missing_evidence = research_brief.get(
                "missing_information",
                structured.get("missing_information", []),
            )
            sources = research_brief.get("sources", structured.get("sources", []))
        else:
            missing_evidence = structured.get("missing_information", [])
            sources = structured.get("sources", [])

        return {
            "user_idea": getattr(self, "current_task", ""),
            "root_plan": getattr(self, "root_coordination_plan", ""),
            "product_research_plan": getattr(self, "pm_research_plan", ""),
            "research_brief": research_brief,
            "agent_briefs": agent_briefs,
            "debate_rounds": debate_rounds,
            "all_agent_messages": all_agent_messages,
            "selected_specialists": getattr(self, "selected_standby_specialists", []),
            "core_agents": self._core_debate_agent_roles(),
            "missing_evidence": missing_evidence or [],
            "sources": sources or [],
        }

    def _full_research_brief_for_report(self):
        payload = getattr(self, "research_artifact_payload", {}) or {}
        raw_brief = payload.get("research_brief") if isinstance(payload, dict) else None
        if isinstance(raw_brief, dict):
            return raw_brief
        if isinstance(raw_brief, str) and raw_brief.strip():
            try:
                parsed = json.loads(raw_brief)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return raw_brief
        structured = getattr(self, "structured_research", {}) or {}
        if structured:
            return structured
        return getattr(self, "research_brief", "")

    def _report_debate_rounds(self) -> List[Dict]:
        rounds = []
        for item in getattr(self, "debate_round_history", []) or []:
            messages = []
            for response in item.get("responses", []) or []:
                agent = response.get("agent", "Agent")
                messages.append(
                    {
                        "agent": agent,
                        "role": agent,
                        "content": response.get("content", ""),
                    }
                )
            rounds.append(
                {
                    "round": item.get("round"),
                    "messages": messages,
                    "consensus": item.get("consensus", ""),
                }
            )
        return rounds

    def _all_report_agent_messages(
        self,
        research_brief,
        debate_rounds: List[Dict],
    ) -> List[Dict]:
        messages = []

        def add(agent: str, content: str, phase: str):
            text = str(content or "").strip()
            if not text or agent == "System":
                return
            messages.append({"agent": agent, "role": agent, "phase": phase, "content": text})

        coordinator_role = getattr(self, "COORDINATOR_ROLE", "Root Coordinator")
        product_manager_role = getattr(self, "PRODUCT_MANAGER_ROLE", "Product Manager")
        add(coordinator_role, getattr(self, "root_coordination_plan", ""), "orchestration")
        add(product_manager_role, getattr(self, "pm_research_plan", ""), "research_plan")
        if research_brief:
            add("Research Agent", self.build_public_research_summary(research_brief), "research")
        for finding in getattr(self, "research_findings", []) or []:
            add(finding.get("agent", "Agent"), finding.get("content", ""), "agent_brief")
        for round_item in debate_rounds:
            phase = f"debate_round_{round_item.get('round')}"
            for message in round_item.get("messages", []) or []:
                add(message.get("agent", "Agent"), message.get("content", ""), phase)
            add(
                "MVP Scope Guard",
                round_item.get("consensus", ""),
                f"{phase}_consensus",
            )

        deduped = []
        seen = set()
        for item in messages:
            key = (item["agent"], item["phase"], item["content"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _build_blueprint_context(self, report_context: Dict | None = None) -> Dict:
        report_context = report_context or self._build_report_context()
        research = report_context.get("research_brief") or {}
        objectives = research.get("objectives", []) if isinstance(research, dict) else []
        completed = 0
        for objective in objectives or []:
            status = str(objective.get("status") or "").lower()
            if status in {"complete", "completed", "covered", "done"}:
                completed += 1
        total = len(objectives or [])
        debate_summary = self._agent_debate_summary_replacements(report_context)
        consensus_text = "\n\n".join(
            str(item.get("consensus") or "").strip()
            for item in report_context.get("debate_rounds", []) or []
            if item.get("consensus")
        )
        return {
            **report_context,
            "blueprint_sections": BLUEPRINT_SECTION_DEFINITIONS,
            "research_coverage": {
                "completed": completed,
                "total": total,
                "label": f"{completed} / {total} Objectives",
            },
            "agreements": debate_summary.get("Key Agreements", ""),
            "disagreements": debate_summary.get("Key Disagreements", ""),
            "final_resolution": debate_summary.get("Final Resolution", ""),
            "consensus_level": self._consensus_level(consensus_text, completed, total),
        }

    def _consensus_level(self, consensus_text: str, completed: int, total: int) -> str:
        text = str(consensus_text or "").lower()
        has_disagreement = bool(
            re.search(r"\b(disagreement|tradeoff|risk|concern|challenge)\b", text)
        )
        coverage_ratio = (completed / total) if total else 0
        if coverage_ratio >= 0.75 and not has_disagreement:
            return "Strong"
        if coverage_ratio >= 0.4 or text.strip():
            return "Moderate"
        return "Weak"

    async def _generate_blueprint_sections(
        self,
        report_context: Dict | None = None,
        section_keys: List[str] | None = None,
    ) -> Dict[str, Dict]:
        blueprint_context = self._build_blueprint_context(report_context)
        selected_sections = [
            section for section in (section_keys or list(CANONICAL_SECTIONS))
            if section in BLUEPRINT_SECTION_DEFINITIONS
        ]
        semaphore = asyncio.Semaphore(3)

        async def run_section(section: str):
            async with semaphore:
                return section, await self._generate_blueprint_section(
                    section,
                    blueprint_context,
                )

        results = await asyncio.gather(
            *(run_section(section) for section in selected_sections),
            return_exceptions=True,
        )
        sections = {}
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Blueprint section generation failed: %s", result)
                continue
            section, payload = result
            sections[section] = payload

        for section in selected_sections:
            if section not in sections:
                sections[section] = self._fallback_blueprint_section(
                    section,
                    blueprint_context,
                    reason="Section writer unavailable.",
                )
        return sections

    async def _generate_blueprint_section(
        self,
        section: str,
        blueprint_context: Dict,
    ) -> Dict:
        definition = BLUEPRINT_SECTION_DEFINITIONS[section]
        owner = definition["owner"]
        agent = self._blueprint_owner_agent(owner)
        if agent is None:
            return self._fallback_blueprint_section(
                section,
                blueprint_context,
                reason=f"{owner} is not available in this run.",
            )

        prompt = self._render_prompt(
            "blueprint.section_writer",
            section_key=section,
            section_title=definition["title"],
            owner=owner,
            blueprint_context=self._compress_text(
                json.dumps(blueprint_context, ensure_ascii=False),
                50000,
            ),
        )
        if not prompt:
            return self._fallback_blueprint_section(
                section,
                blueprint_context,
                reason="Blueprint section prompt is not configured.",
            )

        try:
            agent.reset()
            response = await asyncio.wait_for(agent.astep(prompt), timeout=75.0)
            raw = response.msgs[0].content if response and response.msgs else ""
            parsed = self._extract_json_object(raw)
            return self._normalize_blueprint_section(section, parsed, blueprint_context)
        except Exception as error:
            logger.warning(
                "Blueprint owner %s failed for %s: %s",
                owner,
                section,
                self._error_text(error),
            )
            return self._fallback_blueprint_section(
                section,
                blueprint_context,
                reason=f"{owner} synthesis failed.",
            )

    def _blueprint_owner_agent(self, owner: str):
        if owner == "Research Agent":
            return None
        agents = getattr(self, "agents", {}) or {}
        if owner in agents:
            return agents[owner]
        for agent_id, config in getattr(self, "standby_agent_configs", {}).items():
            if config.get("role") == owner:
                return self._get_or_build_standby_agent(agent_id)
        return None

    def _normalize_blueprint_section(
        self,
        section: str,
        parsed,
        blueprint_context: Dict,
    ) -> Dict:
        if not isinstance(parsed, dict):
            return self._fallback_blueprint_section(
                section,
                blueprint_context,
                reason="Section writer returned non-JSON output.",
            )

        definition = BLUEPRINT_SECTION_DEFINITIONS[section]
        owner = definition["owner"]
        body = parsed.get("body") if isinstance(parsed.get("body"), dict) else parsed
        normalized_body = {}
        fallback = self._default_blueprint_body(section, blueprint_context)
        for field in self.BLUEPRINT_REQUIRED_BODY_FIELDS:
            value = body.get(field, fallback.get(field))
            if field == "launch_confidence":
                normalized_body[field] = self._coerce_launch_confidence(value)
            elif field == "validated_by":
                normalized_body[field] = owner
            elif field in {"key_findings", "supporting_evidence", "risks"}:
                normalized_body[field] = self._sanitize_blueprint_list(value)
            else:
                normalized_body[field] = self._sanitize_blueprint_text(value)

        content = self._format_blueprint_content(definition["title"], normalized_body)
        if self._looks_like_raw_chat_log(content) or self._contains_blueprint_banned_text(content):
            return self._fallback_blueprint_section(
                section,
                blueprint_context,
                reason="Section writer output looked like debate transcript.",
            )

        metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
        coverage = blueprint_context.get("research_coverage", {})
        return {
            "title": definition["title"],
            "owner": owner,
            "content": content,
            "body": normalized_body,
            "metadata": {
                "validated_by": owner,
                "launch_confidence": normalized_body["launch_confidence"],
                "research_coverage": coverage.get("label", "0 / 0 Objectives"),
                "consensus_level": self._normalize_consensus_level(
                    metadata.get("consensus_level")
                    or blueprint_context.get("consensus_level")
                ),
            },
            "status": "draft",
            "source": "blueprint_section_writer",
            "template_version": BLUEPRINT_TEMPLATE_VERSION,
        }

    def _fallback_blueprint_section(
        self,
        section: str,
        blueprint_context: Dict,
        reason: str = "",
    ) -> Dict:
        definition = BLUEPRINT_SECTION_DEFINITIONS[section]
        body = self._default_blueprint_body(section, blueprint_context)
        coverage = blueprint_context.get("research_coverage", {})
        content = self._format_blueprint_content(definition["title"], body)
        return {
            "title": definition["title"],
            "owner": definition["owner"],
            "content": content,
            "body": body,
            "metadata": {
                "validated_by": definition["owner"],
                "launch_confidence": body["launch_confidence"],
                "research_coverage": coverage.get("label", "0 / 0 Objectives"),
                "consensus_level": self._normalize_consensus_level(
                    blueprint_context.get("consensus_level")
                ),
            },
            "status": "draft",
            "source": "deterministic_blueprint_fallback",
            "template_version": BLUEPRINT_TEMPLATE_VERSION,
            "fallback_reason": reason,
        }

    def _default_blueprint_body(self, section: str, blueprint_context: Dict) -> Dict:
        definition = BLUEPRINT_SECTION_DEFINITIONS[section]
        title = definition["title"]
        owner = definition["owner"]
        research = blueprint_context.get("research_brief") or {}
        research_summary = ""
        if isinstance(research, dict):
            research_summary = str(research.get("research_summary") or "").strip()
        findings = self._section_evidence_points(blueprint_context, owner)
        risks = self._section_risk_points(blueprint_context)
        coverage = blueprint_context.get("research_coverage", {})
        completed = int(coverage.get("completed") or 0)
        total = int(coverage.get("total") or 0)
        confidence = self._default_launch_confidence(
            completed,
            total,
            blueprint_context.get("consensus_level"),
            bool(risks),
        )
        return {
            "objective": (
                f"Define the {title.lower()} for the proposed launch decision "
                "using available research, debate outcomes, and unresolved constraints."
            ),
            "key_findings": findings
            or [
                research_summary
                or "Available evidence is limited, so this section should be treated as a planning baseline."
            ],
            "supporting_evidence": self._supporting_evidence_points(blueprint_context),
            "risks": risks or ["Evidence gaps remain and should be validated before scaling."],
            "mitigation_strategy": (
                "Run a focused validation pass on the highest-risk assumptions, keep MVP scope narrow, "
                "and update this section when stronger evidence is available."
            ),
            "recommendation": self._section_recommendation(section, blueprint_context),
            "launch_confidence": confidence,
            "confidence_explanation": (
                f"Confidence reflects {coverage.get('label', '0 / 0 Objectives').lower()}, "
                f"{self._normalize_consensus_level(blueprint_context.get('consensus_level')).lower()} consensus, "
                "and remaining execution risks."
            ),
            "validated_by": owner,
        }

    def _section_evidence_points(self, blueprint_context: Dict, owner: str) -> List[str]:
        points = []
        for finding in (blueprint_context.get("agent_briefs") or {}).items():
            agent, content = finding
            if agent == owner and content:
                points.append(self._sanitize_blueprint_text(content))
        if not points:
            research = blueprint_context.get("research_brief") or {}
            if isinstance(research, dict):
                for objective in research.get("objectives", []) or []:
                    name = objective.get("name")
                    status = objective.get("status")
                    if name:
                        points.append(f"{name} is marked {status or 'unverified'} in the research checklist.")
                    if len(points) >= 3:
                        break
        return [item for item in points if item][:3]

    def _supporting_evidence_points(self, blueprint_context: Dict) -> List[str]:
        points = []
        research = blueprint_context.get("research_brief") or {}
        if isinstance(research, dict):
            for source in research.get("sources", []) or []:
                if isinstance(source, dict):
                    title = source.get("title") or source.get("source_title") or "Source"
                    url = source.get("url") or source.get("source_url") or ""
                    points.append(f"{title}: {url}".strip(": "))
                else:
                    points.append(str(source))
                if len(points) >= 4:
                    break
        if not points:
            missing = blueprint_context.get("missing_evidence") or []
            if missing:
                points.append("Missing evidence remains documented in the research brief.")
        return points or ["No external source was available for this section."]

    def _section_risk_points(self, blueprint_context: Dict) -> List[str]:
        risks = []
        for item in blueprint_context.get("missing_evidence", []) or []:
            text = self._sanitize_blueprint_text(item)
            if text:
                risks.append(text)
            if len(risks) >= 3:
                break
        disagreements = self._sanitize_blueprint_text(
            blueprint_context.get("disagreements", "")
        )
        if disagreements and len(risks) < 3:
            risks.append(disagreements)
        return risks

    def _section_recommendation(self, section: str, blueprint_context: Dict) -> str:
        resolution = self._sanitize_blueprint_text(
            blueprint_context.get("final_resolution", "")
        )
        if resolution:
            return resolution
        if section == "final_recommendation":
            return "Proceed only after validating the highest-risk assumptions with a narrow MVP."
        if section == "product_mvp":
            return "Keep the first release focused on the smallest testable value proposition."
        return "Use this section as a decision baseline and refresh it as stronger validation arrives."

    def _default_launch_confidence(
        self,
        completed: int,
        total: int,
        consensus_level: str,
        has_risks: bool,
    ) -> int:
        score = 52
        if total:
            score += int((completed / total) * 28)
        level = self._normalize_consensus_level(consensus_level)
        if level == "Strong":
            score += 12
        elif level == "Moderate":
            score += 6
        if has_risks:
            score -= 8
        return max(0, min(100, score))

    def _format_blueprint_content(self, title: str, body: Dict) -> str:
        def list_or_text(value):
            if isinstance(value, list):
                clean = [str(item).strip() for item in value if str(item).strip()]
                return "\n".join(f"- {item}" for item in clean) if clean else "- Not specified."
            return str(value or "Not specified.").strip()

        return (
            f"## {title}\n\n"
            f"### Objective\n{list_or_text(body.get('objective'))}\n\n"
            f"### Key Findings\n{list_or_text(body.get('key_findings'))}\n\n"
            f"### Supporting Evidence\n{list_or_text(body.get('supporting_evidence'))}\n\n"
            f"### Risks\n{list_or_text(body.get('risks'))}\n\n"
            f"### Mitigation Strategy\n{list_or_text(body.get('mitigation_strategy'))}\n\n"
            f"### Recommendation\n{list_or_text(body.get('recommendation'))}\n\n"
            f"### Launch Confidence\n{self._coerce_launch_confidence(body.get('launch_confidence'))}%\n\n"
            f"### Confidence Explanation\n{list_or_text(body.get('confidence_explanation'))}\n\n"
            f"### Validated By\n{body.get('validated_by') or 'Responsible Agent'}"
        )

    def _compile_blueprint_markdown(self, sections: Dict[str, Dict]) -> str:
        parts = ["# Startup Blueprint"]
        for section in CANONICAL_SECTIONS:
            payload = sections.get(section) or {}
            title = payload.get("title") or BLUEPRINT_SECTION_DEFINITIONS[section]["title"]
            metadata = payload.get("metadata") or {}
            parts.extend(
                [
                    f"\n# {title}",
                    (
                        f"Validated By: {metadata.get('validated_by') or payload.get('owner')}\n"
                        f"Launch Confidence: {metadata.get('launch_confidence', 0)}%\n"
                        f"Research Coverage: {metadata.get('research_coverage', '0 / 0 Objectives')}\n"
                        f"Consensus Level: {metadata.get('consensus_level', 'Weak')}"
                    ),
                    str(payload.get("content") or "").strip(),
                ]
            )
        return "\n\n".join(part for part in parts if part).strip()

    def _sanitize_blueprint_list(self, value) -> List[str]:
        if isinstance(value, list):
            items = value
        elif value:
            items = [value]
        else:
            items = []
        cleaned = []
        for item in items:
            text = self._sanitize_blueprint_text(item)
            if text:
                cleaned.append(text)
            if len(cleaned) >= 5:
                break
        return cleaned

    def _sanitize_blueprint_text(self, value) -> str:
        text = self._compress_text(value or "", 1200)
        text = re.sub(r"(?m)^\s*\[[^\]\n]{1,60}\]\s*:\s*", "", text)
        text = re.sub(r"\bI agree with\b", "The evidence supports", text, flags=re.I)
        text = re.sub(r"\bI disagree with\b", "The evidence challenges", text, flags=re.I)
        text = re.sub(
            r"\bthe\s+([A-Za-z ]{2,40}?)\s+agent\s+said\b",
            "the available debate context indicates",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"\bas\s+([A-Za-z ]{2,40}?)\s+mentioned\b",
            "based on the available context",
            text,
            flags=re.I,
        )
        text = re.sub(r"\bResearch Summary\b\s*:?", "Evidence", text, flags=re.I)
        return " ".join(text.split())

    def _contains_blueprint_banned_text(self, text: str) -> bool:
        return any(
            re.search(pattern, str(text or ""), flags=re.IGNORECASE)
            for pattern in self.BLUEPRINT_BANNED_PATTERNS
        )

    def _coerce_launch_confidence(self, value) -> int:
        try:
            return max(0, min(100, int(float(str(value).replace("%", "").strip() or 0))))
        except (TypeError, ValueError):
            return 0

    def _normalize_consensus_level(self, value) -> str:
        text = str(value or "").strip().title()
        return text if text in {"Strong", "Moderate", "Weak"} else "Weak"

    def _report_context_debug(self, report_context: Dict) -> Dict:
        messages = report_context.get("all_agent_messages", []) or []
        agent_names = []
        for item in messages:
            agent = item.get("agent")
            if agent and agent not in agent_names:
                agent_names.append(agent)
        return {
            "debate_round_count": len(report_context.get("debate_rounds", []) or []),
            "agent_message_count": len(messages),
            "agent_names": agent_names,
            "has_research_brief": bool(report_context.get("research_brief")),
            "has_product_manager_output": bool(
                report_context.get("product_research_plan")
            ),
        }

    async def _summarize(self) -> AsyncGenerator[Dict, None]:
        """Generate final Blueprint sections and a compatibility markdown summary."""
        recent = self.memory_store.retrieve_relevant(
            "summary conclusion decision", limit=8
        )
        context = self._compress_text(
            "\n".join([f"[{m.agent}]: {m.content}" for m in recent]),
            3000,
        )
        report_context = self._build_report_context()
        debug = self._report_context_debug(report_context)
        logger.info(
            "report context before summarizer: debate_rounds=%s total_agent_messages=%s agents=%s research_brief_present=%s product_manager_output_present=%s",
            debug["debate_round_count"],
            debug["agent_message_count"],
            ", ".join(debug["agent_names"]) or "none",
            debug["has_research_brief"],
            debug["has_product_manager_output"],
        )
        try:
            sections = await self._generate_blueprint_sections(report_context)
            self.generated_blueprint_sections = sections
            yield {
                "type": "summarizer",
                "agent": "Blueprint Synthesizer",
                "content": self._compile_blueprint_markdown(sections),
            }
        except asyncio.TimeoutError:
            yield {
                "type": "summarizer",
                "agent": "Blueprint Synthesizer",
                "content": self._fallback_summary(recent, report_context=report_context),
            }
        except Exception as e:
            yield {
                "type": "error",
                "agent": "Blueprint Synthesizer",
                "content": f"Summary error: {self._error_text(e)}",
            }

    def _fallback_summary(
        self,
        messages: List[Message],
        report_context: Dict | None = None,
    ) -> str:
        """Return a deterministic structured report if the model summary times out."""
        if report_context:
            blueprint_context = self._build_blueprint_context(report_context)
            sections = {
                section: self._fallback_blueprint_section(
                    section,
                    blueprint_context,
                    reason="Summary fallback used.",
                )
                for section in CANONICAL_SECTIONS
            }
            self.generated_blueprint_sections = sections
            return self._compile_blueprint_markdown(sections)
        return self._structured_fallback_report(messages, report_context=report_context)

    def _normalize_final_report(
        self,
        report_text: str,
        fallback_messages: List[Message] | None = None,
        report_context: Dict | None = None,
    ) -> str:
        report = self._compress_markdown_report(report_text)
        if not report or self._looks_like_raw_chat_log(report):
            return self._structured_fallback_report(
                fallback_messages or [],
                report_context=report_context,
            )

        report = self._ensure_required_report_sections(report)
        report = self._ensure_report_subsections(
            report,
            "Agent Debate Summary",
            self.AGENT_DEBATE_SUBSECTIONS,
        )
        report = self._ensure_report_subsections(
            report,
            "MVP Definition",
            self.MVP_DEFINITION_SUBSECTIONS,
        )
        report = self._fill_insufficient_sections_from_context(
            report,
            report_context or {},
        )
        return report

    def _compress_markdown_report(self, text: str, max_chars: int = 12000) -> str:
        compact = str(text or "")
        compact = compact.replace("\r\n", "\n").replace("\r", "\n")
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
        compact = "\n".join(line.rstrip() for line in compact.split("\n")).strip()
        if len(compact) <= max_chars:
            return compact

        head = compact[: max_chars // 2].rstrip()
        tail = compact[-max_chars // 3 :].lstrip()
        return (
            f"{head}\n\n"
            f"... [report compressed {len(compact)} chars] ...\n\n"
            f"{tail}"
        )

    def _looks_like_raw_chat_log(self, text: str) -> bool:
        bracketed_speaker_lines = re.findall(
            r"(?m)^\s*\[[^\]\n]{1,60}\]\s*:",
            str(text or ""),
        )
        return len(bracketed_speaker_lines) >= 2

    def _ensure_required_report_sections(self, report: str) -> str:
        normalized = report.rstrip()
        for heading in self.FINAL_REPORT_SECTIONS:
            if not self._has_markdown_heading(normalized, heading, level=1):
                normalized += f"\n\n# {heading}\n{self.REPORT_MISSING_TEXT}"
        return normalized.strip()

    def _ensure_report_subsections(
        self,
        report: str,
        section_heading: str,
        subsections: tuple[str, ...],
    ) -> str:
        section_match = self._find_markdown_heading(report, section_heading, level=1)
        if not section_match:
            return report

        next_section = re.search(r"(?m)^#\s+", report[section_match.end() :])
        insert_at = (
            section_match.end() + next_section.start()
            if next_section
            else len(report)
        )
        section_body = report[section_match.end() : insert_at]
        missing = [
            subsection
            for subsection in subsections
            if not self._has_markdown_heading(section_body, subsection, level=2)
        ]
        if not missing:
            return report

        insertion = "".join(
            f"\n\n## {subsection}\n{self.REPORT_MISSING_TEXT}"
            for subsection in missing
        )
        return (
            report[:insert_at].rstrip()
            + insertion
            + "\n\n"
            + report[insert_at:].lstrip()
        ).strip()

    def _has_markdown_heading(self, text: str, heading: str, level: int) -> bool:
        return self._find_markdown_heading(text, heading, level) is not None

    def _find_markdown_heading(self, text: str, heading: str, level: int):
        marker = "#" * level
        return re.search(
            rf"(?im)^\s*{re.escape(marker)}\s+{re.escape(heading)}\s*$",
            str(text or ""),
        )

    def _fill_insufficient_sections_from_context(
        self,
        report: str,
        report_context: Dict,
    ) -> str:
        if not report_context:
            return report

        updated = report
        section_agents = {
            "Problem Statement": ["Product Manager", "Business Analyst"],
            "Proposed Solution": ["Product Manager", "Technical Lead", "MVP Scope Guard"],
            "Market Analysis": ["Business Analyst", "Research Agent", "Product Manager"],
            "Customer Persona": ["UX Researcher", "Product Manager"],
            "Business Model": ["Business Analyst", "Finance Analyst"],
            "Technical Architecture": ["Technical Lead"],
            "UX Strategy": ["UX Researcher"],
            "Financial Analysis": ["Finance Analyst"],
            "Marketing Strategy": ["Marketing Strategist"],
            "MVP Definition": ["MVP Scope Guard", "Product Manager"],
            "Risk Assessment": ["Risk & Compliance", "Legal Advisor", "Regulatory Analyst"],
            "Implementation Roadmap": ["MVP Scope Guard", "Technical Lead", "Product Manager"],
            "Success Metrics": ["Product Manager", "Business Analyst", "Marketing Strategist"],
            "Final Recommendation": [
                "MVP Scope Guard",
                getattr(self, "COORDINATOR_ROLE", "Root Coordinator"),
            ],
        }
        for section, agents in section_agents.items():
            body = self._section_body(updated, section)
            if body.strip() != self.REPORT_MISSING_TEXT:
                continue
            evidence = self._evidence_bullets_for_section(report_context, agents)
            if evidence:
                updated = self._replace_section_body(updated, section, evidence)
        return self._fill_agent_debate_summary_from_context(updated, report_context)

    def _section_body(self, report: str, section_heading: str) -> str:
        match = self._find_markdown_heading(report, section_heading, level=1)
        if not match:
            return ""
        next_section = re.search(r"(?m)^#\s+", report[match.end() :])
        end = match.end() + next_section.start() if next_section else len(report)
        return report[match.end() : end].strip()

    def _replace_section_body(
        self,
        report: str,
        section_heading: str,
        body: str,
    ) -> str:
        match = self._find_markdown_heading(report, section_heading, level=1)
        if not match:
            return report
        next_section = re.search(r"(?m)^#\s+", report[match.end() :])
        end = match.end() + next_section.start() if next_section else len(report)
        replacement = f"\n{body.strip()}\n\n"
        return (report[: match.end()] + replacement + report[end:].lstrip()).strip()

    def _evidence_bullets_for_section(
        self,
        report_context: Dict,
        agents: List[str],
    ) -> str:
        messages = report_context.get("all_agent_messages", []) or []
        selected = []
        for message in messages:
            if message.get("agent") not in agents:
                continue
            content = self._compress_text(message.get("content", ""), 420)
            if content and content not in selected:
                selected.append(f"- {self._sanitize_blueprint_text(content)}")
            if len(selected) >= 3:
                break
        return "\n".join(selected)

    def _fill_agent_debate_summary_from_context(
        self,
        report: str,
        report_context: Dict,
    ) -> str:
        if not report_context.get("debate_rounds"):
            return report

        replacements = self._agent_debate_summary_replacements(report_context)
        updated = report
        for subsection, body in replacements.items():
            current = self._subsection_body(
                updated,
                "Agent Debate Summary",
                subsection,
            )
            if current.strip() not in {"", self.REPORT_MISSING_TEXT}:
                continue
            updated = self._replace_subsection_body(
                updated,
                "Agent Debate Summary",
                subsection,
                body,
            )
        return updated

    def _agent_debate_summary_replacements(self, report_context: Dict) -> Dict[str, str]:
        rounds = report_context.get("debate_rounds", []) or []
        consensus_text = "\n\n".join(
            str(item.get("consensus") or "").strip()
            for item in rounds
            if item.get("consensus")
        )
        messages = []
        for round_item in rounds:
            messages.extend(round_item.get("messages", []) or [])

        agreements = self._extract_labeled_summary(consensus_text, "Key Agreements")
        disagreements = self._extract_labeled_summary(consensus_text, "Key Disagreements")
        resolution = self._extract_labeled_summary(consensus_text, "Final Resolution")

        if not agreements:
            agreements = self._summary_from_messages(
                messages,
                ("agree", "support", "consensus", "aligned", "recommend"),
                "Agents shared support for moving toward a focused, evidence-backed MVP instead of broad initial scope.",
            )
        if not disagreements:
            disagreements = self._summary_from_messages(
                messages,
                ("risk", "tradeoff", "challenge", "concern", "disagree", "defer", "complex"),
                "Agents raised tradeoffs around scope, implementation risk, validation evidence, and which capabilities should be deferred.",
            )
        if not resolution:
            resolution = self._summary_from_messages(
                messages,
                ("recommend", "mvp", "should", "next", "defer", "focus"),
                "Proceed with the smallest testable MVP, reject or defer higher-risk alternatives, and validate the highest-risk assumptions next.",
            )

        return {
            "Key Agreements": agreements,
            "Key Disagreements": disagreements,
            "Final Resolution": resolution,
        }

    def _extract_labeled_summary(self, text: str, label: str) -> str:
        if not text:
            return ""
        labels = "|".join(re.escape(item) for item in self.AGENT_DEBATE_SUBSECTIONS)
        match = re.search(
            rf"(?is){re.escape(label)}\s*:\s*(.*?)(?=\n\s*(?:{labels})\s*:|\Z)",
            text,
        )
        if not match:
            return ""
        return self._compress_text(match.group(1).strip(), 900)

    def _summary_from_messages(
        self,
        messages: List[Dict],
        markers: tuple[str, ...],
        fallback: str,
    ) -> str:
        selected = []
        for message in messages:
            content = str(message.get("content") or "")
            if not any(marker in content.lower() for marker in markers):
                continue
            selected.append(self._sanitize_blueprint_text(content))
            if len(selected) >= 2:
                break
        return " ".join(selected) if selected else fallback

    def _subsection_body(
        self,
        report: str,
        section_heading: str,
        subsection_heading: str,
    ) -> str:
        section_match = self._find_markdown_heading(report, section_heading, level=1)
        if not section_match:
            return ""
        next_section = re.search(r"(?m)^#\s+", report[section_match.end() :])
        section_end = (
            section_match.end() + next_section.start()
            if next_section
            else len(report)
        )
        section_text = report[section_match.end() : section_end]
        subsection_match = self._find_markdown_heading(
            section_text,
            subsection_heading,
            level=2,
        )
        if not subsection_match:
            return ""
        next_subsection = re.search(r"(?m)^##\s+", section_text[subsection_match.end() :])
        subsection_end = (
            subsection_match.end() + next_subsection.start()
            if next_subsection
            else len(section_text)
        )
        return section_text[subsection_match.end() : subsection_end].strip()

    def _replace_subsection_body(
        self,
        report: str,
        section_heading: str,
        subsection_heading: str,
        body: str,
    ) -> str:
        section_match = self._find_markdown_heading(report, section_heading, level=1)
        if not section_match:
            return report
        next_section = re.search(r"(?m)^#\s+", report[section_match.end() :])
        section_end = (
            section_match.end() + next_section.start()
            if next_section
            else len(report)
        )
        section_text = report[section_match.end() : section_end]
        subsection_match = self._find_markdown_heading(
            section_text,
            subsection_heading,
            level=2,
        )
        if not subsection_match:
            return report
        next_subsection = re.search(r"(?m)^##\s+", section_text[subsection_match.end() :])
        body_start = section_match.end() + subsection_match.end()
        body_end = (
            body_start + next_subsection.start()
            if next_subsection
            else section_end
        )
        replacement = f"\n{body.strip()}\n\n"
        return (report[:body_start] + replacement + report[body_end:].lstrip()).strip()

    def _structured_fallback_report(
        self,
        messages: List[Message],
        report_context: Dict | None = None,
    ) -> str:
        agent_names = []
        for item in (report_context or {}).get("all_agent_messages", []) or []:
            agent = item.get("agent")
            if agent and agent not in agent_names and agent != "System":
                agent_names.append(agent)
        for msg in messages or []:
            if msg.agent not in agent_names and msg.agent != "System":
                agent_names.append(msg.agent)

        participant_text = (
            f"Discussion participants included: {', '.join(agent_names)}."
            if agent_names
            else self.REPORT_MISSING_TEXT
        )
        sections = []
        for heading in self.FINAL_REPORT_SECTIONS:
            sections.append(f"# {heading}")
            if heading == "Executive Summary":
                sections.append(participant_text)
            elif heading == "MVP Definition":
                for subsection in self.MVP_DEFINITION_SUBSECTIONS:
                    sections.append(f"\n## {subsection}")
                    sections.append(self.REPORT_MISSING_TEXT)
            elif heading == "Agent Debate Summary":
                for subsection in self.AGENT_DEBATE_SUBSECTIONS:
                    sections.append(f"\n## {subsection}")
                    sections.append(self.REPORT_MISSING_TEXT)
            else:
                sections.append(self.REPORT_MISSING_TEXT)
            sections.append("")
        report = "\n".join(sections).strip()
        return self._fill_insufficient_sections_from_context(
            report,
            report_context or {},
        )

    def _all_agent_memory_context(self) -> str:
        parts = []
        for agent_name in self.agents:
            memory = self.memory_store.get_agent_context(agent_name, limit=6)
            if memory:
                parts.append(f"[{agent_name} Memory]: {memory}")

        if not parts:
            return "No per-agent memory recorded."

        return self._compress_text("\n\n".join(parts), 3500)
