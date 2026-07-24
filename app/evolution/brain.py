from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Config

from .scanner import ProjectScanner
from .planner import EvolutionPlanner
from .generator import CodeGenerator
from .reviewer import PatchReviewer
from .validator import PatchValidator
from .analyzer import Analyzer
from .autofix import AutoFixer
from .sandbox import Sandbox
from .installer import ApprovalRequest, Installer
from .git_manager import GitManager
from .rollback import RollbackManager
from .version import VersionManager
from .tester import TestRunner
from .benchmark import Benchmark


def _backup_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


class EvolutionBrain:

    TASKS={
        "1":("Improve dynamic skill discovery.","app/skills/loader.py"),
        "2":("Improve semantic search.","app/memory/search.py"),
        "3":("Improve retry logic.","app/ai/router.py"),
        "4":("Improve sandbox safety.","app/evolution/sandbox.py")
    }

    def evolve(self) -> bool:
        Analyzer().analyze()
        ProjectScanner().scan()
        EvolutionPlanner().create_plan()

        print("="*50)
        print("JARVIS EVOLUTION TASKS")
        print("="*50)
        for k,v in self.TASKS.items():
            print(f"{k}. {v[1]}")

        choice=input("Choose task: ").strip()
        task,target=self.TASKS.get(choice,self.TASKS["1"])

        # Create a real backup directory for the target before any install
        # is attempted. Without this the previous call (choice used as a
        # directory path) would crash against any real file target.
        backup_dir = (
            Config.DATA_DIR
            / "evolution"
            / "backups"
            / f"{Path(target).name}-{_backup_timestamp()}"
        )
        backup_result = RollbackManager().create_backup(target, str(backup_dir))
        if not backup_result.success:
            print(f"[BLOCKED] Could not create backup: {backup_result.message}")
            return False

        patch=CodeGenerator().generate_task(task,target)
        PatchReviewer().review(patch,target)

        for _ in range(3):
            AutoFixer().fix()

        ok,report=PatchValidator().validate(patch)

        with open(patch, "r", encoding="utf-8") as f:
            sandbox_result = Sandbox().run(f.read())

        test_result = TestRunner().run()

        request = ApprovalRequest(
            patch_path=patch,
            target_path=target,
            backup_path=str(backup_dir),
            summary={
                "validation_ok": ok,
                "sandbox_success": sandbox_result.success,
                "test_success": test_result.success,
            },
        )

        install_result = Installer().install(request)

        if not install_result.success:
            print(f"[BLOCKED] install: {install_result.message}")
            return False

        GitManager().status()
        VersionManager().bump_patch()
        Benchmark().run(task, TestRunner().run)

        print("="*50)
        for line in report:
            print(line)
        print("="*50)

        if ok:
            print("[READY] Patch passed validation.")
        else:
            print("[BLOCKED] Patch failed validation.")
            print("See data/validation_report.txt")

        return True
