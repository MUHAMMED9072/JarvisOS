"""Tests for CommandRouter (session-control short-circuit)."""

from __future__ import annotations

import pytest

from app.skills.result import SkillResult
from app.voice.commands import CommandRouter
from app.voice.config import VoiceConfig


class TestCommandRouter:
    def test_empty_by_default(self):
        router = CommandRouter(VoiceConfig())
        assert router.commands == ()
        assert router.is_command("stop") is False
        assert router.is_command("anything") is False

    def test_match_literal(self):
        router = CommandRouter(VoiceConfig(commands=("stop", "cancel")))
        assert router.is_command("stop") is True
        assert router.is_command("cancel") is True
        assert router.is_command("open chrome") is False

    def test_match_is_case_insensitive(self):
        router = CommandRouter(VoiceConfig(commands=("stop",)))
        assert router.is_command("STOP") is True
        assert router.is_command("Stop") is True

    def test_match_strips_whitespace(self):
        router = CommandRouter(VoiceConfig(commands=("stop",)))
        assert router.is_command("  stop  ") is True

    def test_handle_non_command_returns_none(self):
        router = CommandRouter(VoiceConfig(commands=("stop",)))
        assert router.handle("open chrome") is None

    def test_handle_matched_command_returns_skill_result(self):
        router = CommandRouter(VoiceConfig(commands=("stop",)))
        result = router.handle("stop")
        assert isinstance(result, SkillResult)
        assert result.success is True
        assert "stop" in result.message.lower()
        assert result.data.get("command") == "stop"

    def test_handle_empty_text(self):
        router = CommandRouter(VoiceConfig(commands=("stop",)))
        assert router.is_command("") is False
        assert router.handle("") is None
        assert router.handle(None) is None  # type: ignore[arg-type]
