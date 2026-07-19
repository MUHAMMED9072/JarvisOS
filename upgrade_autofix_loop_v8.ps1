# ==========================================
# JARVIS Auto Fix Loop v8
# ==========================================

function Write-PyFile($Path,$Content){
 $Dir=Split-Path $Path
 New-Item -ItemType Directory -Force -Path $Dir | Out-Null
 Set-Content -Path $Path -Value $Content -Encoding UTF8
 Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\evolution\autofix.py" @'
from pathlib import Path
from app.ai.providers.ollama import OllamaProvider

class AutoFixer:

    def fix(self,
            review_file="data/review_report.txt",
            patch_file="data/generated_patch.py"):

        review = Path(review_file).read_text(encoding="utf-8")
        patch = Path(patch_file).read_text(encoding="utf-8")

        if "WARNING" not in review and "ERROR" not in review:
            print("[AutoFix] Patch already passed review.")
            return patch_file

        prompt=f"""
You are fixing a generated Python patch.

Review:
{review}

Patch:
{patch}

Rules:
- Fix every warning/error.
- Keep the same filename and public API.
- Return ONLY valid Python code.
"""

        print("[AutoFix] Asking AI to repair patch...")
        fixed = OllamaProvider().generate(prompt)
        Path(patch_file).write_text(fixed, encoding="utf-8")
        return patch_file
'@

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner
from .planner import EvolutionPlanner
from .generator import CodeGenerator
from .reviewer import PatchReviewer
from .autofix import AutoFixer

class EvolutionBrain:

    TASKS={
        "1":("Improve dynamic skill discovery.","app/skills/loader.py"),
        "2":("Improve semantic search.","app/memory/search.py"),
        "3":("Improve retry logic.","app/ai/router.py"),
        "4":("Improve sandbox safety.","app/evolution/sandbox.py")
    }

    def evolve(self):
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
        review=PatchReviewer().review(patch,target)

        print(f"[Review] Syntax OK: {review['syntax']}")

        if review["errors"] or review["warnings"]:
            AutoFixer().fix()

        print("[DONE] Evolution cycle complete.")
'@

Write-Host ""
Write-Host "Auto Fix Loop Installed" -ForegroundColor Cyan
