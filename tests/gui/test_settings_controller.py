from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.gui.controllers.settings_controller import (
    ProviderInfo,
    SettingsController,
    _DEFAULTS,
    _SETTINGS_FILE,
)


class TestSettingsController:
    @pytest.fixture
    def ai_router(self):
        router = MagicMock()
        router.providers = {}
        return router

    @pytest.fixture
    def registry(self, ai_router):
        r = MagicMock()
        r.get.side_effect = lambda name: {
            "ai_router": ai_router,
        }[name]
        return r

    @pytest.fixture
    def controller(self, registry):
        return SettingsController(registry)

    # ------------------------------------------------------------------
    # Default values
    # ------------------------------------------------------------------

    def test_default_ai_provider(self, controller):
        assert controller.get("ai_provider") == "ollama"

    def test_default_voice_enabled(self, controller):
        assert controller.get("voice_enabled") is False

    def test_default_theme_mode(self, controller):
        assert controller.get("theme_mode") == "dark"

    def test_default_log_level(self, controller):
        assert controller.get("log_level") == "INFO"

    def test_get_all_returns_dict(self, controller):
        all_s = controller.get_all()
        assert isinstance(all_s, dict)
        assert "ai_provider" in all_s

    def test_get_with_default(self, controller):
        assert controller.get("nonexistent", "fallback") == "fallback"

    def test_get_nonexistent(self, controller):
        assert controller.get("nonexistent") is None

    # ------------------------------------------------------------------
    # Set / get
    # ------------------------------------------------------------------

    def test_set_updates_value(self, controller):
        controller.set("ai_provider", "deepseek")
        assert controller.get("ai_provider") == "deepseek"

    def test_set_many(self, controller):
        controller.set_many(ai_provider="deepseek", theme_mode="light")
        assert controller.get("ai_provider") == "deepseek"
        assert controller.get("theme_mode") == "light"

    # ------------------------------------------------------------------
    # Dirty state
    # ------------------------------------------------------------------

    def test_has_unsaved_changes_false_initially(self, controller):
        assert controller.has_unsaved_changes is False

    def test_has_unsaved_changes_after_set(self, controller):
        controller.set("ai_provider", "deepseek")
        assert controller.has_unsaved_changes is True

    def test_has_unsaved_changes_false_after_save(self, controller):
        controller.set("ai_provider", "deepseek")
        controller.save()
        assert controller.has_unsaved_changes is False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def test_save_writes_json(self, controller):
        controller.set("ai_provider", "custom")
        controller.save()
        assert os.path.isfile(_SETTINGS_FILE)
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["ai_provider"] == "custom"
        # Cleanup
        try:
            os.unlink(_SETTINGS_FILE)
        except OSError:
            pass
        try:
            os.rmdir(os.path.dirname(_SETTINGS_FILE))
        except OSError:
            pass

    def test_load_reads_saved_data(self, controller):
        controller.set("ai_provider", "custom")
        controller.save()
        new_ctrl = SettingsController(controller.registry)
        assert new_ctrl.get("ai_provider") == "custom"
        try:
            os.unlink(_SETTINGS_FILE)
        except OSError:
            pass
        try:
            os.rmdir(os.path.dirname(_SETTINGS_FILE))
        except OSError:
            pass

    def test_load_no_file_uses_defaults(self, registry):
        with patch.object(
            SettingsController, "_SETTINGS_FILE",
            create=True,
            new="/nonexistent/path/settings.json",
        ):
            ctrl = SettingsController(registry)
            assert ctrl.get("ai_provider") == "ollama"

    def test_load_bad_json_uses_defaults(self, controller):
        os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write("not json")
        ctrl = SettingsController(controller.registry)
        assert ctrl.get("ai_provider") == "ollama"
        try:
            os.unlink(_SETTINGS_FILE)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Restore defaults
    # ------------------------------------------------------------------

    def test_restore_defaults(self, controller):
        controller.set("ai_provider", "deepseek")
        controller.restore_defaults()
        assert controller.get("ai_provider") == _DEFAULTS["ai_provider"]

    def test_restore_defaults_persists(self, controller):
        controller.set("ai_provider", "deepseek")
        controller.restore_defaults()
        assert os.path.isfile(_SETTINGS_FILE)
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["ai_provider"] == _DEFAULTS["ai_provider"]
        try:
            os.unlink(_SETTINGS_FILE)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Available providers
    # ------------------------------------------------------------------

    def test_get_available_providers_empty(self, controller):
        assert controller.get_available_providers() == []

    def test_get_available_providers_no_router(self, registry):
        registry.get.side_effect = KeyError("no ai_router")
        ctrl = SettingsController(registry)
        assert ctrl.get_available_providers() == []

    def test_get_available_providers_stub(self, ai_router, registry):
        stub = MagicMock()
        stub.generate.side_effect = Exception("not implemented")
        ai_router.providers = {"deepseek": stub}
        ctrl = SettingsController(registry)
        results = ctrl.get_available_providers()
        assert len(results) == 1
        assert results[0].name == "deepseek"
        assert results[0].status == "stub"

    def test_get_available_providers_available(self, ai_router, registry):
        working = MagicMock()
        working.generate.return_value = "ok"
        ai_router.providers = {"ollama": working}
        ctrl = SettingsController(registry)
        results = ctrl.get_available_providers()
        assert len(results) == 1
        assert results[0].status == "available"

    def test_get_available_providers_sorted(self, ai_router, registry):
        a = MagicMock()
        b = MagicMock()
        ai_router.providers = {"zulu": a, "alpha": b}
        ctrl = SettingsController(registry)
        names = [p.name for p in ctrl.get_available_providers()]
        assert names == ["alpha", "zulu"]

    # ------------------------------------------------------------------
    # Info methods
    # ------------------------------------------------------------------

    def test_get_version(self, controller):
        from app.core.config import Config
        assert controller.get_version() == Config.VERSION

    def test_get_log_levels(self, controller):
        assert controller.get_log_levels() == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def test_get_theme_modes(self, controller):
        assert controller.get_theme_modes() == ["dark", "light", "system"]

    def test_get_whisper_models(self, controller):
        assert controller.get_whisper_models() == ["tiny", "base", "small", "medium", "large"]

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def test_apply_calls_callback(self, controller):
        cb = MagicMock()
        controller.on_settings_applied = cb
        controller.apply()
        cb.assert_called_once()

    def test_apply_passes_settings(self, controller):
        cb = MagicMock()
        controller.on_settings_applied = cb
        controller.apply()
        args, _ = cb.call_args
        assert isinstance(args[0], dict)
        assert args[0]["ai_provider"] == "ollama"
