# models.py
from dataclasses import dataclass, field
from typing import Optional, Any
import uuid
import time


CANONICAL_SECTIONS = (
    "mvp_scope",
    "business_plan",
    "technical_architecture",
    "ux_strategy",
    "go_to_market",
    "risk_assessment",
    "financial_plan",
)


SECTION_ALIASES = {
    "marketing_strategy": "go_to_market",
    "financial_projection": "financial_plan",
    "finance": "financial_plan",
    "financial": "financial_plan",
    "financials": "financial_plan",
    "go_to_market_strategy": "go_to_market",
    "gtm": "go_to_market",
    "risk": "risk_assessment",
    "risks": "risk_assessment",
}


def normalize_section_key(section: str) -> str:
    key = str(section or "").strip().lower().replace(" ", "_").replace("-", "_")
    return SECTION_ALIASES.get(key, key)


@dataclass
class Message:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent: str = "User"
    content: str = ""
    reply_to: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "id": self.id,
            "agent": self.agent,
            "content": self.content,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp,
            "meta": self.meta,
        }


def empty_sections() -> dict:
    return {section: {} for section in CANONICAL_SECTIONS}


@dataclass
class ImpactAssessment:
    affected_sections: list[str] = field(default_factory=list)
    agents_needed: list[str] = field(default_factory=list)
    need_research: bool = False
    research_questions: list[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self):
        return {
            "affected_sections": self.affected_sections,
            "agents_needed": self.agents_needed,
            "need_research": self.need_research,
            "research_questions": self.research_questions,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            affected_sections=list(data.get("affected_sections") or []),
            agents_needed=list(data.get("agents_needed") or []),
            need_research=bool(data.get("need_research", False)),
            research_questions=list(data.get("research_questions") or []),
            rationale=str(data.get("rationale") or ""),
        )


@dataclass
class SessionSectionUpdate:
    section: str
    before: Any = None
    after: Any = None
    request: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        return {
            "section": self.section,
            "before": self.before,
            "after": self.after,
            "request": self.request,
            "timestamp": self.timestamp,
        }


@dataclass
class ChatSession:
    chat_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    user_idea: str = ""
    research_brief: Any = field(default_factory=dict)
    agent_briefs: dict = field(default_factory=dict)
    sections: dict = field(default_factory=empty_sections)
    decision_log: list = field(default_factory=list)
    change_history: list = field(default_factory=list)

    def ensure_sections(self):
        for section in CANONICAL_SECTIONS:
            self.sections.setdefault(section, {})

    def touch(self):
        self.updated_at = time.time()

    def to_dict(self):
        self.ensure_sections()
        return {
            "chat_id": self.chat_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "user_idea": self.user_idea,
            "research_brief": self.research_brief,
            "agent_briefs": self.agent_briefs,
            "sections": self.sections,
            "decision_log": self.decision_log,
            "change_history": self.change_history,
        }

    @classmethod
    def from_dict(cls, data: dict):
        session = cls(
            chat_id=str(data.get("chat_id") or uuid.uuid4()),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            user_idea=str(data.get("user_idea") or ""),
            research_brief=data.get("research_brief") or {},
            agent_briefs=dict(data.get("agent_briefs") or {}),
            sections=dict(data.get("sections") or empty_sections()),
            decision_log=list(data.get("decision_log") or []),
            change_history=list(data.get("change_history") or []),
        )
        session.ensure_sections()
        return session
