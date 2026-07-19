# ==========================================
# JARVIS Evolution Validation v9
# Adds:
#  - Syntax validation
#  - Import existence validation
#  - Review report
#  - Safe install gate
# ==========================================

function Write-PyFile($Path,$Content){
    $Dir = Split-Path $Path
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    Set-Content -Path $Path -Value $Content -Encoding UTF8
    Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\evolution\validator.py" @'
from pathlib import Path
import ast
import importlib.util
import re

class PatchValidator:

    def validate(self, patch_path="data/generated_patch.py"):
        report=[]
        ok=True

        code=Path(patch_path).read_text(encoding="utf-8")

        if code.startswith("```"):
            lines=code.splitlines()
            if lines and lines[0].startswith("```"):
                lines=lines[1:]
            if lines and lines[-1].startswith("```"):
                lines=lines[:-1]
            code="\n".join(lines)

        try:
            ast.parse(code)
            report.append("[OK] Syntax")
        except Exception as e:
            ok=False
            report.append(f"[FAIL] Syntax: {e}")

        imports=re.findall(r"^(?:from|import)\s+([a-zA-Z0-9_\.]+)",code,re.MULTILINE)

        for mod in imports:
            if mod.startswith("app."):
                spec=importlib.util.find_spec(mod)
                if spec is None:
                    ok=False
                    report.append(f"[FAIL] Missing module: {mod}")

        Path("data/validation_report.txt").write_text(
            "\n".join(report),
            encoding="utf-8"
        )

        return ok,report
'@

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner
from .planner import EvolutionPlanner
from .generator import CodeGenerator
from .reviewer import PatchReviewer
from .validator import PatchValidator

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
        PatchReviewer().review(patch,target)
        ok,report=PatchValidator().validate(patch)

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
'@

Write-Host ""
Write-Host "Evolution Validation v9 Installed" -ForegroundColor Cyan
