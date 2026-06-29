import asyncio
import types
import unittest

from backend.runtime_bootstrap import bootstrap_runtime

bootstrap_runtime()

from backend.dynamic_engine.core.engine import DynamicStreamingEngine
from backend.dynamic_engine.parallel_debate_engine import ParallelDebateEngine


class FakeMemoryStore:
    def __init__(self):
        self.messages = []
        self.agent_memories = []

    def add_message(self, message):
        self.messages.append(message)

    def add_agent_memory(self, agent_name, label, content):
        self.agent_memories.append(
            {"agent": agent_name, "label": label, "content": content}
        )

    def get_agent_context(self, agent_name, limit=8):
        return ""


class FakeRenderer:
    def __init__(self, complete_consensus=True):
        self.agent_calls = []
        self.consensus_calls = []
        self.complete_consensus = complete_consensus

    def render(self, prompt_id, **values):
        if prompt_id == "debate.parallel_agent_step":
            self.agent_calls.append(dict(values))
            return (
                f"agent={values['agent_name']}\n"
                f"current_round={values['current_round_discussion']}\n"
                f"history={values['debate_history']}\n"
                f"guidance={values['adaptive_guidance']}"
            )
        if prompt_id == "debate.parallel_consensus":
            self.consensus_calls.append(dict(values))
            if self.complete_consensus:
                return (
                    "Key Agreements: Agents agree the MVP should stay focused.\n"
                    "Key Disagreements: Technical Lead raised a risk and tradeoff.\n"
                    "Final Resolution: Recommend a narrow MVP and defer complex features."
                )
            return "Key Agreements: Agents agree the MVP should stay focused."
        if prompt_id == "orchestration.root_plan":
            return "Plan the workflow."
        return ""


class SleepingAgent:
    def __init__(self, name, delay, prompts):
        self.name = name
        self.delay = delay
        self.prompts = prompts

    def reset(self):
        pass

    async def astep(self, prompt):
        self.prompts.setdefault(self.name, []).append(prompt)
        await asyncio.sleep(self.delay)
        return types.SimpleNamespace(
            msgs=[types.SimpleNamespace(content=f"{self.name} finished")]
        )


class FakeHost:
    def __init__(self, complete_consensus=True):
        self.current_task = "Plan a clinic booking app"
        self.active_debate_agent_roles = []
        self.debate_round_history = []
        self.memory_store = FakeMemoryStore()
        self.prompt_renderer = FakeRenderer(complete_consensus=complete_consensus)
        self.COORDINATOR_ROLE = "Root Coordinator"
        self.PRODUCT_MANAGER_ROLE = "Product Manager"
        self.prompts = {}
        self.agents = {
            "MVP Scope Guard": SleepingAgent(
                "MVP Scope Guard",
                0,
                self.prompts,
            )
        }

    def _compress_text(self, text, max_chars=1800):
        return str(text)[:max_chars]

    def _error_text(self, error, max_chars=600):
        return str(error)[:max_chars]

    def _agent_memory_context(self, agent_name):
        return self.memory_store.get_agent_context(agent_name)


class ParallelDebateEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_agents_receive_previous_same_round_speaker_context(self):
        host = FakeHost()
        selected = [
            ("Agent A", SleepingAgent("Agent A", 0, host.prompts)),
            ("Agent B", SleepingAgent("Agent B", 0, host.prompts)),
            ("Agent C", SleepingAgent("Agent C", 0, host.prompts)),
        ]
        engine = ParallelDebateEngine(host)

        events = [
            event
            async for event in engine.run_rounds(
                user_idea=host.current_task,
                research_brief="Shared evidence only.",
                max_rounds=1,
                selected_agents_for_round=lambda round_num: selected,
            )
        ]

        self.assertEqual(events[0]["type"], "round_started")
        self.assertEqual(events[-1]["type"], "round_consensus")
        self.assertIn("No other agent has spoken", host.prompts["Agent A"][0])
        self.assertIn("[Agent A]: Agent A finished", host.prompts["Agent B"][0])
        self.assertIn("[Agent B]: Agent B finished", host.prompts["Agent C"][0])

    async def test_incomplete_conclusion_runs_another_round_with_adaptive_guidance(self):
        host = FakeHost(complete_consensus=False)
        selected = [
            ("Agent A", SleepingAgent("Agent A", 0, host.prompts)),
            ("Agent B", SleepingAgent("Agent B", 0, host.prompts)),
        ]
        engine = ParallelDebateEngine(host)

        events = [
            event
            async for event in engine.run_rounds(
                user_idea=host.current_task,
                research_brief="Shared evidence only.",
                max_rounds=2,
                selected_agents_for_round=lambda round_num: selected,
            )
        ]

        self.assertEqual(
            [event["type"] for event in events if event["type"] == "round_started"],
            ["round_started", "round_started"],
        )
        self.assertTrue(any(event["type"] == "debate_needs_more" for event in events))
        round_two_calls = [
            call for call in host.prompt_renderer.agent_calls if call["round_num"] == 2
        ]
        self.assertTrue(round_two_calls)
        self.assertIn(
            "Challenge assumptions",
            round_two_calls[0]["adaptive_guidance"],
        )
        self.assertIn("Previous round consensus", round_two_calls[0]["round_context"])

    async def test_complete_round_one_consensus_respects_minimum_rounds(self):
        host = FakeHost(complete_consensus=True)
        selected = [
            ("Agent A", SleepingAgent("Agent A", 0, host.prompts)),
            ("Agent B", SleepingAgent("Agent B", 0, host.prompts)),
        ]
        engine = ParallelDebateEngine(host)

        events = [
            event
            async for event in engine.run_rounds(
                user_idea=host.current_task,
                research_brief="Shared evidence only.",
                max_rounds=2,
                selected_agents_for_round=lambda round_num: selected,
                min_rounds=2,
            )
        ]

        self.assertEqual(
            [event["round"] for event in events if event["type"] == "round_started"],
            [1, 2],
        )
        self.assertEqual(
            [call["round_num"] for call in host.prompt_renderer.consensus_calls],
            [1, 2],
        )


class DebateModeSelectionTests(unittest.TestCase):
    def test_parallel_mode_selects_new_engine(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.DEBATE_MODE = "parallel"

        self.assertTrue(engine._use_parallel_debate_engine())

    def test_sequential_mode_keeps_legacy_engine(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.DEBATE_MODE = "sequential"

        self.assertFalse(engine._use_parallel_debate_engine())


class RootCoordinatorTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_coordinator_timeout_yields_warning_and_continues(self):
        engine = object.__new__(DynamicStreamingEngine)
        engine.COORDINATOR_ROLE = "Root Coordinator"
        engine.ROOT_COORDINATOR_TIMEOUT = 0.01
        engine.root_coordination_plan = ""
        engine.prompt_renderer = FakeRenderer()
        engine.memory_store = FakeMemoryStore()
        engine.agents = {
            "Root Coordinator": SleepingAgent("Root Coordinator", 0.05, {})
        }
        engine._compress_text = lambda text, max_chars=1800: str(text)[:max_chars]

        events = [
            event
            async for event in engine._run_root_coordinator_phase("Build a product")
        ]

        self.assertTrue(any(event["type"] == "warning" for event in events))
        self.assertTrue(
            any(
                event["type"] == "orchestration_plan"
                and "timed out" in event["content"]
                for event in events
            )
        )


if __name__ == "__main__":
    unittest.main()
