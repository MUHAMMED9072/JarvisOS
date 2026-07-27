"""Tests for ThemeManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.client.events import EventDispatcher
from app.client.ui.theme import ThemeManager, ThemeMode


class TestThemeManagerInit:
    def test_default_mode(self):
        tm = ThemeManager()
        assert tm.mode == ThemeMode.SYSTEM

    def test_custom_events(self):
        events = EventDispatcher()
        tm = ThemeManager(events=events)
        assert tm._events is events

    def test_default_colors_loaded(self):
        tm = ThemeManager()
        assert "bg_primary" in tm.colors
        assert "accent" in tm.colors
        assert "sidebar_bg" in tm.colors


class TestThemeManagerMode:
    def test_set_dark(self):
        tm = ThemeManager()
        with patch("customtkinter.set_appearance_mode") as mock_set:
            tm.set_dark()
            assert tm.mode == ThemeMode.DARK
            mock_set.assert_called_once_with("Dark")

    def test_set_light(self):
        tm = ThemeManager()
        with patch("customtkinter.set_appearance_mode") as mock_set:
            tm.set_light()
            assert tm.mode == ThemeMode.LIGHT
            mock_set.assert_called_once_with("Light")

    def test_set_system(self):
        tm = ThemeManager()
        with patch("customtkinter.set_appearance_mode") as mock_set:
            tm.set_system()
            assert tm.mode == ThemeMode.SYSTEM
            mock_set.assert_called_once_with("System")

    def test_toggle_cycles_modes(self):
        tm = ThemeManager()
        with patch("customtkinter.set_appearance_mode"):
            tm.mode = ThemeMode.DARK
            tm.toggle()
            assert tm.mode == ThemeMode.LIGHT
            tm.toggle()
            assert tm.mode == ThemeMode.SYSTEM
            tm.toggle()
            assert tm.mode == ThemeMode.DARK


class TestThemeManagerEvents:
    def test_mode_change_emits_event(self):
        events = EventDispatcher()
        tm = ThemeManager(events=events)
        received = []

        def handler(event, **data):
            received.append(data.get("mode"))

        events.subscribe("theme.changed", handler)
        with patch("customtkinter.set_appearance_mode"):
            tm.mode = ThemeMode.DARK
        assert "Dark" in received

    def test_toggle_emits_event(self):
        events = EventDispatcher()
        tm = ThemeManager(events=events)
        received = []

        def handler(event, **data):
            received.append(data.get("mode"))

        events.subscribe("theme.changed", handler)
        with patch("customtkinter.set_appearance_mode"):
            tm.set_dark()
            tm.toggle()
        assert len(received) == 2


class TestThemeManagerColors:
    def test_get_existing(self):
        tm = ThemeManager()
        assert tm.get("bg_primary") == "#1a1a2e"

    def test_get_missing_returns_default(self):
        tm = ThemeManager()
        assert tm.get("nonexistent", "fallback") == "fallback"

    def test_get_missing_no_default(self):
        tm = ThemeManager()
        assert tm.get("nonexistent") == ""

    def test_colors_returns_copy(self):
        tm = ThemeManager()
        colors = tm.colors
        colors["bg_primary"] = "changed"
        assert tm.get("bg_primary") == "#1a1a2e"


class TestThemeManagerStatic:
    def test_is_dark_mode(self):
        with patch("customtkinter.get_appearance_mode", return_value="Dark"):
            assert ThemeManager.is_dark_mode() is True
            assert ThemeManager.is_light_mode() is False

    def test_is_light_mode(self):
        with patch("customtkinter.get_appearance_mode", return_value="Light"):
            assert ThemeManager.is_light_mode() is True
            assert ThemeManager.is_dark_mode() is False


class TestThemeModeEnum:
    def test_values(self):
        assert ThemeMode.DARK.value == "Dark"
        assert ThemeMode.LIGHT.value == "Light"
        assert ThemeMode.SYSTEM.value == "System"

    def test_unique(self):
        values = [m.value for m in ThemeMode]
        assert len(values) == len(set(values))
