from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Config


class TestConfig:
    # ------------------------------------------------------------------
    # Default values
    # ------------------------------------------------------------------

    def test_app_name(self):
        assert Config.APP_NAME == "JARVIS OS"

    def test_version_format(self):
        assert Config.VERSION == "0.4.0-alpha"

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def test_root_is_absolute(self):
        assert isinstance(Config.ROOT, Path)
        assert Config.ROOT.is_absolute()

    def test_root_points_to_project_root(self):
        assert (Config.ROOT / "app").is_dir()
        assert (Config.ROOT / "tests").is_dir()

    def test_app_dir(self):
        assert Config.APP_DIR == Config.ROOT / "app"

    def test_data_dir(self):
        assert Config.DATA_DIR == Config.ROOT / "data"

    def test_log_dir(self):
        assert Config.LOG_DIR == Config.ROOT / "logs"

    def test_plugin_dir(self):
        assert Config.PLUGIN_DIR == Config.ROOT / "app" / "skills"

    def test_memory_dir(self):
        assert Config.MEMORY_DIR == Config.ROOT / "memory"

    def test_cache_dir(self):
        assert Config.CACHE_DIR == Config.ROOT / "cache"

    # ------------------------------------------------------------------
    # AI defaults
    # ------------------------------------------------------------------

    def test_default_brain(self):
        assert Config.DEFAULT_BRAIN == "fast"

    def test_reasoning_brain(self):
        assert Config.REASONING_BRAIN == "reasoning"

    def test_coding_brain(self):
        assert Config.CODING_BRAIN == "coding"

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    def test_voice_is_voice_config(self):
        from app.voice.config import VoiceConfig
        assert isinstance(Config.VOICE, VoiceConfig)

    def test_voice_default_language(self):
        assert Config.DEFAULT_LANGUAGE == "en"

    def test_wake_word(self):
        assert Config.WAKE_WORD == "jarvis"

    # ------------------------------------------------------------------
    # Logging defaults
    # ------------------------------------------------------------------

    def test_log_level(self):
        assert Config.LOG_LEVEL == "INFO"

    def test_log_file_resolved(self):
        assert Config.LOG_FILE == Config.LOG_DIR / "jarvis.log"

    # ------------------------------------------------------------------
    # Applications
    # ------------------------------------------------------------------

    def test_applications_contains_expected_keys(self):
        expected = {"chrome", "notepad", "calculator", "paint", "cmd", "explorer"}
        assert expected.issubset(Config.APPLICATIONS.keys())

    def test_applications_values_are_strings(self):
        for path in Config.APPLICATIONS.values():
            assert isinstance(path, str)
            assert len(path) > 0

    # ------------------------------------------------------------------
    # Immutability (documenting that Config is a static class)
    # ------------------------------------------------------------------

    def test_can_override_attr_at_runtime(self):
        """Config attributes are mutable at runtime — this is by design
        and used by tests to override LOG_LEVEL etc."""
        saved = Config.LOG_LEVEL
        Config.LOG_LEVEL = "DEBUG"
        assert Config.LOG_LEVEL == "DEBUG"
        Config.LOG_LEVEL = saved  # restore
