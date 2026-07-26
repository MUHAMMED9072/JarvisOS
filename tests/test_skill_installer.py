# tests/test_skill_installer.py

import sys
import textwrap
from pathlib import Path

import pytest

from app.generator.installer import SkillInstaller
from app.skills.base import Skill
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


class TestSkillInstallerInstall:
    """Integration tests for ``SkillInstaller.install()`` against the real public API."""

    def test_install_full_workflow(self, module_path):
        """A valid skill module is imported, discovered, registered, and its intent returned."""
        _write_module(
            module_path,
            "greet_skill",
            """
            from app.skills.base import Skill

            class GreetSkill(Skill):
                name = "Greet"
                intent = "greet"
                description = "Greets the user"

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        manager = SkillManager()

        intents = installer.install("greet_skill", manager)

        # Returned intent list reflects the registered skill.
        assert intents == ["greet"]

        # The skill is actually stored on the manager under its intent.
        assert "greet" in manager.skills
        assert isinstance(manager.skills["greet"], Skill)
        assert isinstance(manager.skills["greet"], GreetSkill := __import__(
            "greet_skill", fromlist=["GreetSkill"]
        ).GreetSkill)
        assert manager.skills["greet"].name == "Greet"
        assert manager.skills["greet"].intent == "greet"

    def test_install_discovers_all_skill_subclasses(self, module_path):
        """Every concrete ``Skill`` subclass in a module is registered."""
        _write_module(
            module_path,
            "multi_skills",
            """
            from app.skills.base import Skill

            class FirstSkill(Skill):
                name = "First"
                intent = "first"

                def run(self, request):
                    pass

            class SecondSkill(Skill):
                name = "Second"
                intent = "second"

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        manager = SkillManager()

        intents = installer.install("multi_skills", manager)

        assert sorted(intents) == ["first", "second"]
        assert set(manager.skills) == {"first", "second"}
        assert manager.skills["first"].name == "First"
        assert manager.skills["second"].name == "Second"

    def test_install_invalid_module_returns_empty(self):
        """A non-existent module name yields no registrations and no exception."""
        installer = SkillInstaller()
        manager = SkillManager()

        intents = installer.install("definitely_not_a_real_module_xyz", manager)

        assert intents == []
        assert manager.skills == {}

    def test_install_module_without_skill_subclasses(self, module_path):
        """A module lacking ``Skill`` subclasses yields no registrations."""
        _write_module(
            module_path,
            "no_skills",
            """
            SOME_CONSTANT = 42

            def helper():
                return "not a skill"

            class RegularClass:
                pass
            """,
        )

        installer = SkillInstaller()
        manager = SkillManager()

        intents = installer.install("no_skills", manager)

        assert intents == []
        assert manager.skills == {}

    def test_install_skips_skill_on_registration_failure(self, module_path):
        """A skill whose registration raises is caught and skipped."""
        # ``intent == ""`` causes ``SkillManager.register`` to raise ``ValueError``.
        _write_module(
            module_path,
            "broken_skill",
            """
            from app.skills.base import Skill

            class BrokenSkill(Skill):
                name = "Broken"
                intent = ""

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        manager = SkillManager()

        intents = installer.install("broken_skill", manager)

        # The broken skill is not registered and its (empty) intent is not returned.
        assert intents == []
        assert manager.skills == {}

    def test_install_mixed_success_and_failure(self, module_path):
        """Valid skills in a module are registered even when other skills fail."""
        _write_module(
            module_path,
            "mixed_skills",
            """
            from app.skills.base import Skill

            class GoodSkill(Skill):
                name = "Good"
                intent = "good"

                def run(self, request):
                    pass

            class BadSkill(Skill):
                name = "Bad"
                intent = ""

                def run(self, request):
                    pass
            """,
        )

        installer = SkillInstaller()
        manager = SkillManager()

        intents = installer.install("mixed_skills", manager)

        assert intents == ["good"]
        assert set(manager.skills) == {"good"}

    def test_install_injects_registry_services(self, module_path):
        """A non-None registry is forwarded to ``skill.setup()``."""
        _write_module(
            module_path,
            "registry_skill",
            """
            from app.skills.base import Skill

            class RegistrySkill(Skill):
                name = "Registry"
                intent = "registry_test"

                def run(self, request):
                    pass
            """,
        )

        class FakeRegistry:
            def __init__(self):
                self.services = {
                    "memory": object(),
                    "event_bus": object(),
                    "skill_manager": object(),
                }

            def get(self, key):
                return self.services[key]

            def exists(self, key):
                return key in self.services

        registry = FakeRegistry()
        installer = SkillInstaller()
        manager = SkillManager()

        intents = installer.install("registry_skill", manager, registry=registry)

        assert intents == ["registry_test"]
        skill = manager.skills["registry_test"]
        assert skill.memory is registry.services["memory"]
        assert skill.event_bus is registry.services["event_bus"]
        assert skill.skill_manager is registry.services["skill_manager"]
