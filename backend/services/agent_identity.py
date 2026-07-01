import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _initials(name: str) -> str:
    parts = [part for part in str(name or "").replace("/", " ").split() if part]
    return "".join(part[0].upper() for part in parts)[:2] or "AI"


@lru_cache(maxsize=1)
def _agent_catalog() -> dict[str, dict[str, str]]:
    path = Path(__file__).resolve().parents[1] / "config" / "agents.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    catalog: dict[str, dict[str, str]] = {}
    for group in ("core_team", "standby_specialists"):
        for agent in data.get(group, []) or []:
            role = str(agent.get("role") or agent.get("id") or "Agent")
            identity = {
                "id": str(agent.get("id") or role),
                "name": role,
                "role": str(agent.get("description") or role),
                "description": str(agent.get("description") or ""),
                "avatar": _initials(role),
            }
            catalog[role] = identity
            for alias in agent.get("aliases", []) or []:
                catalog[str(alias)] = identity
    planner = data.get("planner") or {}
    if planner:
        role = str(planner.get("role") or planner.get("id") or "Agent Planner")
        identity = {
            "id": str(planner.get("id") or role),
            "name": role,
            "role": str(planner.get("description") or role),
            "description": str(planner.get("description") or ""),
            "avatar": _initials(role),
        }
        catalog[role] = identity
    catalog.setdefault(
        "Genesis",
        {
            "id": "genesis",
            "name": "Genesis",
            "role": "Startup blueprint workspace",
            "description": "Handles general chat and workspace guidance.",
            "avatar": "G",
        },
    )
    catalog.setdefault(
        "User",
        {
            "id": "user",
            "name": "User",
            "role": "You",
            "description": "",
            "avatar": "U",
        },
    )
    return catalog


def agent_identity(agent_name: Any) -> dict[str, str] | None:
    name = str(agent_name or "").strip()
    if not name:
        return None
    catalog = _agent_catalog()
    identity = catalog.get(name)
    if identity:
        return dict(identity)
    return {
        "id": name.lower().replace(" ", "_"),
        "name": name,
        "role": "Specialist agent",
        "description": "",
        "avatar": _initials(name),
    }


def enrich_event_agent_identity(event: dict) -> dict:
    enriched = dict(event or {})
    if enriched.get("agent") and not enriched.get("agent_identity"):
        enriched["agent_identity"] = agent_identity(enriched.get("agent"))
    selected = enriched.get("coordinator_selected_agent")
    if selected and not enriched.get("selected_agent_identity"):
        enriched["selected_agent_identity"] = agent_identity(selected)
    return enriched
