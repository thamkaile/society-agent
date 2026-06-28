# router.py
from typing import List
from ..models.models import Message

class Router:
    def __init__(self, agent_roles: List[str], llm_model=None):
        self.agent_roles = agent_roles
        self.llm_model = llm_model

    def select_speakers(self, msg: Message, history: List[Message]) -> List[str]:
        # 1) Rule‑based
        candidates = self._rule_based(msg)
        if candidates:
            return candidates

        # 2) LLM fallback (if model supplied)
        if self.llm_model:
            return self._llm_route(msg, history)

        # 3) Default: if from User, let first 3 agents speak
        if msg.agent == "User":
            return self.agent_roles[:3]

        return []

    def _rule_based(self, msg: Message) -> List[str]:
        content = msg.content.lower()
        agents = []
        keyword_map = {
            "ux": "UX Researcher",
            "ui": "UX Researcher",
            "cost": "Business Analyst",
            "budget": "Business Analyst",
            "tech": "Technical Lead",
            "architecture": "Technical Lead",
            "product": "Product Manager",
            "market": "Business Analyst",
        }
        for keyword, role in keyword_map.items():
            if keyword in content:
                if role not in agents:
                    agents.append(role)
        return agents[:3]

    def _llm_route(self, msg: Message, history: List[Message]) -> List[str]:
        # Placeholder – implement with a cheap LLM call if desired
        return []