import asyncio
import json
import re
from typing import Any, Dict, List

from ..models import CANONICAL_SECTIONS, ChatSession, ImpactAssessment
from ..models.research import StructuredResearch


class ResearchMixin:
    def _render_prompt(self, prompt_id: str, **values) -> str:
        renderer = getattr(self, "prompt_renderer", None)
        if renderer is None:
            return ""
        return renderer.render(prompt_id, **values)

    def _create_research_task(self, original_task: str, round_num: int) -> str:
        """Create a focused research brief for the Tavily Research Agent."""
        role_brief = self._research_role_brief()
        configured_guidance = self._configured_research_guidance()
        agent_headings = "\n".join(f"{name}: [role-specific evidence]" for name in self.agents)
        pm_plan = self.pm_research_plan or "No Product Manager plan was produced."
        if round_num == 0:
            prompt = self._render_prompt(
                "research.initial_task",
                task=original_task,
                pm_research_plan=pm_plan,
                configured_guidance=configured_guidance,
                role_brief=role_brief,
                agent_headings=agent_headings,
            )
        else:
            prompt = self._render_prompt(
                "research.followup_task",
                task=original_task,
                pm_research_plan=pm_plan,
                configured_guidance=configured_guidance,
            )

        return prompt

    def _research_role_brief(self) -> str:
        roles = []
        for agent in self.config.get("core_team", []):
            if agent.get("id") in {
                getattr(self, "RESEARCH_AGENT_ID", "research_agent"),
                "root_coordinator",
                "agent_planner",
                "report_generator",
            }:
                continue
            role = agent.get("role") or agent.get("description")
            description = agent.get("description", "")
            if role:
                roles.append(f"- {role}: {description or 'role-relevant findings'}")

        if not roles:
            return "- Product Manager: user, value, risks, evidence, and next steps"

        return "\n".join(roles)

    def _configured_research_guidance(self) -> str:
        guidance = self.config.get("research_guidance")
        if not guidance:
            return ""

        if isinstance(guidance, list):
            lines = [f"- {item}" for item in guidance if item]
            if lines:
                return "Additional research guidance from config:\n" + "\n".join(lines) + "\n\n"
            return ""

        return f"Additional research guidance from config:\n{guidance}\n\n"

    def _create_minimal_pm_research_plan(self, original_task: str, reason: str) -> str:
        role_questions = []
        configured_questions = (
            getattr(self, "research_config", {})
            .get("fallback", {})
            .get("role_questions", {})
        )
        for agent_name in self.agents:
            question = configured_questions.get(
                agent_name,
                configured_questions.get("default", agent_name),
            )
            role_questions.append(f"- {agent_name}: {question}")

        return self._compress_text(
            self._render_prompt(
                "research.pm_plan_fallback",
                task=original_task,
                role_questions="\n".join(role_questions),
                reason=reason,
            ),
            1800,
        )

    async def _run_product_manager_research_plan(self, original_task: str) -> str:
        agent = self.agents.get(getattr(self, "PRODUCT_MANAGER_ROLE", "Product Manager"))
        if agent is None:
            raise RuntimeError("Product Manager agent is not configured.")

        agent.reset()
        role_brief = self._research_role_brief()
        prompt = self._render_prompt(
            "research.pm_plan",
            task=original_task,
            role_brief=role_brief,
        )
        response = await asyncio.wait_for(
            agent.astep(prompt),
            timeout=self.PM_RESEARCH_PLAN_TIMEOUT,
        )
        if not response or not response.msgs:
            raise RuntimeError("Product Manager research plan returned no content.")
        return self._compress_text(response.msgs[0].content or "", 1800)

    async def _run_product_manager_impact_assessment(
        self,
        session: ChatSession,
        request: str,
    ) -> ImpactAssessment:
        agent = self.agents.get(getattr(self, "PRODUCT_MANAGER_ROLE", "Product Manager"))
        if agent is None:
            return self._fallback_impact_assessment(request)

        agent.reset()
        prompt = self._render_prompt(
            "research.impact_assessment",
            canonical_sections=", ".join(CANONICAL_SECTIONS),
            available_agents=", ".join(self.agents.keys()),
            original_idea=session.user_idea,
            existing_sections=json.dumps(session.sections, ensure_ascii=False)[:4000],
            request=request,
        )
        try:
            response = await asyncio.wait_for(
                agent.astep(prompt),
                timeout=self.PM_RESEARCH_PLAN_TIMEOUT,
            )
            content = ""
            if response and response.msgs:
                content = response.msgs[0].content or ""
            return self._parse_impact_assessment(content, request)
        except Exception:
            return self._fallback_impact_assessment(request)

    def _parse_impact_assessment(self, raw: str, request: str = "") -> ImpactAssessment:
        data = self._extract_json_object(raw)
        if not isinstance(data, dict):
            return self._fallback_impact_assessment(request)

        impact = ImpactAssessment.from_dict(data)
        impact.affected_sections = self._normalize_sections(
            impact.affected_sections
        )
        impact.agents_needed = self._normalize_agents(impact.agents_needed)
        impact.research_questions = [
            str(item).strip() for item in impact.research_questions if str(item).strip()
        ][:6]
        if not impact.affected_sections or not impact.agents_needed:
            return self._fallback_impact_assessment(request)
        if impact.need_research and not impact.research_questions:
            impact.research_questions = [request] if request else []
        return impact

    def _extract_json_object(self, raw: str):
        text = str(raw or "").strip()
        if not text:
            return None

        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        else:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)

        try:
            return json.loads(text)
        except Exception:
            return None

    def _fallback_impact_assessment(self, request: str) -> ImpactAssessment:
        sections = list(CANONICAL_SECTIONS)
        agents = list(self.agents.keys())
        needs_research = self._request_needs_research(request)
        questions = [request] if needs_research and request else []
        return ImpactAssessment(
            affected_sections=sections,
            agents_needed=agents,
            need_research=needs_research,
            research_questions=questions,
            rationale="Fallback assessment used because structured PM output was unavailable or incomplete.",
        )

    def _request_needs_research(self, request: str) -> bool:
        content = str(request or "").lower()
        triggers = (
            "current",
            "latest",
            "today",
            "2026",
            "market",
            "competitor",
            "pricing",
            "price",
            "compliance",
            "regulation",
            "legal",
            "law",
            "policy",
            "japan",
            "china",
            "india",
            "europe",
            "eu",
            "uk",
            "canada",
            "singapore",
            "malaysia",
            "us ",
            "u.s.",
            "usa",
        )
        return any(trigger in content for trigger in triggers)

    def _normalize_sections(self, sections: List[str]) -> List[str]:
        aliases = {
            "mvp": "mvp_scope",
            "scope": "mvp_scope",
            "business": "business_plan",
            "business_model": "business_plan",
            "architecture": "technical_architecture",
            "technical": "technical_architecture",
            "tech": "technical_architecture",
            "ux": "ux_strategy",
            "ui": "ux_strategy",
            "marketing": "marketing_strategy",
            "go_to_market": "marketing_strategy",
            "gtm": "marketing_strategy",
            "finance": "financial_projection",
            "financial": "financial_projection",
            "financials": "financial_projection",
            "pitch": "pitch_script",
            "script": "pitch_script",
            "actions": "action_items",
            "next_steps": "action_items",
        }
        normalized = []
        for section in sections or []:
            key = str(section).strip().lower().replace(" ", "_").replace("-", "_")
            key = aliases.get(key, key)
            if key in CANONICAL_SECTIONS and key not in normalized:
                normalized.append(key)
        return normalized

    def _normalize_agents(self, agents: List[str]) -> List[str]:
        available = {name.lower(): name for name in self.agents}
        aliases = {
            "pm": "Product Manager",
            "product": "Product Manager",
            "product_manager": "Product Manager",
            "tech": "Technical Lead",
            "technical": "Technical Lead",
            "engineering": "Technical Lead",
            "business": "Business Analyst",
            "finance": "Finance Analyst",
            "financial": "Finance Analyst",
            "ux": "UX Researcher",
            "ui": "UX Researcher",
            "mvp": "MVP Scope Guard",
            "scope": "MVP Scope Guard",
            "risk": "Risk & Compliance",
            "compliance": "Risk & Compliance",
            "marketing": "Marketing Strategist",
            "executive": getattr(self, "COORDINATOR_ROLE", "Root Coordinator"),
            "leadership": getattr(self, "COORDINATOR_ROLE", "Root Coordinator"),
        }
        normalized = []
        for agent in agents or []:
            raw = str(agent).strip()
            key = raw.lower().replace(" ", "_").replace("-", "_")
            name = aliases.get(key) or available.get(raw.lower())
            if name in self.agents and name not in normalized:
                normalized.append(name)
        coordinator = getattr(self, "COORDINATOR_ROLE", "Root Coordinator")
        if coordinator in self.agents and coordinator not in normalized:
            normalized.append(coordinator)
        return normalized

    def _agents_used_for_refinement(self, impact: ImpactAssessment) -> List[str]:
        agents = list(impact.agents_needed)
        if self.COORDINATOR_ROLE in self.agents and self.COORDINATOR_ROLE not in agents:
            agents.append(self.COORDINATOR_ROLE)
        if impact.need_research and "Research Agent" not in agents:
            agents.append("Research Agent")
        return agents

    def _agents_used_for_initial_run(self) -> List[str]:
        agents = list(self.agents.keys())
        for item in getattr(self, "selected_standby_specialists", []):
            role = item.get("role")
            if role and role not in agents:
                agents.append(role)
        if "Research Agent" not in agents:
            agents.append("Research Agent")
        return agents

    def _create_targeted_research_task(
        self,
        session: ChatSession,
        request: str,
        impact: ImpactAssessment,
    ) -> str:
        questions = "\n".join(f"- {item}" for item in impact.research_questions)
        return self._render_prompt(
            "research.targeted_task",
            original_idea=session.user_idea,
            request=request,
            research_questions=questions or "- Verify the refinement request.",
            affected_sections=", ".join(impact.affected_sections),
            agents_needed=", ".join(impact.agents_needed),
        )

    def _fallback_research_brief(self, task: str, reason: str) -> str:
        if not hasattr(self, "fallback_policy"):
            from .fallback import FallbackPolicy
            from .prompt_renderer import PromptRenderer

            if not hasattr(self, "prompt_renderer"):
                self.prompt_renderer = PromptRenderer(
                    getattr(self, "config", {}).get("prompts_config", {})
                )
            if not hasattr(self, "research_config"):
                self.research_config = getattr(self, "config", {}).get(
                    "research_config",
                    {},
                )
            self.fallback_policy = FallbackPolicy(
                self.prompt_renderer,
                self.research_config,
            )
        return self._compress_text(
            self.fallback_policy.research_brief(task, reason, self.agents.keys()),
            2400,
        )

    def build_public_research_summary(self, research_brief: Any) -> str:
        """Build the short Research Agent message shown in the chat feed."""
        structured = self._structured_research_from_any(research_brief)
        completed = [
            item.get("name", "Objective")
            for item in structured.objectives
            if item.get("status") == "complete"
        ]
        incomplete = [
            item.get("name", "Objective")
            for item in structured.objectives
            if item.get("status") != "complete"
        ]

        key_findings = []
        source_items = []
        for objective in structured.objectives:
            for evidence in objective.get("evidence", []) or []:
                claim = str(evidence.get("claim") or "").strip()
                summary = str(evidence.get("summary") or "").strip()
                title = str(evidence.get("source_title") or "").strip()
                url = str(evidence.get("source_url") or "").strip()
                if claim or summary:
                    text = claim or summary
                    if title:
                        text = f"{text} ({title})"
                    key_findings.append(text)
                if url:
                    source_items.append((title or url, url))

        if not source_items:
            source_items = [(url, url) for url in structured.sources]

        lines = [
            "Research Agent summary",
            f"Research quality: {structured.research_quality or 'weak'}",
            "Objectives completed: " + (", ".join(completed) if completed else "None"),
            "Objectives incomplete: " + (", ".join(incomplete) if incomplete else "None"),
        ]

        if key_findings:
            lines.append("Key findings:")
            for finding in key_findings[:5]:
                lines.append(f"- {self._compress_text(finding, 320)}")

        lines.append("Missing information:")
        if structured.missing_information:
            for item in structured.missing_information[:5]:
                lines.append(f"- {self._compress_text(item, 260)}")
        else:
            lines.append("- None reported.")

        lines.append("Sources:")
        if source_items:
            seen = set()
            added = 0
            for title, url in source_items:
                if url in seen:
                    continue
                seen.add(url)
                lines.append(f"- {self._compress_text(title, 140)}: {url}")
                added += 1
                if added >= 8:
                    break
        else:
            lines.append("- None.")

        return self._compress_text("\n".join(lines), 2800)

    def build_agent_research_brief(self, research_brief: Any, agent_role: str) -> str:
        """Build a compact role-specific research brief for debate prompts."""
        structured = self._structured_research_from_any(research_brief)
        role = str(agent_role or "Agent")
        existing = ""
        for finding in getattr(self, "research_findings", []) or []:
            if finding.get("agent") == role:
                existing = str(finding.get("content") or "")
                break

        evidence_lines = []
        role_key = role.lower()
        for objective in structured.objectives:
            objective_name = str(objective.get("name") or "Objective")
            status = str(objective.get("status") or "incomplete")
            for evidence in objective.get("evidence", []) or []:
                text = " ".join(
                    str(evidence.get(key) or "")
                    for key in ("objective", "claim", "summary", "source_title")
                ).lower()
                include = not existing or any(
                    token in text
                    for token in self._role_research_tokens(role_key)
                )
                if include:
                    evidence_lines.append(
                        (
                            f"{objective_name} ({status}): "
                            f"{evidence.get('claim') or evidence.get('summary')} "
                            f"Source: {evidence.get('source_title') or evidence.get('source_url')}"
                        )
                    )

        parts = [
            f"Research brief for {role}",
            f"Research quality: {structured.research_quality or 'weak'}",
        ]
        if existing:
            parts.append("Role-routed evidence:")
            parts.append(existing)
        elif evidence_lines:
            parts.append("Relevant evidence:")
            parts.extend(f"- {line}" for line in evidence_lines[:6])
        elif structured.research_summary:
            parts.append(f"Research summary: {structured.research_summary}")

        if structured.missing_information:
            parts.append(
                "Missing information: "
                + "; ".join(structured.missing_information[:4])
            )
        if structured.sources:
            parts.append("Sources: " + "; ".join(structured.sources[:6]))

        return self._compress_text("\n".join(parts), 1800)

    def _structured_research_from_any(self, research_brief: Any) -> StructuredResearch:
        if isinstance(research_brief, StructuredResearch):
            return research_brief
        if isinstance(research_brief, dict):
            if "research" in research_brief and isinstance(research_brief["research"], dict):
                return StructuredResearch.from_brief(
                    task=research_brief.get("task") or getattr(self, "current_task", ""),
                    raw_brief=json.dumps(research_brief["research"], ensure_ascii=False),
                    findings=getattr(self, "research_findings", []) or [],
                )
            return StructuredResearch.from_brief(
                task=research_brief.get("task") or getattr(self, "current_task", ""),
                raw_brief=json.dumps(research_brief, ensure_ascii=False),
                findings=getattr(self, "research_findings", []) or [],
            )
        return StructuredResearch.from_brief(
            task=getattr(self, "current_task", ""),
            raw_brief=str(research_brief or ""),
            findings=getattr(self, "research_findings", []) or [],
        )

    def _role_research_tokens(self, role_key: str) -> List[str]:
        if "finance" in role_key:
            return ["pricing", "cost", "finance", "financial", "revenue", "unit economics"]
        if "marketing" in role_key:
            return ["marketing", "channel", "go-to-market", "gtm", "positioning", "customer"]
        if "technical" in role_key:
            return ["technical", "implementation", "feasibility", "platform", "integration"]
        if "ux" in role_key:
            return ["user", "customer", "pain", "behavior", "adoption", "persona"]
        if "risk" in role_key or "compliance" in role_key:
            return ["risk", "regulation", "compliance", "legal", "policy"]
        if "business" in role_key:
            return ["business", "market", "competitor", "pricing", "demand"]
        if "product" in role_key or "mvp" in role_key:
            return ["mvp", "product", "scope", "user", "demand", "problem"]
        return []

    def _extract_findings(self, research_brief: str) -> List[Dict]:
        """Extract role-routed findings from the compressed research brief."""
        structured = StructuredResearch.from_brief(
            task=getattr(self, "current_task", ""),
            raw_brief=research_brief,
            findings=[],
        )
        if structured.objectives or structured.research_summary:
            findings = self._extract_structured_research_findings(structured)
            if findings:
                return findings

        findings = []
        result_str = self._compress_text(research_brief, max_chars=3000)
        headings = [
            "Search Queries Used",
            "Shared Evidence",
            *self.agents.keys(),
            "Failed Sources",
            "Open Questions",
            "Sources",
        ]
        shared = self._extract_heading_section(
            research_brief,
            "Shared Evidence",
            headings,
        )
        sources = self._extract_heading_section(research_brief, "Sources", headings)
        open_questions = self._extract_heading_section(
            research_brief,
            "Open Questions",
            headings,
        )

        for agent_name in self.agents.keys():
            role_section = self._extract_heading_section(
                research_brief,
                agent_name,
                headings,
            )
            content_parts = []
            if shared:
                content_parts.append(f"Shared Evidence: {shared}")
            if role_section:
                content_parts.append(f"{agent_name}: {role_section}")
            if open_questions:
                content_parts.append(f"Open Questions: {open_questions}")
            if sources:
                content_parts.append(f"Sources: {sources}")

            if content_parts:
                findings.append(
                    {
                        "agent": agent_name,
                        "content": self._compress_text(
                            "\n".join(content_parts),
                            1800,
                        ),
                    }
                )

        if not findings:
            for agent_name in self.agents.keys():
                findings.append(
                    {
                        "agent": agent_name,
                        "content": f"Research Agent evidence brief: {result_str}",
                    }
                )

        return findings

    def _extract_structured_research_findings(
        self,
        structured: StructuredResearch,
    ) -> List[Dict]:
        evidence_lines = []
        for objective in structured.objectives:
            name = objective.get("name", "Objective")
            status = objective.get("status", "incomplete")
            evidence = objective.get("evidence", []) or []
            if not evidence:
                evidence_lines.append(f"{name} ({status}): no valid evidence collected.")
                continue
            for item in evidence:
                evidence_lines.append(
                    (
                        f"{name} ({status}): {item.get('claim')} "
                        f"Source: {item.get('source_title')} {item.get('source_url')}. "
                        f"Summary: {item.get('summary')} "
                        f"Confidence: {item.get('confidence')}."
                    )
                )

        content_parts = []
        if not structured.sources:
            content_parts.append(
                "Research Evidence Missing: Tavily returned no valid sources. "
                "Do not invent market facts; state that evidence is missing."
            )
        if structured.research_summary:
            content_parts.append(f"Research Summary: {structured.research_summary}")
        if structured.search_queries:
            content_parts.append(
                "Search Queries: " + "; ".join(structured.search_queries)
            )
        if structured.research_quality:
            content_parts.append(f"Research Quality: {structured.research_quality}")
        if evidence_lines:
            content_parts.append("Evidence: " + " ".join(evidence_lines))
        if structured.missing_information:
            content_parts.append(
                "Missing Information: " + "; ".join(structured.missing_information)
            )
        if structured.sources:
            content_parts.append("Sources: " + "; ".join(structured.sources))
        if structured.failed_sources:
            content_parts.append(
                "Failed Sources: " + "; ".join(structured.failed_sources)
            )

        if not content_parts:
            return []

        content = self._compress_text("\n".join(content_parts), 1800)
        return [
            {
                "agent": agent_name,
                "content": content,
            }
            for agent_name in self.agents.keys()
        ]

    def _extract_heading_section(
        self,
        text: str,
        heading: str,
        headings: List[str],
    ) -> str:
        all_headings = [re.escape(item) for item in headings if item]
        if not all_headings:
            return ""

        heading_pattern = re.escape(heading)
        stop_pattern = "|".join(all_headings)
        match = re.search(
            rf"(?ims)^\s*{heading_pattern}\s*:?\s*(.*?)(?=^\s*(?:{stop_pattern})\s*:|\Z)",
            str(text),
        )
        if not match:
            return ""
        return self._compress_text(match.group(1), 1200)

    def _findings_to_agent_briefs(self, findings: List[Dict]) -> Dict[str, str]:
        return {
            finding.get("agent", "Unknown"): self._compress_text(
                finding.get("content", ""),
                1800,
            )
            for finding in findings
        }

    def _store_research_in_agent_memory(self, finding: Dict):
        content = self._compress_text(finding.get("content", ""), 1200)
        target_agent = finding.get("agent", "")

        if target_agent in self.agents:
            self.memory_store.add_agent_memory(
                target_agent,
                "Research Brief",
                content,
            )
            return

        for agent_name in self.agents:
            self.memory_store.add_agent_memory(
                agent_name,
                "Shared Research Brief",
                content,
            )
