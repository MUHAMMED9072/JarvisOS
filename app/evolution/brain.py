from .scanner import ProjectScanner
from .planner import EvolutionPlanner
from .generator import CodeGenerator
from .reviewer import PatchReviewer
from .validator import PatchValidator
from .analyzer import Analyzer
from .autofix import AutoFixer
from .sandbox import Sandbox
from .installer import Installer
from .git_manager import GitManager
from .rollback import RollbackManager
from .version import VersionManager
from .tester import TestRunner
from .benchmark import Benchmark

class EvolutionBrain:

    TASKS={
        "1":("Improve dynamic skill discovery.","app/skills/loader.py"),
        "2":("Improve semantic search.","app/memory/search.py"),
        "3":("Improve retry logic.","app/ai/router.py"),
        "4":("Improve sandbox safety.","app/evolution/sandbox.py")
    }

    def evolve(self):
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

        RollbackManager().create_backup(target, choice)

        patch=CodeGenerator().generate_task(task,target)
        PatchReviewer().review(patch,target)

        for _ in range(3):
            AutoFixer().fix()

        ok,report=PatchValidator().validate(patch)

        with open(patch, "r", encoding="utf-8") as f:
            Sandbox().run(f.read())

        TestRunner().run()
        Installer().install()
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

        return ok
