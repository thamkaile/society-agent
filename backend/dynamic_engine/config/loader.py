"""Load engine configuration from the canonical config directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .schema import normalize_legacy_config, normalize_new_config


class ConfigLoader:
    def __init__(self, backend_dir: Path | None = None):
        self.backend_dir = Path(backend_dir or Path(__file__).resolve().parents[2])
        self.config_dir = self.backend_dir / "config"

    def load(self) -> Dict[str, Any]:
        required = ("agents.json", "research.json", "system_prompts.json", "models.json")
        missing = [name for name in required if not (self.config_dir / name).exists()]
        if missing:
            missing_list = ", ".join(missing)
            raise FileNotFoundError(
                f"Missing required backend config file(s) in {self.config_dir}: {missing_list}"
            )

        return normalize_new_config(
            self._read_json(self.config_dir / "agents.json"),
            self._read_json(self.config_dir / "research.json"),
            self._read_json(self.config_dir / "system_prompts.json"),
            self._read_json(self.config_dir / "models.json"),
        )

    def normalize(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if {
            "agents_config",
            "research_config",
            "prompts_config",
            "models_config",
        }.issubset(config):
            return config
        if "core_team" in config or "standby_specialists" in config:
            return normalize_new_config(
                config,
                config.get("research_config", {}),
                config.get("prompts_config", {"version": "inline", "prompts": {}}),
                config.get(
                    "models_config",
                    {
                        "version": "inline",
                        "default_model_id": "default",
                        "models": {
                            "default": {
                                "model_type": "openrouter/owl-alpha",
                                "api_url": "https://openrouter.ai/api/v1",
                                "context_window": 200000,
                                "suppress_unknown_context_warning": True,
                            }
                        },
                    },
                ),
            )
        return normalize_legacy_config(config)

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)


def load_engine_config(backend_dir: Path | None = None) -> Dict[str, Any]:
    return ConfigLoader(backend_dir).load()
