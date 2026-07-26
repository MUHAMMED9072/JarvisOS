# tests/test_skill_lifecycle.py

import sys
import textwrap
from pathlib import Path

import pytest

from app.generator.installer import SkillInstaller
from app.skills.base import Skill
from app.skills.loader import SkillLoader
from app.skills.manager import SkillManager


def _write_module(directory: Path, name: str, source: str) -> Path:
    """Write a Python module file inside ``directory`` and return the path."""
    module_file = directory / f"{name}.py"
    module_file.write_text(textwrap.dedent(source).lstrip())
    return module_file


@pytest.fixture
def module_path(tmp_path):
    """
    Make ``tmp_path`` importable for the duration of a test.

    Removes anything that was imported from this directory afterwards so
    subsequent tests start from a clean ``sys.modules`` cache.
    """
    sys.path.insert(0, str(tmp_path))
    yield tmp_path

    stale = [
        name
        for name, mod in list(sys.modules.items())
        if getattr(mod, "__file__", None) is not None
        and str(tmp_path) in str(mod.__file__)
    ]
    for name in stale:
        del sys.modules[name]

    while str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))


class FakeRegistry:
    """Minimal stand-in for a real service registry."""

    def __init__(self):
        self.services = {
            "memory": object(),
            "event_bus": object(),
            "skill_manager": object(),
        }
        self.get_calls: list[str] = []

    def get(self, key: str):
        self.get_calls.append(key)
        return self.services[key]

    def exists(self, key: str) -> bool:
        return key in self.services


class TestSkillLifecycle:

    def test_install_reload_uninstall(self, module_path):
        """Full lifecycle: install, reload, uninstall, and verify removal."""
        _write_module(
            module_path,
            "lifecycle_skill",
            """
            from app.skills.base import Skill

            class LifecycleSkill(Skill):
                name = "Lifecycle"
                intent = "lifecycle_test"

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        loader = SkillLoader()
        manager = SkillManager()

        # Install.
        install_intents = installer.install("lifecycle_skill", manager)
        assert install_intents == ["lifecycle_test"]
        assert "lifecycle_test" in manager.skills
        first_instance = manager.skills["lifecycle_test"]

        # Reload.
        reload_intents = loader.reload("lifecycle_test", manager)
        assert reload_intents == ["lifecycle_test"]
        assert "lifecycle_test" in manager.skills
        reloaded_instance = manager.skills["lifecycle_test"]
        assert reloaded_instance is not first_instance
        assert isinstance(reloaded_instance, Skill)

        # Uninstall.
        assert manager.unregister("lifecycle_test") is True
        assert "lifecycle_test" not in manager.skills
        assert manager.get("lifecycle_test") is manager.fallback

    def test_reload_unknown_intent_returns_empty(self, module_path):
        """Reloading an intent that was never registered returns ``[]``."""
        _write_module(
            module_path,
            "known_skill",
            """
            from app.skills.base import Skill

            class KnownSkill(Skill):
                name = "Known"
                intent = "known_intent"

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        loader = SkillLoader()
        manager = SkillManager()

        installer.install("known_skill", manager)

        # Should not raise.
        result = loader.reload("not_a_real_intent", manager)
        assert result == []
        # The known skill is unaffected.
        assert "known_intent" in manager.skills

    def test_unregister_unknown_intent_returns_false(self, module_path):
        """Unregistering a missing intent returns ``False`` and does not raise."""
        _write_module(
            module_path,
            "some_skill",
            """
            from app.skills.base import Skill

            class SomeSkill(Skill):
                name = "Some"
                intent = "some_intent"

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        manager = SkillManager()

        installer.install("some_skill", manager)

        # Unknown intent.
        assert manager.unregister("never_registered") is False
        # Known intent is untouched.
        assert "some_intent" in manager.skills
        # Empty intent is also rejected.
        assert manager.unregister("") is False
        assert "some_intent" in manager.skills

    def test_install_after_uninstall(self, module_path):
        """A skill can be re-installed after it has been uninstalled."""
        _write_module(
            module_path,
            "reinstall_skill",
            """
            from app.skills.base import Skill

            class ReinstallSkill(Skill):
                name = "Reinstall"
                intent = "reinstall_test"

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        manager = SkillManager()

        # First install.
        assert installer.install("reinstall_skill", manager) == ["reinstall_test"]
        first = manager.skills["reinstall_test"]

        # Uninstall.
        assert manager.unregister("reinstall_test") is True
        assert "reinstall_test" not in manager.skills

        # Re-install.
        assert installer.install("reinstall_skill", manager) == ["reinstall_test"]
        assert "reinstall_test" in manager.skills
        second = manager.skills["reinstall_test"]
        # Re-registration produces a fresh instance, not a cached one.
        assert second is not first
        assert isinstance(second, Skill)

    def test_reload_does_not_affect_other_skills(self, module_path):
        """Reloading one skill leaves every other registered skill untouched."""
        _write_module(
            module_path,
            "primary_skill",
            """
            from app.skills.base import Skill

            class PrimarySkill(Skill):
                name = "Primary"
                intent = "primary_test"

                def run(self, request):
                    pass
            """,
        )
        _write_module(
            module_path,
            "sibling_skill",
            """
            from app.skills.base import Skill

            class SiblingSkill(Skill):
                name = "Sibling"
                intent = "sibling_test"

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        loader = SkillLoader()
        manager = SkillManager()

        installer.install("primary_skill", manager)
        installer.install("sibling_skill", manager)

        sibling_before = manager.skills["sibling_test"]
        primary_before = manager.skills["primary_test"]

        # Reload only the primary skill.
        reload_intents = loader.reload("primary_test", manager)
        assert reload_intents == ["primary_test"]

        # Primary was replaced.
        assert "primary_test" in manager.skills
        primary_after = manager.skills["primary_test"]
        assert primary_after is not primary_before
        assert isinstance(primary_after, Skill)

        # Sibling is unchanged.
        assert "sibling_test" in manager.skills
        assert manager.skills["sibling_test"] is sibling_before

    def test_setup_is_preserved_after_reload(self, module_path):
        """``setup(registry)`` is re-invoked on every reload."""
        _write_module(
            module_path,
            "di_skill",
            """
            from app.skills.base import Skill

            class DiSkill(Skill):
                name = "DI"
                intent = "di_test"

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        loader = SkillLoader()
        manager = SkillManager()
        registry = FakeRegistry()

        installer.install("di_skill", manager, registry=registry)
        first = manager.skills["di_test"]
        assert first.memory is registry.services["memory"]
        assert first.event_bus is registry.services["event_bus"]
        assert first.skill_manager is registry.services["skill_manager"]

        # The skill instance starts with injected services.
        assert "memory" in registry.get_calls
        assert "event_bus" in registry.get_calls
        assert "skill_manager" in registry.get_calls

        calls_before = len(registry.get_calls)

        # Reload and confirm DI is re-applied to the new instance.
        assert loader.reload("di_test", manager, registry=registry) == ["di_test"]
        second = manager.skills["di_test"]
        assert second is not first

        assert second.memory is registry.services["memory"]
        assert second.event_bus is registry.services["event_bus"]
        assert second.skill_manager is registry.services["skill_manager"]

        # ``setup`` is invoked again on the reloaded instance.
        assert len(registry.get_calls) > calls_before
        