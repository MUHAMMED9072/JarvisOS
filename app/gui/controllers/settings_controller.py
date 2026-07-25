from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Config
from app.core.logger import JarvisLogger


@dataclass
class ProviderInfo:
    name: str
    status: str  # "available", "stub", "error"


_SETTINGS_FILE = os.path.join(str(Config.DATA_DIR), "settings.json")

_DEFAULTS: dict[str, Any] = {
    "ai_provider": "ollama",
    "voice_enabled": False,
    "whisper_model": "base",
    "wake_word_enabled": False,
    "theme_mode": "dark",
    "log_level": "INFO",
}


class SettingsController:
    """Orchestrates the Settings page."""

    def __init__(self, registry) -> None:
        self.registry = registry
        self._settings: dict[str, Any] = dict(_DEFAULTS)
        self._original: dict[str, Any] = {}
        self._load()
        self.on_settings_applied: Callable[[dict[str, Any]], None] | None = None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.isfile(_SETTINGS_FILE):
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._settings.update(data)
            JarvisLogger.debug("Settings loaded from %s", _SETTINGS_FILE)
        except (OSError, json.JSONDecodeError) as exc:
            JarvisLogger.warning(
                "Failed to load settings (%s): %s", _SETTINGS_FILE, exc,
            )
        self._original = dict(self._settings)

    def save(self) -> None:
        os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, indent=2)
        self._original = dict(self._settings)
        self._dirty = False
        JarvisLogger.info("Settings saved to %s", _SETTINGS_FILE)
        self._apply()

    def restore_defaults(self) -> None:
        self._settings = dict(_DEFAULTS)
        self.save()

    # ------------------------------------------------------------------
    # Dirty state
    # ------------------------------------------------------------------

    @property
    def has_unsaved_changes(self) -> bool:
        return self._settings != self._original

    # ------------------------------------------------------------------
    # Get / Set
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def get_all(self) -> dict[str, Any]:
        return dict(self._settings)

    def set(self, key: str, value: Any) -> None:
        self._settings[key] = value

    def set_many(self, **kwargs: Any) -> None:
        self._settings.update(kwargs)

    # ------------------------------------------------------------------
    # Apply to live system
    # ------------------------------------------------------------------

    def apply(self) -> None:
        self._apply()

    def _apply(self) -> None:
        if self.on_settings_applied is not None:
            self.on_settings_applied(dict(self._settings))

    # ------------------------------------------------------------------
    # Dynamic data from services
    # ------------------------------------------------------------------

    def get_available_providers(self) -> list[ProviderInfo]:
        try:
            router = self.registry.get("ai_router")
        except KeyError:
            return []
        results: list[ProviderInfo] = []
        for name, provider in router.providers.items():
            try:
                provider.generate("test")
                status = "available"
            except Exception:
                status = "stub"
            results.append(ProviderInfo(name=name, status=status))
        return sorted(results, key=lambda p: p.name)

    def get_version(self) -> str:
        return getattr(Config, "VERSION", "unknown")

    def get_log_levels(self) -> list[str]:
        return ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def get_theme_modes(self) -> list[str]:
        return ["dark", "light", "system"]

    def get_whisper_models(self) -> list[str]:
        return ["tiny", "base", "small", "medium", "large"]
