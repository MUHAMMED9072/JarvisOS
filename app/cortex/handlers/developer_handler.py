from __future__ import annotations

from app.cortex.handlers import BaseHandler
from app.skills.result import SkillResult


class DeveloperHandler(BaseHandler):
    """Thin wrapper around Evolution Engine services for code operations."""

    def generate_code(self, spec: str) -> SkillResult:
        try:
            generator = self.registry.get("generator")
        except KeyError:
            return SkillResult.fail("Generator service not available.")
        return generator.generate_task(spec, "data/generated_patch.py")  # type: ignore[union-attr]

    def analyze_code(self, filepath: str) -> SkillResult:
        try:
            analyzer = self.registry.get("analyzer")
        except KeyError:
            return SkillResult.fail("Analyzer service not available.")
        return analyzer.analyze(filepath)  # type: ignore[union-attr]

    def run_tests(self, path: str) -> SkillResult:
        try:
            tester = self.registry.get("tester")
        except KeyError:
            return SkillResult.fail("TestRunner service not available.")
        return tester.run(path)  # type: ignore[union-attr]
