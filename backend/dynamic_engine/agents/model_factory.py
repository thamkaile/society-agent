"""Build CAMEL model backends from normalized models.json configuration."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Dict


PLATFORM_ALIASES = {
    "openai_compatible": "openai-compatible-model",
    "openai-compatible": "openai-compatible-model",
    "openai_compatible_model": "openai-compatible-model",
}

GENERATION_CONFIG_KEYS = (
    "temperature",
    "top_p",
    "max_tokens",
    "stream",
    "presence_penalty",
    "frequency_penalty",
    "response_format",
)


class ConfiguredModelFactory:
    """Creates and caches CAMEL models using only normalized config data."""

    def __init__(
        self,
        models_config: Dict[str, Any],
        warning_filter_installer: Callable[[str], None] | None = None,
    ):
        self.models_config = models_config
        self.default_model_id = str(models_config.get("default_model_id") or "")
        self.models = dict(models_config.get("models", {}))
        self._cache: Dict[str, object] = {}
        self._install_warning_filter = warning_filter_installer

    def get_model(self, model_id: str | None = None):
        resolved_model_id = str(model_id or self.default_model_id)
        if resolved_model_id not in self.models:
            raise ValueError(f"Unknown model_id '{resolved_model_id}'.")
        if resolved_model_id not in self._cache:
            self._cache[resolved_model_id] = self._create_model(resolved_model_id)
        return self._cache[resolved_model_id]

    def _create_model(self, model_id: str):
        from camel.models import ModelFactory

        model = dict(self.models[model_id])
        if (
            model.get("suppress_unknown_context_warning")
            and self._install_warning_filter
        ):
            self._install_warning_filter(str(model.get("model_type") or ""))

        model_config_dict = self._model_config_dict(model)
        api_key_env = self._api_key_env(model)
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"API key environment variable '{api_key_env}' is not configured "
                f"for model_id '{model_id}'."
            )

        kwargs: Dict[str, Any] = {
            "model_platform": self._normalize_platform(str(model["platform"])),
            "model_type": model["model_type"],
            "url": model["api_url"],
            "api_key": api_key,
            "model_config_dict": model_config_dict,
        }
        for key in ("timeout", "max_retries"):
            if model.get(key) is not None:
                kwargs[key] = model[key]

        for extra_key in ("client_options", "provider_options"):
            extra = model.get(extra_key)
            if isinstance(extra, dict):
                kwargs.update(extra)

        return ModelFactory.create(**kwargs)

    def _model_config_dict(self, model: Dict[str, Any]) -> Dict[str, Any]:
        config = dict(model.get("model_config") or {})
        for key in GENERATION_CONFIG_KEYS:
            if key in model and key not in config:
                config[key] = model[key]
        return config

    def _api_key_env(self, model: Dict[str, Any]) -> str:
        configured = str(model.get("api_key_env") or "").strip()
        if configured:
            return configured
        provider = str(model.get("provider") or "").strip()
        if not provider:
            raise ValueError("Model provider is required to resolve API key env var.")
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", provider).strip("_").upper()
        if not normalized:
            raise ValueError(f"Cannot derive API key env var from provider '{provider}'.")
        return f"{normalized}_API_KEY"

    def _normalize_platform(self, platform: str) -> str:
        normalized = platform.strip()
        return PLATFORM_ALIASES.get(normalized.lower(), normalized)


class UnknownContextWindowWarningFilter(logging.Filter):
    def __init__(self, model_type: str):
        super().__init__()
        self.model_type = model_type

    def filter(self, record):
        message = record.getMessage()
        if self.model_type and re.search(
            rf"Unknown model '{re.escape(self.model_type)}'.*context window size not defined",
            message,
        ):
            return False
        return True
