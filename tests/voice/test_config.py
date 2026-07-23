"""Tests for VoiceConfig dataclass."""

from __future__ import annotations

from app.voice.config import VoiceConfig


class TestVoiceConfig:
    def test_default_disabled(self):
        config = VoiceConfig()
        assert config.enabled is False

    def test_default_sample_rate(self):
        config = VoiceConfig()
        assert config.sample_rate == 16000

    def test_default_wake_word(self):
        config = VoiceConfig()
        assert config.wake_word == "jarvis"
        assert config.wake_word_enabled is False

    def test_default_vad_disabled(self):
        config = VoiceConfig()
        assert config.vad_enabled is False
        assert config.vad_energy_threshold > 0

    def test_default_commands_empty(self):
        config = VoiceConfig()
        assert config.commands == ()

    def test_default_speaker_disabled(self):
        config = VoiceConfig()
        assert config.speaker_enabled is False

    def test_slots(self):
        config = VoiceConfig()
        with __import__("pytest").raises(AttributeError):
            config.not_a_field = 1  # type: ignore[attr-defined]

    def test_can_override(self):
        config = VoiceConfig(enabled=True, wake_word="hey jarvis")
        assert config.enabled is True
        assert config.wake_word == "hey jarvis"

    def test_core_config_voice_default(self):
        """The core Config.VOICE singleton must be disabled by default."""
        from app.core.config import Config

        assert isinstance(Config.VOICE, VoiceConfig)
        assert Config.VOICE.enabled is False
        # Back-compat constants
        assert Config.WAKE_WORD == "jarvis"
        assert Config.DEFAULT_LANGUAGE == "en"
