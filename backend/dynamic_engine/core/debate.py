import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Dict, List

from ..models import ChatSession, ImpactAssessment, Message


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
            event = await self._run_debate_step(
                agent,
                agent_name,
                debate_msg,
                prior_responses=prior_responses,
                debate_stage="proposal",
            )
            event["round"] = 1
            yield event
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
        yield pm_event
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
            event = await self._run_debate_step(
                agent,
                agent_name,
                debate_msg,
                prior_responses=prior_responses,
                debate_stage=debate_stage,
            )
            event["round"] = round_num
            yield event
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
        """Generate final summary."""
        agent_name = "Report Generator"
        agent = self.agents.get(agent_name) or self.agents.get(self.PRODUCT_MANAGER_ROLE)
        if not agent:
            return

        agent.reset()
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
        agent_memory_context = self._all_agent_memory_context()
        prompt = self._render_prompt(
            "summary.final",
            report_context=self._compress_text(
                json.dumps(report_context, ensure_ascii=False),
                60000,
            ),
            context=context,
            agent_memory_context=agent_memory_context,
        )

        try:
            response = await asyncio.wait_for(
                agent.astep(prompt),
                timeout=45.0,
            )

            if response and response.msgs:
                yield {
                    "type": "summarizer",
                    "agent": agent_name if agent_name in self.agents else "Summarizer",
                    "content": self._normalize_final_report(
                        response.msgs[0].content,
                        recent,
                        report_context=report_context,
                    ),
                }
                return

            yield {
                "type": "summarizer",
                "agent": "Summarizer",
                "content": self._fallback_summary(recent, report_context=report_context),
            }
        except asyncio.TimeoutError:
            yield {
                "type": "summarizer",
                "agent": "Summarizer",
                "content": self._fallback_summary(recent, report_context=report_context),
            }
        except Exception as e:
            yield {
                "type": "error",
                "agent": "Summarizer",
                "content": f"Summary error: {self._error_text(e)}",
            }

    def _fallback_summary(
        self,
        messages: List[Message],
        report_context: Dict | None = None,
    ) -> str:
        """Return a deterministic structured report if the model summary times out."""
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
                selected.append(f"- {message.get('agent')}: {content}")
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
            agent = message.get("agent", "Agent")
            selected.append(f"{agent}: {self._compress_text(content, 260)}")
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
