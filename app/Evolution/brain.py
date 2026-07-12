"""
JARVIS Evolution Engine - Brain
"""

from __future__ import annotations

from dataclasses import dataclass

from .analyzer import Analyzer
from .planner import EvolutionPlanner
from .generator import CodeGenerator
from .sandbox import Sandbox
from .tester import TestRunner
from .benchmark import Benchmark
from .git_manager import GitManager
from .rollback import RollbackManager
from .version import VersionManager


@dataclass
class EvolutionResult:
    success: bool
    stage: str
    message: str


class EvolutionBrain:
    """
    Coordinates the complete self-upgrade pipeline.
    AI generation is intentionally left as a provider hook.
    """

    def __init__(self):
        self.analyzer = Analyzer()
        self.planner = EvolutionPlanner()
        self.generator = CodeGenerator()
        self.sandbox = Sandbox()
        self.tester = TestRunner()
        self.benchmark = Benchmark()
        self.git = GitManager()
        self.rollback = RollbackManager()
        self.version = VersionManager()

    def analyze(self):
        return self.analyzer.analyze()

    def plan(self):
        return self.planner.pending()

    def generate(self, output_path: str, source: str):
        return self.generator.generate(output_path, source)

    def sandbox_test(self, source: str):
        return self.sandbox.run(source)

    def project_tests(self):
        return self.tester.run()

    def upgrade(self):
        info = self.analyze()

        return EvolutionResult(
            success=True,
            stage="READY",
            message=(
                f"Evolution pipeline ready. "
                f"Files={info.files}, "
                f"Lines={info.lines}, "
                f"Version={self.version.info()['version']}"
            ),
        )


if __name__ == "__main__":
    brain = EvolutionBrain()
    print(brain.upgrade())
