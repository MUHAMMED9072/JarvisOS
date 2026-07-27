"""
JARVIS Evolution Engine - Updater
"""

from __future__ import annotations

from dataclasses import dataclass

from .analyzer import Analyzer
from .planner import EvolutionPlanner
from .generator import CodeGenerator
from .tester import TestRunner
from .benchmark import Benchmark
from .git_manager import GitManager
from .rollback import RollbackManager
from .version import VersionManager


@dataclass
class UpdateReport:
    success: bool
    message: str


class Updater:
    """Coordinates the self-upgrade workflow."""

    def __init__(self, registry=None) -> None:
        self.analyzer = Analyzer()
        self.planner = EvolutionPlanner(registry) if registry else None
        self.generator = CodeGenerator(registry) if registry else None
        self.tester = TestRunner()
        self.benchmark = Benchmark()
        self.git = GitManager()
        self.rollback = RollbackManager()
        self.version = VersionManager()

    def status(self) -> dict:
        analysis = self.analyzer.analyze()
        return {
            "version": self.version.info(),
            "files": analysis.files,
            "lines": analysis.lines,
            "hash": analysis.sha256,
        }

    def upgrade_requested(self) -> UpdateReport:
        return UpdateReport(
            success=True,
            message="Upgrade pipeline initialized. Planner, generator, tester, benchmark and git manager are ready."
        )


if __name__ == "__main__":
    updater = Updater()
    print(updater.status())
