"""Small schema helpers for runtime configuration.

The project intentionally keeps validation lightweight so the CLI can run
without extra dependencies. These helpers normalize the supported config shapes
into the internal keys used by the engine.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List


REQUIRED_MODEL_FIELDS = ("provider", "platform", "model_type", "api_url")


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def prompt_template(prompts: Dict[str, Any], prompt_id: str) -> str:
    item = prompts.get(prompt_id, {})
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("template") or "")
    return ""


def normalize_agent(
    agent: Dict[str, Any],
    prompts: Dict[str, Any],
    default_model_id: str,
) -> Dict[str, Any]:
    prompt_id = agent.get("system_prompt_id", "")
    return {
        "id": agent.get("id"),
        "role": agent.get("role"),
        "description": agent.get("description") or agent.get("role"),
        "system_prompt_id": prompt_id,
        "system_message": agent.get("system_message")
        or prompt_template(prompts, prompt_id),
        "model_id": agent.get("model_id", default_model_id),
        "aliases": as_list(agent.get("aliases")),
        "tools": as_list(agent.get("tools")),
        "allow_tools": bool(agent.get("allow_tools", False)),
    }


def normalize_models_config(models_config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(models_config, dict) or not models_config:
        raise ValueError("models_config is required and must come from models.json.")

    raw_models = models_config.get("models")
    if not isinstance(raw_models, dict) or not raw_models:
        raise ValueError("models_config.models must define at least one model.")

    default_model_id = str(models_config.get("default_model_id") or "").strip()
    if not default_model_id:
        raise ValueError("models_config.default_model_id is required.")
    if default_model_id not in raw_models:
        raise ValueError(
            f"default_model_id '{default_model_id}' is not defined in models_config.models."
        )

    normalized_models: Dict[str, Dict[str, Any]] = {}
    for model_id, raw_model in raw_models.items():
        model_id = str(model_id)
        if not isinstance(raw_model, dict):
            raise ValueError(f"Model '{model_id}' must be an object.")
        model = dict(raw_model)
        missing = [
            field
            for field in REQUIRED_MODEL_FIELDS
            if not str(model.get(field) or "").strip()
        ]
        if missing:
            missing_fields = ", ".join(missing)
            raise ValueError(
                f"Model '{model_id}' is missing required field(s): {missing_fields}."
            )
        model["model_id"] = model_id
        normalized_models[model_id] = model

    return {
        "version": str(models_config.get("version") or "1"),
        "default_model_id": default_model_id,
        "models": normalized_models,
    }


def model_config(models_config: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_models_config(models_config)
    default_model_id = normalized["default_model_id"]
    return dict(normalized["models"][default_model_id])


def validate_agent_model_ids(
    agents: Iterable[Dict[str, Any]],
    models_config: Dict[str, Any],
) -> None:
    known_model_ids = set(models_config.get("models", {}))
    for agent in agents:
        model_id = str(agent.get("model_id") or "").strip()
        if model_id and model_id not in known_model_ids:
            agent_id = agent.get("id") or agent.get("role") or "<unknown>"
            raise ValueError(
                f"Agent '{agent_id}' references unknown model_id '{model_id}'."
            )


def normalize_new_config(
    agents_config: Dict[str, Any],
    research_config: Dict[str, Any],
    prompts_config: Dict[str, Any],
    models_config: Dict[str, Any],
) -> Dict[str, Any]:
    prompts = dict(prompts_config.get("prompts", {}))
    normalized_models_config = normalize_models_config(models_config)
    default_model_id = normalized_models_config["default_model_id"]

    raw_core_team = agents_config.get("core_team")
    if raw_core_team is None:
        raw_core_team = agents_config.get("agents", [])
    core_team = [
        normalize_agent(dict(item), prompts, default_model_id)
        for item in raw_core_team
    ]
    standby_specialists = [
        normalize_agent(dict(item), prompts, default_model_id)
        for item in agents_config.get("standby_specialists", [])
    ]

    coordinator_id = agents_config.get("coordinator_agent_id", "root_coordinator")
    coordinator = next(
        (agent for agent in core_team if agent.get("id") == coordinator_id),
        core_team[0] if core_team else {},
    )
    coordinator_role = str(coordinator.get("role") or "Root Coordinator")

    product_manager = next(
        (agent for agent in core_team if agent.get("id") == "product_manager"),
        next((agent for agent in core_team if agent.get("role") == "Product Manager"), {}),
    )
    product_manager_role = str(product_manager.get("role") or "Product Manager")

    research_prompt_id = research_config.get("system_prompt_id")
    research_agent_id = research_config.get("agent_id", "research_agent")
    research_agent = next(
        (agent for agent in core_team if agent.get("id") == research_agent_id),
        None,
    )
    if not research_prompt_id and research_agent:
        research_prompt_id = research_agent.get("system_prompt_id")
    research_prompt_id = research_prompt_id or "agent.research"

    if research_agent:
        research_agent["system_prompt_id"] = research_prompt_id
        research_agent["system_message"] = prompt_template(prompts, research_prompt_id)
        research_agent.setdefault("tools", ["tavily"])
    else:
        research_agent = normalize_agent(
            {
                "id": research_agent_id,
                "role": "Research Agent",
                "description": "Research Agent",
                "system_prompt_id": research_prompt_id,
                "tools": ["tavily"],
            },
            prompts,
            default_model_id,
        )
        core_team.append(research_agent)

    planner = normalize_agent(
        dict(
            agents_config.get(
                "planner",
                {
                    "id": "agent_planner",
                    "role": "Agent Planner",
                    "description": "Agent Planner",
                    "system_prompt_id": "agent.agent_planner",
                    "tools": [],
                },
            )
        ),
        prompts,
        default_model_id,
    )

    all_agents = [*core_team, *standby_specialists, planner]
    validate_agent_model_ids(all_agents, normalized_models_config)
    agent_registry = {
        str(agent.get("id")): agent
        for agent in all_agents
        if agent.get("id")
    }
    legacy_ignored = [
        key
        for key in ("workers", "workforce_config", "task_agent", "workflow_agent")
        if key in agents_config
    ]

    return {
        "version": agents_config.get("version", "1"),
        "agents_config": deepcopy(agents_config),
        "research_config": deepcopy(research_config),
        "prompts_config": deepcopy(prompts_config),
        "models_config": deepcopy(normalized_models_config),
        "core_team": core_team,
        "standby_specialists": standby_specialists,
        "agent_planner": planner,
        "agent_registry": agent_registry,
        "agents": core_team,
        "coordinator_agent_id": coordinator_id,
        "coordinator_role": coordinator_role,
        "product_manager_role": product_manager_role,
        "research_agent": {
            "id": research_agent_id,
            "role": (research_agent or {}).get("role", "Research Agent"),
            "description": (research_agent or {}).get("description", "Research Agent"),
            "system_prompt_id": research_prompt_id,
            "system_message": prompt_template(prompts, research_prompt_id),
            "provider": "tavily",
        },
        "model_config": model_config(normalized_models_config),
        "legacy_config_ignored": legacy_ignored,
    }


def normalize_legacy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    prompts_config = config.get("prompts_config", {"version": "legacy", "prompts": {}})
    models_config = config.get("models_config")
    if not models_config and config.get("model_config"):
        models_config = {
            "version": "legacy",
            "default_model_id": "default",
            "models": {"default": dict(config.get("model_config", {}))},
        }
    if not models_config:
        raise ValueError("Legacy config must provide models_config or model_config.")
    research_config = config.get("research_config", {})
    agents_config = {
        "version": config.get("version", "legacy"),
        "coordinator_agent_id": config.get("coordinator_agent_id", "root_coordinator"),
        "core_team": config.get("core_team", config.get("agents", [])),
        "standby_specialists": config.get("standby_specialists", []),
        "planner": config.get("planner", config.get("agent_planner", {})),
    }
    normalized = normalize_new_config(
        agents_config,
        research_config,
        prompts_config,
        models_config,
    )
    normalized["legacy_config_ignored"] = [
        key
        for key in ("workers", "workforce_config", "task_agent", "workflow_agent")
        if key in config
    ]
    return normalized


def merge_prompt_sources(*sources: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    prompts: Dict[str, Any] = {}
    version = "1"
    for source in sources:
        if not source:
            continue
        version = str(source.get("version") or version)
        prompts.update(dict(source.get("prompts", {})))
    return {"version": version, "prompts": prompts}
