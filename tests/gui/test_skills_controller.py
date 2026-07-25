from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.gui.controllers.skills_controller import (
    SkillInfo,
    SkillsController,
    SkillsStats,
)
from app.skills.base import Skill


class _FakeSkill(Skill):
    name = "Fake Skill"
    intent = "fake"
    description = "A fake skill for testing"
    version = "1.0.0"
    author = "Test"

    def run(self, request):
        from app.skills.result import SkillResult
        return SkillResult.ok()


class _OtherSkill(Skill):
    name = "Other Skill"
    intent = "other"
    description = "Another test skill"
    version = "2.0.0"
    author = "Tester"

    def run(self, request):
        from app.skills.result import SkillResult
        return SkillResult.ok()


class TestSkillsController:
    @pytest.fixture
    def skill_manager(self):
        mgr = MagicMock()
        mgr.all_skills.return_value = [_FakeSkill(), _OtherSkill()]
        mgr.fallback = _FakeSkill()
        mgr.get.side_effect = lambda intent: (
            _FakeSkill() if intent == "fake" else mgr.fallback
        )
        return mgr

    @pytest.fixture
    def registry(self, skill_manager):
        r = MagicMock()
        r.get.side_effect = lambda name: {
            "skill_manager": skill_manager,
        }[name]
        return r

    @pytest.fixture
    def controller(self, registry):
        return SkillsController(registry)

    # ------------------------------------------------------------------
    # get_all_skills
    # ------------------------------------------------------------------

    def test_get_all_skills_returns_list(self, controller):
        skills = controller.get_all_skills()
        assert len(skills) == 2
        assert all(isinstance(s, SkillInfo) for s in skills)

    def test_get_all_skills_contains_expected(self, controller):
        names = [s.name for s in controller.get_all_skills()]
        assert "Fake Skill" in names
        assert "Other Skill" in names

    def test_get_all_skills_default_enabled(self, controller):
        for s in controller.get_all_skills():
            assert s.enabled is True

    # ------------------------------------------------------------------
    # search_skills
    # ------------------------------------------------------------------

    def test_search_skills_empty_query(self, controller):
        assert len(controller.search_skills("")) == 2

    def test_search_skills_whitespace(self, controller):
        assert len(controller.search_skills("   ")) == 2

    def test_search_skills_by_name(self, controller):
        results = controller.search_skills("Fake")
        assert len(results) == 1
        assert results[0].name == "Fake Skill"

    def test_search_skills_by_intent(self, controller):
        results = controller.search_skills("other")
        assert len(results) == 1
        assert results[0].intent == "other"

    def test_search_skills_by_description(self, controller):
        results = controller.search_skills("Another")
        assert len(results) == 1
        assert results[0].name == "Other Skill"

    def test_search_skills_no_match(self, controller):
        assert controller.search_skills("zzzzz") == []

    def test_search_skills_case_insensitive(self, controller):
        results = controller.search_skills("FAKE")
        assert len(results) == 1

    # ------------------------------------------------------------------
    # get_skill_by_intent
    # ------------------------------------------------------------------

    def test_get_skill_by_intent_found(self, controller):
        info = controller.get_skill_by_intent("fake")
        assert info is not None
        assert info.name == "Fake Skill"

    def test_get_skill_by_intent_not_found(self, controller):
        assert controller.get_skill_by_intent("nonexistent") is None

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def test_get_statistics_type(self, controller):
        stats = controller.get_statistics()
        assert isinstance(stats, SkillsStats)

    def test_get_statistics_values(self, controller):
        stats = controller.get_statistics()
        assert stats.total == 2
        assert stats.enabled == 2
        assert stats.disabled == 0

    def test_get_statistics_with_disabled(self, controller):
        controller._disabled.add("fake")
        stats = controller.get_statistics()
        assert stats.total == 2
        assert stats.enabled == 1
        assert stats.disabled == 1

    # ------------------------------------------------------------------
    # toggle_skill
    # ------------------------------------------------------------------

    def test_toggle_skill_disables(self, controller):
        result = controller.toggle_skill("fake")
        assert result is False
        assert controller.is_enabled("fake") is False

    def test_toggle_skill_enables(self, controller):
        controller._disabled.add("fake")
        result = controller.toggle_skill("fake")
        assert result is True
        assert controller.is_enabled("fake") is True

    def test_toggle_skill_updates_info(self, controller):
        controller.toggle_skill("fake")
        info = controller.get_skill_by_intent("fake")
        assert info is not None
        assert info.enabled is False

    # ------------------------------------------------------------------
    # is_enabled
    # ------------------------------------------------------------------

    def test_is_enabled_default(self, controller):
        assert controller.is_enabled("fake") is True

    def test_is_enabled_after_disable(self, controller):
        controller.toggle_skill("fake")
        assert controller.is_enabled("fake") is False

    # ------------------------------------------------------------------
    # reload_all
    # ------------------------------------------------------------------

    @patch("app.gui.controllers.skills_controller.SkillLoader")
    def test_reload_all_calls_loader_load(self, mock_loader_cls, controller):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader

        controller._loader = mock_loader
        controller.reload_all()

        mock_loader.load.assert_called_once_with(
            controller._manager, controller.registry,
        )

    @patch("app.gui.controllers.skills_controller.SkillLoader")
    def test_reload_all_clears_disabled(self, mock_loader_cls, controller):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader

        controller._loader = mock_loader
        controller._disabled.add("fake")
        controller.reload_all()
        assert len(controller._disabled) == 0

    @patch("app.gui.controllers.skills_controller.SkillLoader")
    def test_reload_all_returns_intents(self, mock_loader_cls, controller):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader

        controller._loader = mock_loader
        intents = controller.reload_all()
        assert isinstance(intents, list)
        assert len(intents) == 2
