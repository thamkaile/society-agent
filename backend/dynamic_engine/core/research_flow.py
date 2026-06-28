"""Research orchestration with structured success/fallback results."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

try:
    from backend.research.tavily_research import TavilyResearch
except ImportError:
    from research.tavily_research import TavilyResearch

from ..models import ChatSession, ImpactAssessment
from ..models.research import StructuredResearch
from .fallback import FallbackPolicy


logger = logging.getLogger(__name__)


@dataclass
class ResearchRunResult:
    brief: str
    findings: List[Dict[str, Any]]
    structured: StructuredResearch
    artifact_payload: Dict[str, Any]

    @property
    def fallback_used(self) -> bool:
        return self.structured.fallback_used

    @property
    def fallback_reason(self) -> str | None:
        return self.structured.fallback_reason


class ResearchOrchestrator:
    def __init__(self, engine):
        self.engine = engine
        self.fallback_policy = FallbackPolicy(
            engine.prompt_renderer,
            getattr(engine, "research_config", {}),
        )
        self.tavily_research = TavilyResearch(
            getattr(engine, "research_config", {}).get("tavily", {})
        )

    async def run_initial(self, task: str, round_idx: int) -> ResearchRunResult:
        if self.engine.research_findings and not self.engine.RESEARCH_EVERY_ROUND:
            brief = self.engine._compress_text(
                "Reusing compact Research Agent evidence brief from round 1.",
                600,
            )
            structured = StructuredResearch.from_brief(
                task=task,
                raw_brief=brief,
                findings=[dict(finding) for finding in self.engine.research_findings],
            )
            return ResearchRunResult(
                brief=brief,
                findings=[dict(finding) for finding in self.engine.research_findings],
                structured=structured,
                artifact_payload={
                    "task": task,
                    "pm_research_plan": self.engine.pm_research_plan,
                    "research": structured.to_dict(),
                },
            )

        research_task = self.engine._create_research_task(task, round_idx)
        return await self._run_research(
            task=task,
            research_task=research_task,
            timeout=self._research_timeout(),
            fallback_prefix="Research Agent Tavily research",
            artifact_extra={"pm_research_plan": self.engine.pm_research_plan},
        )

    async def run_targeted(
        self,
        session: ChatSession,
        task: str,
        impact: ImpactAssessment,
    ) -> ResearchRunResult:
        research_task = self.engine._create_targeted_research_task(session, task, impact)
        return await self._run_research(
            task=task,
            research_task=research_task,
            timeout=self._research_timeout(),
            fallback_prefix="Targeted research",
            artifact_extra={"research_questions": impact.research_questions},
        )

    async def _run_research(
        self,
        task: str,
        research_task: str,
        timeout: float,
        fallback_prefix: str,
        artifact_extra: Dict[str, Any] | None = None,
    ) -> ResearchRunResult:
        artifact_extra = artifact_extra or {}
        try:
            logger.info("%s: calling TavilyResearch.build_structured_evidence", fallback_prefix)
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.tavily_research.build_structured_evidence,
                    task,
                    research_task,
                    self.engine.agents.keys(),
                ),
                timeout=timeout,
            )
            logger.info(
                "%s: tavily returned sources=%s failed_sources=%s search_queries=%s",
                fallback_prefix,
                len(response.get("sources", []) or []),
                len(response.get("failed_sources", []) or []),
                len(response.get("search_queries", []) or []),
            )
            raw_brief = json.dumps(response, ensure_ascii=False)
            seed_structured = StructuredResearch.from_brief(
                task=task,
                raw_brief=raw_brief,
                findings=[],
            )
            structured = self._with_missing_evidence_status(seed_structured)
            findings = self.engine._extract_structured_research_findings(structured)
            structured = StructuredResearch.from_brief(
                task=task,
                raw_brief=raw_brief,
                findings=findings,
                status=structured.status,
                fallback_reason=structured.fallback_reason,
            )
            structured = self._with_missing_evidence_status(structured)
            payload = {
                "task": task,
                "research_brief": raw_brief,
                "research": structured.to_dict(),
            }
            payload.update(artifact_extra)
            return ResearchRunResult(raw_brief, findings, structured, payload)
        except asyncio.TimeoutError:
            return self._fallback_result(
                task,
                f"{fallback_prefix} timed out after {int(timeout)} seconds.",
                artifact_extra,
            )
        except Exception as error:
            reason = self.engine._error_text(error)
            return self._fallback_result(task, reason, artifact_extra)

    def _with_missing_evidence_status(
        self,
        structured: StructuredResearch,
    ) -> StructuredResearch:
        if structured.fallback_used or structured.sources:
            return structured

        structured.status = "missing_evidence"
        message = "Research evidence is missing: Tavily returned no valid sources."
        if message not in structured.missing_information:
            structured.missing_information.insert(0, message)
        if structured.research_summary:
            if "Research evidence is missing" not in structured.research_summary:
                structured.research_summary = (
                    f"{structured.research_summary} {message}"
                ).strip()
        else:
            structured.research_summary = message
        return structured

    def _fallback_result(
        self,
        task: str,
        reason: str,
        artifact_extra: Dict[str, Any] | None = None,
    ) -> ResearchRunResult:
        artifact_extra = artifact_extra or {}
        brief = self.engine._compress_text(
            self.fallback_policy.research_brief(task, reason, self.engine.agents.keys()),
            2400,
        )
        findings = self.engine._extract_findings(brief)
        structured = self.fallback_policy.structured_result(
            task,
            reason,
            self.engine.agents.keys(),
            findings,
            brief,
        )
        payload = {
            "task": task,
            "research_brief": brief,
            "research": structured.to_dict(),
            "fallback_reason": reason,
        }
        payload.update(artifact_extra)
        return ResearchRunResult(brief, findings, structured, payload)

    def _research_timeout(self) -> float:
        timeout = (
            getattr(self.engine, "research_config", {})
            .get("timeouts", {})
            .get("research_seconds", 180)
        )
        try:
            return float(timeout)
        except (TypeError, ValueError):
            return 180.0
