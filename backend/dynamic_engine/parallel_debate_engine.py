"""Debate orchestration for live sequential specialist discussion."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Dict, Iterable, List

from .models.models import Message


@dataclass(frozen=True)
class ParallelAgentResult:
    agent: str
    content: str
    ok: bool = True


@dataclass(frozen=True)
class DebateConclusionStatus:
    has_agreement: bool
    has_disagreement: bool
    has_resolution: bool

    @property
    def is_meaningful(self) -> bool:
        return self.has_agreement and self.has_disagreement and self.has_resolution


class ParallelDebateEngine:
    """Runs specialists one at a time so each agent can respond to prior speakers."""

    AGREEMENT_RE = re.compile(
        r"\b(agree|aligned|alignment|support|consensus|concur|shared|strongest)\b",
        re.IGNORECASE,
    )
    DISAGREEMENT_RE = re.compile(
        r"\b(disagree|challenge|concern|risk|tradeoff|trade-off|assumption|"
        r"however|but|defer|postpone|reject|conflict|not work|too complex)\b",
        re.IGNORECASE,
    )
    RESOLUTION_RE = re.compile(
        r"\b(recommend|decide|decision|final|resolution|direction|next step|"
        r"mvp|should focus|choose|defer|go|revise|no-go)\b",
        re.IGNORECASE,
    )

    def __init__(self, host: Any, clock: Callable[[], float] | None = None):
        self.host = host
        self.clock = clock or time.time

    async def run_rounds(
        self,
        user_idea: str,
        research_brief: str,
        max_rounds: int,
        selected_agents_for_round: Callable[[int], List[tuple[str, object]]],
        min_rounds: int = 1,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        previous_consensus = ""
        unresolved_disagreements = ""
        targeted_questions = ""
        adaptive_guidance = ""

        for round_num in range(1, max_rounds + 1):
            selected_agents = selected_agents_for_round(round_num)
            if not selected_agents:
                yield self._event(
                    "warning",
                    round=round_num,
                    content="No debate speakers selected.",
                )
                continue

            agent_names = [name for name, _agent in selected_agents]
            self.host.active_debate_agent_roles = agent_names
            round_context = self.build_round_context(
                user_idea=user_idea,
                research_brief=research_brief,
                previous_consensus=previous_consensus,
                unresolved_disagreements=unresolved_disagreements,
                targeted_questions=targeted_questions,
                adaptive_guidance=adaptive_guidance,
            )
            self.host.memory_store.add_message(
                Message(agent="System", content=round_context)
            )

            yield self._event(
                "round_started",
                phase="debate",
                round=round_num,
                content=f"Round-table debate round {round_num} started",
                agents=agent_names,
            )

            current_round_results: List[ParallelAgentResult] = []
            current_round_records: List[Dict[str, str]] = []
            for agent_name, agent in selected_agents:
                yield self._event(
                    "agent_started",
                    phase="debate",
                    round=round_num,
                    agent=agent_name,
                    content=f"{agent_name} started round {round_num}",
                )
                prompt = self._agent_prompt(
                    agent_name,
                    round_context,
                    round_num,
                    current_round_records,
                    adaptive_guidance,
                )
                result = await self._run_agent(agent, agent_name, prompt)
                current_round_results.append(result)
                record = {"agent": result.agent, "content": result.content}
                current_round_records.append(record)
                self._store_agent_result(result, round_num)
                yield self._event(
                    "agent_completed",
                    phase="debate",
                    round=round_num,
                    agent=result.agent,
                    content=result.content,
                    ok=result.ok,
                )

            consensus = await self._coordinator_merge(
                round_context=round_context,
                responses=current_round_results,
                round_num=round_num,
            )
            response_records = [
                {"agent": result.agent, "content": result.content}
                for result in current_round_results
            ]
            self.host.debate_round_history.append(
                {
                    "round": round_num,
                    "stage": "sequential",
                    "responses": response_records,
                    "consensus": consensus,
                }
            )
            yield self._event(
                "round_consensus",
                phase="debate",
                round=round_num,
                agent=self._coordinator_name(),
                content=consensus,
            )

            status = self._evaluate_conclusion(consensus, response_records)
            previous_consensus = consensus
            unresolved_disagreements = consensus
            targeted_questions = consensus
            if status.is_meaningful and round_num >= min_rounds:
                break

            adaptive_guidance = self._adaptive_guidance(status)
            if round_num < max_rounds:
                yield self._event(
                    "debate_needs_more",
                    phase="debate",
                    round=round_num,
                    agent="Debate Controller",
                    content=adaptive_guidance,
                )

    def build_round_context(
        self,
        user_idea: str,
        research_brief: str,
        previous_consensus: str = "",
        unresolved_disagreements: str = "",
        targeted_questions: str = "",
        adaptive_guidance: str = "",
    ) -> str:
        parts = [
            "Original user idea:",
            str(user_idea or ""),
            "",
            "Research brief:",
            str(research_brief or ""),
        ]
        if previous_consensus:
            parts.extend(["", "Previous round consensus:", previous_consensus])
        if unresolved_disagreements:
            parts.extend(["", "Unresolved disagreements or tradeoffs:", unresolved_disagreements])
        if targeted_questions:
            parts.extend(["", "Targeted questions for this round:", targeted_questions])
        if adaptive_guidance:
            parts.extend(["", "Debate controller guidance:", adaptive_guidance])
        return self._compress("\n".join(parts), 10000)

    def _agent_prompt(
        self,
        agent_name: str,
        round_context: str,
        round_num: int,
        current_round_records: List[Dict[str, str]],
        adaptive_guidance: str,
    ) -> str:
        previous_speaker = current_round_records[-1]["agent"] if current_round_records else "User"
        previous_message = (
            current_round_records[-1]["content"]
            if current_round_records
            else getattr(self.host, "current_task", "")
        )
        return self.host.prompt_renderer.render(
            "debate.parallel_agent_step",
            task=getattr(self.host, "current_task", ""),
            round_context=round_context,
            role_research_brief=self._role_research_brief(agent_name, round_context),
            agent_memory=self.host._agent_memory_context(agent_name),
            agent_name=agent_name,
            round_num=round_num,
            previous_speaker_name=previous_speaker,
            previous_speaker_message=self._compress(previous_message, 700),
            current_round_discussion=self._format_response_records(
                current_round_records,
                empty="No other agent has spoken yet in this round.",
            ),
            debate_history=self._format_debate_history(),
            adaptive_guidance=adaptive_guidance
            or "Use the prior discussion to move toward a concrete decision.",
        )

    def _role_research_brief(self, agent_name: str, round_context: str) -> str:
        builder = getattr(self.host, "build_agent_research_brief", None)
        if not callable(builder):
            return self._compress(round_context, 1800)
        return builder(
            getattr(self.host, "research_artifact_payload", {})
            or getattr(self.host, "structured_research", {}),
            agent_name,
        )

    async def _run_agent(
        self,
        agent: object,
        agent_name: str,
        prompt: str,
    ) -> ParallelAgentResult:
        try:
            agent.reset()
            response = await asyncio.wait_for(agent.astep(prompt), timeout=90.0)
            if response and response.msgs:
                text = self._clean_agent_text(response.msgs[0].content)
                return ParallelAgentResult(agent=agent_name, content=text)
            return ParallelAgentResult(
                agent=agent_name,
                content="Empty debate response",
                ok=False,
            )
        except asyncio.TimeoutError:
            return ParallelAgentResult(
                agent=agent_name,
                content="Response timed out",
                ok=False,
            )
        except Exception as error:
            return ParallelAgentResult(
                agent=agent_name,
                content=f"Error: {self.host._error_text(error)}",
                ok=False,
            )

    async def _coordinator_merge(
        self,
        round_context: str,
        responses: Iterable[ParallelAgentResult],
        round_num: int,
    ) -> str:
        coordinator_name = self._coordinator_name()
        coordinator = self.host.agents.get(coordinator_name)
        response_text = self._format_responses(responses)
        if coordinator is None:
            return self._fallback_consensus(response_text)

        prompt = self.host.prompt_renderer.render(
            "debate.parallel_consensus",
            task=getattr(self.host, "current_task", ""),
            round_context=round_context,
            agent_responses=response_text,
            round_num=round_num,
        )
        try:
            coordinator.reset()
            response = await asyncio.wait_for(coordinator.astep(prompt), timeout=60.0)
            if response and response.msgs:
                text = self._clean_agent_text(response.msgs[0].content, max_chars=2400)
                self.host.memory_store.add_message(
                    Message(agent=coordinator_name, content=text)
                )
                self.host.memory_store.add_agent_memory(
                    coordinator_name,
                    f"Sequential Round {round_num} Consensus",
                    text,
                )
                return text
        except Exception:
            pass
        return self._fallback_consensus(response_text)

    def _coordinator_name(self) -> str:
        for name in (
            "MVP Scope Guard",
            getattr(self.host, "COORDINATOR_ROLE", ""),
            getattr(self.host, "PRODUCT_MANAGER_ROLE", ""),
        ):
            if name and name in self.host.agents:
                return name
        return next(iter(self.host.agents), "Coordinator")

    def _format_responses(self, responses: Iterable[ParallelAgentResult]) -> str:
        parts = []
        for result in responses:
            parts.append(f"[{result.agent}]: {self._compress(result.content, 1200)}")
        return "\n".join(parts)

    def _format_response_records(
        self,
        records: List[Dict[str, str]],
        empty: str = "No debate history yet.",
    ) -> str:
        if not records:
            return empty
        return "\n".join(
            f"[{item.get('agent', 'Agent')}]: {self._compress(item.get('content', ''), 700)}"
            for item in records[-8:]
        )

    def _format_debate_history(self) -> str:
        records = []
        for round_item in getattr(self.host, "debate_round_history", []) or []:
            for response in round_item.get("responses", []) or []:
                records.append(response)
            if round_item.get("consensus"):
                records.append(
                    {
                        "agent": "Round Consensus",
                        "content": round_item.get("consensus", ""),
                    }
                )
        return self._format_response_records(records, empty="No previous debate rounds yet.")

    def _fallback_consensus(self, response_text: str) -> str:
        if not str(response_text or "").strip():
            return (
                "Key Agreements: The debate did not produce usable agent responses.\n"
                "Key Disagreements: The debate did not produce enough material to compare viewpoints.\n"
                "Final Resolution: Retry the discussion or continue with a minimal, clearly marked assumption-based MVP."
            )
        return self._compress(
            "Key Agreements: The agents generally support moving toward the smallest testable MVP path.\n"
            "Key Disagreements: The transcript includes risks, assumptions, or tradeoffs that must be resolved before expanding scope.\n"
            "Final Resolution: Continue with an evidence-backed MVP direction, defer higher-risk alternatives, and validate the highest-risk assumptions next.\n\n"
            f"Specialist responses:\n{response_text}",
            2400,
        )

    def _store_agent_result(self, result: ParallelAgentResult, round_num: int):
        self.host.memory_store.add_message(
            Message(agent=result.agent, content=result.content)
        )
        self.host.memory_store.add_agent_memory(
            result.agent,
            f"Sequential Round {round_num}",
            result.content,
        )

    def _evaluate_conclusion(
        self,
        consensus: str,
        response_records: List[Dict[str, str]],
    ) -> DebateConclusionStatus:
        transcript = "\n".join(
            [str(consensus or "")]
            + [str(item.get("content", "")) for item in response_records]
        )
        return DebateConclusionStatus(
            has_agreement=bool(self.AGREEMENT_RE.search(transcript)),
            has_disagreement=bool(self.DISAGREEMENT_RE.search(transcript)),
            has_resolution=bool(self.RESOLUTION_RE.search(transcript)),
        )

    def _adaptive_guidance(self, status: DebateConclusionStatus) -> str:
        guidance = []
        if not status.has_disagreement:
            guidance.append(
                "The previous discussion contains little or no disagreement. "
                "Challenge assumptions, identify implementation risks, discuss tradeoffs, "
                "or explain why another proposal may not work."
            )
        if not status.has_agreement:
            guidance.append(
                "The discussion lacks consensus. Identify which ideas are strongest and explain why."
            )
        if not status.has_resolution:
            guidance.append(
                "The discussion has not reached a concrete conclusion. Decide on the recommended MVP direction and justify it."
            )
        return " ".join(guidance)

    def _clean_agent_text(self, text: Any, max_chars: int = 1400) -> str:
        clean = self._compress(text or "", max_chars)
        if "<longcat_tool_call>" in clean or "<tool_call>" in clean:
            return (
                "I attempted to call a tool, but debate agents do not have external "
                "research tools. I will proceed using only the compact research brief "
                "and mark unverified claims as assumptions."
            )
        return clean

    def _compress(self, text: Any, max_chars: int) -> str:
        return self.host._compress_text(text, max_chars)

    def _event(self, event_type: str, **values: Any) -> Dict[str, Any]:
        event = {"type": event_type, "timestamp": self.clock()}
        event.update(values)
        return event
