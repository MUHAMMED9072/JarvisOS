# ==========================================
# JARVIS Patch Reviewer v7
# ==========================================

function Write-PyFile($Path,$Content){
 $Dir=Split-Path $Path
 New-Item -ItemType Directory -Force -Path $Dir | Out-Null
 Set-Content -Path $Path -Value $Content -Encoding UTF8
 Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\evolution\reviewer.py" @'
from pathlib import Path
import ast

class PatchReviewer:

    def review(self,
               patch="data/generated_patch.py",
               original="app/skills/loader.py"):

        result={
            "syntax":False,
            "imports_ok":True,
            "errors":[],
            "warnings":[]
        }

        code=Path(patch).read_text(encoding="utf-8")

        if code.startswith("```"):
            lines=code.splitlines()
            if lines and lines[0].startswith("```"):
                lines=lines[1:]
            if lines and lines[-1].startswith("```"):
                lines=lines[:-1]
            code="\n".join(lines)

        try:
            ast.parse(code)
            result["syntax"]=True
        except Exception as e:
            result["errors"].append(f"Syntax: {e}")

        if "package = app.skills" in code and "import app.skills" not in code:
            result["warnings"].append(
                "Uses app.skills without importing app.skills"
            )

        Path("data/review_report.txt").write_text(
            "\n".join(
                ["PATCH REVIEW",
                 f"Syntax OK: {result['syntax']}",
                 *["ERROR: "+e for e in result["errors"]],
                 *["WARNING: "+w for w in result["warnings"]]]
            ),
            encoding="utf-8"
        )

        return result
'@

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner
from .planner import EvolutionPlanner
from .generator import CodeGenerator
from .reviewer import PatchReviewer

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

        c=input("Choose task: ").strip()
        task,target=self.TASKS.get(c,self.TASKS["1"])

        out=CodeGenerator().generate_task(task,target)
        review=PatchReviewer().review(out,target)

        print()
        print("[OK] Patch generated")
        print(f"[OK] Syntax: {review['syntax']}")
        if review["warnings"]:
            print("[WARNING]")
            for w in review["warnings"]:
                print(" -",w)
        print("Review saved -> data/review_report.txt")
'@

Write-Host ""
Write-Host "Patch Reviewer Installed" -ForegroundColor Cyan
