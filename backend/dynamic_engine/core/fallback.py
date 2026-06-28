"""Central fallback policy for research failures."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from ..models.research import StructuredResearch


class FallbackPolicy:
    def __init__(self, prompt_renderer, research_config: Dict[str, Any] | None = None):
        self.prompt_renderer = prompt_renderer
        self.research_config = research_config or {}

    def research_brief(self, task: str, reason: str, agents: Iterable[str]) -> str:
        agent_sections = "\n".join(
            f"{agent_name}: Tavily research was unavailable; treat any "
            "recommendation as an assumption until fresh evidence is collected."
            for agent_name in agents
        )
        prompt_id = (
            self.research_config.get("fallback", {}).get("prompt_id")
            or "research.fallback_brief"
        )
        rendered = self.prompt_renderer.render(
            prompt_id,
            task=task,
            reason=reason,
            agent_sections=agent_sections,
        )
        if not rendered:
            raise RuntimeError("Research fallback prompt is not configured.")
        return rendered

    def structured_result(
        self,
        task: str,
        reason: str,
        agents: Iterable[str],
        findings,
        raw_brief: str,
    ) -> StructuredResearch:
        return StructuredResearch.from_brief(
            task=task,
            raw_brief=raw_brief,
            findings=findings,
            status="fallback",
            fallback_reason=reason,
        )
