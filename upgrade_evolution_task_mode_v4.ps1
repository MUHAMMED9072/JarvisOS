# ==========================================
# JARVIS Evolution Task Mode v4
# ==========================================

function Write-PyFile($Path,$Content){
 $Dir=Split-Path $Path
 New-Item -ItemType Directory -Force -Path $Dir | Out-Null
 Set-Content -Path $Path -Value $Content -Encoding UTF8
 Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\evolution\generator.py" @'
from pathlib import Path
from app.ai.providers.ollama import OllamaProvider

class CodeGenerator:

    def generate_task(self,
                      task:str,
                      output="data/generated_patch.py"):

        prompt=f"""
You are improving JARVIS OS.

TASK:
{task}

Generate ONLY ONE complete Python file.
Return ONLY Python code.
Do not explain.
"""

        print("[AI] Generating one file...")

        code = OllamaProvider().generate(prompt)

        Path(output).write_text(code, encoding="utf-8")

        return output
'@

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner
from .planner import EvolutionPlanner
from .generator import CodeGenerator

class EvolutionBrain:

    TASKS = [
        "Improve app/skills/loader.py with dynamic discovery.",
        "Improve app/memory/search.py with semantic search.",
        "Improve app/ai/router.py with retry logic.",
        "Improve app/evolution/sandbox.py with safer execution."
    ]

    def evolve(self):
        scan = ProjectScanner().scan()
        EvolutionPlanner().create_plan()

        print("="*50)
        print("JARVIS EVOLUTION TASKS")
        print("="*50)
        for i,t in enumerate(self.TASKS,1):
            print(f"{i}. {t}")

        choice = input("Choose task (1-4): ").strip()
        idx = max(1, min(4, int(choice))) - 1

        out = CodeGenerator().generate_task(self.TASKS[idx])

        print()
        print("[OK] Project scanned")
        print("[OK] AI plan created")
        print(f"[OK] Generated task #{idx+1}")
        print(f"[OK] Saved -> {out}")
        return out
'@

Write-Host ""
Write-Host "Evolution Task Mode Installed" -ForegroundColor Cyan
