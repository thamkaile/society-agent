import logging
import os
import re

_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
os.environ["OPENAI_API_KEY"] = _OPENROUTER_KEY or ""


class AgentFactoryMixin:
    def _build_model(self):
        from camel.models import ModelFactory
        from camel.types import ModelPlatformType

        model_config = self.config["model_config"]
        if model_config.get("suppress_unknown_context_warning"):
            self._install_model_warning_filter(model_config.get("model_type", ""))

        kwargs = {
            "model_platform": ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            "model_type": model_config["model_type"],
            "url": model_config["api_url"],
            "api_key": _OPENROUTER_KEY,
        }
        return ModelFactory.create(**kwargs)

    def _install_model_warning_filter(self, model_type: str):
        if getattr(self, "_model_warning_filter_installed", False):
            return

        class UnknownContextWindowFilter(logging.Filter):
            def filter(self, record):
                message = record.getMessage()
                if model_type and re.search(
                    rf"Unknown model '{re.escape(model_type)}'.*context window size not defined",
                    message,
                ):
                    return False
                return True

        warning_filter = UnknownContextWindowFilter()
        root_logger = logging.getLogger()
        root_logger.addFilter(warning_filter)
        for handler in root_logger.handlers:
            handler.addFilter(warning_filter)
        self._model_warning_filter_installed = True

    def _build_agents(self):
        """Build always-active core agents. Non-research agents never receive tools."""
        from camel.agents import ChatAgent

        self.core_agent_configs = {
            agent["id"]: agent
            for agent in self.config.get("core_team", [])
            if agent.get("id")
        }
        self.standby_agent_configs = {
            agent["id"]: agent
            for agent in self.config.get("standby_specialists", [])
            if agent.get("id")
        }
        self.agent_configs_by_role = {}
        for agent in [
            *self.config.get("core_team", []),
            *self.config.get("standby_specialists", []),
            self.config.get("agent_planner", {}),
        ]:
            role = agent.get("role")
            if role:
                self.agent_configs_by_role[role] = agent

        skipped = ", ".join(self.config.get("legacy_config_ignored", []))
        if skipped:
            print(f"Legacy config usage ignored: {skipped}")

        for agent_config in self.config.get("core_team", []):
            agent_id = agent_config.get("id")
            role = agent_config.get("role")
            if not role or agent_id == self.config.get("research_agent", {}).get("id"):
                continue
            self.agents[role] = self._create_text_agent(agent_config, ChatAgent)

        self.standby_agents = {}
        self.agent_planner = self._create_text_agent(
            self.config.get("agent_planner", {}),
            ChatAgent,
        )

        print(f"Built {len(self.agents)} core agents")

    def _create_text_agent(self, agent_config: dict, ChatAgent):
        return ChatAgent(
            system_message=self._agent_system_message(agent_config),
            model=self.model,
            tools=None,
            max_iteration=1,
            prune_tool_calls_from_memory=True,
        )

    def _get_or_build_standby_agent(self, agent_id: str):
        from camel.agents import ChatAgent

        if agent_id in self.standby_agents:
            return self.standby_agents[agent_id]

        agent_config = self.standby_agent_configs.get(agent_id)
        if not agent_config:
            return None

        agent = self._create_text_agent(agent_config, ChatAgent)
        self.standby_agents[agent_id] = agent
        return agent

    def _agent_system_message(self, agent_config: dict) -> str:
        prompt_id = agent_config.get("system_prompt_id")
        rendered = ""
        if prompt_id and getattr(self, "prompt_renderer", None):
            rendered = self.prompt_renderer.render(
                prompt_id,
                agent_headings=self._agent_headings(),
            )
        if not rendered:
            rendered = agent_config.get("system_message", "")

        if self._is_live_debate_agent(agent_config):
            rendered = (
                f"{rendered}\n\n"
                "When participating in live debate, speak like a human meeting "
                "participant: respond directly to the previous speaker by name, "
                "agree, disagree, challenge, question, or revise your stance, "
                "stay under 120 words, and do not use report formatting, headings, "
                "numbered lists, or bullet lists. This live-debate rule does not "
                "apply when you are explicitly asked to produce a research plan, "
                "structured JSON, or a final report."
            )
        return rendered

    def _is_live_debate_agent(self, agent_config: dict) -> bool:
        return agent_config.get("id") not in {
            self.config.get("research_agent", {}).get("id"),
            "root_coordinator",
            "agent_planner",
            "report_generator",
        }

    def _setup_research_agent(self):
        """Mark the configured Research Agent as Tavily-backed."""
        self.research_agent = self.config.get("research_agent", {})
        print("Research Agent ready (Tavily)")

    def _agent_headings(self) -> str:
        return "\n".join(f"{name}: [role-specific evidence]" for name in self.agents)

