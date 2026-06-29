import re
from typing import Dict, List

from ..models import CANONICAL_SECTIONS, ChatSession, ImpactAssessment, normalize_section_key


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
        report_sections = self._sections_from_final_report(summary)
        sections = {}
        for section in CANONICAL_SECTIONS:
            section_content = report_sections.get(section) or self._section_content(
                section,
                summary,
                debate_summary,
            )
            sections[section] = {
                "status": "draft",
                "source": "initial_run",
                "user_idea": task,
                "content": section_content,
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
            section = normalize_section_key(section)
            if section not in CANONICAL_SECTIONS:
                continue
            previous = session.sections.get(section, {})
            content = self._section_content(section, summary_text, summary_text)
            updates[section] = {
                "status": "updated",
                "source": "refinement",
                "request": request,
                "previous": previous,
                "content": content,
                "impact_rationale": impact.rationale,
            }
        return updates

    def _section_content(self, section: str, summary: str, debate_summary: str) -> str:
        labels = {
            "mvp_scope": "MVP scope",
            "business_plan": "Business plan",
            "technical_architecture": "Technical architecture",
            "ux_strategy": "UX strategy",
            "go_to_market": "Go-to-market strategy",
            "risk_assessment": "Risk assessment",
            "financial_plan": "Financial plan",
        }
        label = labels.get(section, section)
        basis = summary or debate_summary or "No agent output was available."
        return self._compress_text(f"{label}: {basis}", 2200)

    def _merge_section_update(self, before: Dict | None, after: Dict | None) -> Dict:
        before = before if isinstance(before, dict) else {}
        after = after if isinstance(after, dict) else {}
        previous_content = str(before.get("content") or "").strip()
        next_content = str(after.get("content") or "").strip()
        if next_content:
            return after
        if previous_content:
            merged = dict(after)
            merged["content"] = previous_content
            merged["status"] = before.get("status", merged.get("status", "draft"))
            merged["source"] = before.get("source", merged.get("source", "previous"))
            return merged
        return after

    def _sections_from_final_report(self, report: str) -> Dict[str, str]:
        heading_map = {
            "Business Model": "business_plan",
            "Technical Architecture": "technical_architecture",
            "UX Strategy": "ux_strategy",
            "Marketing Strategy": "go_to_market",
            "MVP Definition": "mvp_scope",
            "Risk Assessment": "risk_assessment",
            "Financial Analysis": "financial_plan",
            "Implementation Roadmap": "mvp_scope",
        }
        extracted: Dict[str, str] = {}
        text = str(report or "").replace("\r\n", "\n").replace("\r", "\n")
        for match in re.finditer(r"(?m)^#\s+(.+?)\s*$", text):
            heading = match.group(1).strip()
            key = heading_map.get(heading)
            if not key:
                continue
            next_match = re.search(r"(?m)^#\s+", text[match.end() :])
            end = match.end() + next_match.start() if next_match else len(text)
            body = text[match.end() : end].strip()
            if self._is_usable_section_content(body):
                extracted.setdefault(key, self._compress_text(body, 2200))
        return extracted

    def _is_usable_section_content(self, content: str) -> bool:
        text = str(content or "").strip()
        if not text:
            return False
        missing = getattr(self, "REPORT_MISSING_TEXT", "Insufficient information from the discussion.")
        if text == missing:
            return False
        return True
