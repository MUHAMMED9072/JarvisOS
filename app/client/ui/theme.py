from __future__ import annotations

import platform
from enum import Enum
from typing import Optional

import customtkinter as ctk

from app.client.events import EventDispatcher


class ThemeMode(str, Enum):
    DARK = "Dark"
    LIGHT = "Light"
    SYSTEM = "System"


class ThemeManager:
    def __init__(self, events: Optional[EventDispatcher] = None):
        self._events = events or EventDispatcher()
        self._mode = ThemeMode.SYSTEM
        self._colors: dict[str, str] = {}
        self._load_defaults()

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @mode.setter
    def mode(self, value: ThemeMode) -> None:
        self._mode = value
        self._apply()
        self._events.publish("theme.changed", mode=value.value)

    def _load_defaults(self) -> None:
        self._colors = {
            "bg_primary": "#1a1a2e",
            "bg_secondary": "#16213e",
            "bg_tertiary": "#0f3460",
            "text_primary": "#e0e0e0",
            "text_secondary": "#a0a0a0",
            "accent": "#00d4ff",
            "success": "#00e676",
            "warning": "#ffd740",
            "error": "#ff5252",
            "sidebar_bg": "#1a1a2e",
            "sidebar_hover": "#16213e",
            "sidebar_active": "#0f3460",
            "toolbar_bg": "#16213e",
            "status_bar_bg": "#0d1b2a",
            "card_bg": "#16213e",
            "card_border": "#0f3460",
            "input_bg": "#0d1b2a",
            "input_fg": "#e0e0e0",
            "overlay_bg": "rgba(0, 0, 0, 0.6)",
        }

    @property
    def colors(self) -> dict[str, str]:
        return dict(self._colors)

    def get(self, key: str, default: str = "") -> str:
        return self._colors.get(key, default)

    def _apply(self) -> None:
        mode_map = {
            ThemeMode.DARK: "Dark",
            ThemeMode.LIGHT: "Light",
            ThemeMode.SYSTEM: "System",
        }
        ctk.set_appearance_mode(mode_map[self._mode])

    def toggle(self) -> None:
        if self._mode == ThemeMode.DARK:
            self.mode = ThemeMode.LIGHT
        elif self._mode == ThemeMode.LIGHT:
            self.mode = ThemeMode.SYSTEM
        else:
            self.mode = ThemeMode.DARK

    def set_dark(self) -> None:
        self.mode = ThemeMode.DARK

    def set_light(self) -> None:
        self.mode = ThemeMode.LIGHT

    def set_system(self) -> None:
        self.mode = ThemeMode.SYSTEM

    @staticmethod
    def is_dark_mode() -> bool:
        current = ctk.get_appearance_mode()
        return current == "Dark"

    @staticmethod
    def is_light_mode() -> bool:
        current = ctk.get_appearance_mode()
        return current == "Light"
