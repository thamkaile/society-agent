from typing import Dict, List

from ..models import CANONICAL_SECTIONS, ChatSession, ImpactAssessment


class SessionProjectorMixin:
    def _hydrate_session_memory(self, session: ChatSession):
        if session.research_brief:
            self.memory_store.add_agent_memory(
                getattr(self, "PRODUCT_MANAGER_ROLE", "Product Manager"),
                "Prior Research Brief",
                self._compress_text(session.research_brief, 1400),
            )
        for agent_name, brief in session.agent_briefs.items():
            if agent_name in self.agents:
                self.memory_store.add_agent_memory(
                    agent_name,
                    "Prior Agent Brief",
                    self._compress_text(brief, 1200),
                )

    def _findings_from_session(
        self,
        session: ChatSession,
        agents_needed: List[str] | None = None,
    ) -> List[Dict]:
        agents_needed = agents_needed or list(self.agents.keys())
        findings = []
        for agent_name in agents_needed:
            if agent_name not in self.agents:
                continue
            content = session.agent_briefs.get(agent_name)
            if not content:
                content = f"Prior session research brief: {session.research_brief}"
            findings.append(
                {
                    "agent": agent_name,
                    "content": self._compress_text(content, 1800),
                }
            )
        if not findings:
            findings.append(
                {
                    "agent": self.COORDINATOR_ROLE,
                    "content": self._compress_text(session.research_brief, 1800),
                }
            )
        return findings

    def _build_initial_sections(self, task: str, summary_text: str) -> Dict:
        debate_summary = self._compress_text(
            " ".join(
                f"{item.get('agent')}: {item.get('content')}"
                for round_item in self.debate_round_history
                for item in round_item.get("responses", [])
            ),
            3000,
        )
        summary = summary_text or debate_summary or "No final summary was produced."
        sections = {}
        for section in CANONICAL_SECTIONS:
            sections[section] = {
                "status": "draft",
                "source": "initial_run",
                "user_idea": task,
                "content": self._section_content(section, summary, debate_summary),
            }
        return sections

    def _build_refinement_section_updates(
        self,
        session: ChatSession,
        request: str,
        impact: ImpactAssessment,
        summary_text: str,
    ) -> Dict:
        updates = {}
        for section in impact.affected_sections:
            previous = session.sections.get(section, {})
            updates[section] = {
                "status": "updated",
                "source": "refinement",
                "request": request,
                "previous": previous,
                "content": self._section_content(section, summary_text, summary_text),
                "impact_rationale": impact.rationale,
            }
        return updates

    def _section_content(self, section: str, summary: str, debate_summary: str) -> str:
        labels = {
            "mvp_scope": "MVP scope",
            "business_plan": "Business plan",
            "technical_architecture": "Technical architecture",
            "ux_strategy": "UX strategy",
            "marketing_strategy": "Marketing strategy",
            "financial_projection": "Financial projection",
            "pitch_script": "Pitch script",
            "action_items": "Action items",
        }
        label = labels.get(section, section)
        basis = summary or debate_summary or "No agent output was available."
        return self._compress_text(f"{label}: {basis}", 2200)
