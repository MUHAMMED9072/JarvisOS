# ==========================================
# JARVIS AI Planner Upgrade
# ==========================================

function Write-PyFile($Path,$Content){
 $Dir=Split-Path $Path
 New-Item -ItemType Directory -Force -Path $Dir|Out-Null
 Set-Content -Path $Path -Value $Content -Encoding UTF8
 Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\evolution\planner.py" @'
import json
from pathlib import Path

class EvolutionPlanner:

    def create_plan(self, report_path="data/evolution_report.json"):
        report=json.loads(Path(report_path).read_text(encoding="utf-8"))
        s=report["summary"]

        prompt=f"""
You are the AI architect for JARVIS OS.

Project statistics:
- Python files: {s['files']}
- Classes: {s['classes']}
- Functions: {s['functions']}
- Imports: {s['imports']}

Return ONLY a numbered improvement plan.
"""

        Path("data").mkdir(exist_ok=True)
        Path("data/ai_prompt.txt").write_text(prompt,encoding="utf-8")

        return {
            "status":"READY",
            "prompt_file":"data/ai_prompt.txt",
            "next":"Send this prompt to Qwen2.5-Coder"
        }
'@

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner
from .planner import EvolutionPlanner

class EvolutionBrain:

    def evolve(self):
        scan=ProjectScanner().scan()
        plan=EvolutionPlanner().create_plan()

        print("="*50)
        print("JARVIS EVOLUTION ENGINE")
        print("="*50)
        print(f"Files     : {scan['summary']['files']}")
        print(f"Classes   : {scan['summary']['classes']}")
        print(f"Functions : {scan['summary']['functions']}")
        print()
        print("[OK] evolution_report.json created")
        print("[OK] ai_prompt.txt created")
        print()
        print("Next:")
        print("Feed data/ai_prompt.txt to Qwen2.5-Coder")
        print("="*50)
        return plan
'@

Write-Host ""
Write-Host "AI Planner Installed" -ForegroundColor Cyan
