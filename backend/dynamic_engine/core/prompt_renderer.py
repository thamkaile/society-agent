"""Prompt rendering from JSON templates."""

from __future__ import annotations

from typing import Any, Dict


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class PromptRenderer:
    def __init__(self, prompts_config: Dict[str, Any] | None = None):
        prompts_config = prompts_config or {}
        self.prompts = dict(prompts_config.get("prompts", {}))

    def render(self, prompt_id: str, **values: Any) -> str:
        template = self.template(prompt_id)
        if not template:
            return ""
        prepared = {
            key: self._stringify(value)
            for key, value in values.items()
        }
        return template.format_map(SafeFormatDict(prepared))

    def template(self, prompt_id: str) -> str:
        item = self.prompts.get(prompt_id, {})
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            return str(item.get("template") or "")
        return ""

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple, set)):
            return "\n".join(str(item) for item in value)
        return str(value)
