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
        pipeline_success = False

        def _execute_pipeline():
            nonlocal pipeline_success

            Analyzer().analyze()
            RollbackManager().create_backup("app", "data/app_backup")

            ProjectScanner().scan()
            EvolutionPlanner().create_plan()

            print("="*50)
            print("JARVIS EVOLUTION TASKS")
            print("="*50)
            for k,v in self.TASKS.items():
                print(f"{k}. {v[1]}")

            choice=input("Choose task: ").strip()
            task,target=self.TASKS.get(choice,self.TASKS["1"])

            patch=CodeGenerator().generate_task(task,target)
            review_result=PatchReviewer().review(patch,target)

            for _ in range(3):
                if not review_result.errors and not review_result.warnings:
                    break
                AutoFixer().fix()
                review_result=PatchReviewer().review(patch,target)

            if review_result.errors or review_result.warnings:
                print("[BLOCKED] Patch failed review.")
                print("See data/review_report.txt")
                RollbackManager().restore("data/app_backup", "app")
                pipeline_success = False
                return

            ok,report=PatchValidator().validate(patch, review=review_result)

            print("="*50)
            for line in report:
                print(line)
            print("="*50)

            if not ok:
                print("[BLOCKED] Patch failed validation.")
                print("See data/validation_report.txt")
                RollbackManager().restore("data/app_backup", "app")
                pipeline_success = False
                return

            sandbox_result = Sandbox().run(review_result.clean_code)
            
            if not sandbox_result.success:
                print("[BLOCKED] Sandbox execution failed.")
                RollbackManager().restore("data/app_backup", "app")
                pipeline_success = False
                return

            test_result = TestRunner().run()
            if not test_result.success:
                print("[BLOCKED] Tests failed.")
                RollbackManager().restore("data/app_backup", "app")
                pipeline_success = False
                return

            Installer().install()
            GitManager().add_all()
            GitManager().commit(task)
            VersionManager().bump_patch()

            print("[READY] Patch passed validation and was installed.")
            pipeline_success = True

        Benchmark().run("evolution_pipeline", _execute_pipeline)
        return pipeline_success
