# ==========================================
# JARVIS Prompt Upgrade v5
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

    def generate_task(self, task:str, target_file:str, output="data/generated_patch.py"):
        target = Path(target_file)

        if not target.exists():
            raise FileNotFoundError(target_file)

        source = target.read_text(encoding="utf-8")

        prompt=f"""
You are modifying an EXISTING JARVIS OS project.

TARGET FILE:
{target_file}

RULES:
- Keep existing class names.
- Keep public methods.
- Improve ONLY the requested task.
- Do NOT invent new folders.
- Return ONLY valid Python code.
- Return the COMPLETE replacement file.

TASK:
{task}

CURRENT FILE:

```python
{source}
```
"""

        print(f"[AI] Improving {target_file}...")
        code = OllamaProvider().generate(prompt)
        Path(output).write_text(code, encoding="utf-8")
        return output
'@

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner
from .planner import EvolutionPlanner
from .generator import CodeGenerator

class EvolutionBrain:

    TASKS = {
        "1": ("Improve dynamic skill discovery.","app/skills/loader.py"),
        "2": ("Improve semantic search.","app/memory/search.py"),
        "3": ("Improve retry logic.","app/ai/router.py"),
        "4": ("Improve sandbox safety.","app/evolution/sandbox.py")
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
        task,file=self.TASKS.get(c,self.TASKS["1"])

        out=CodeGenerator().generate_task(task,file)

        print(f"[OK] Generated patch for {file}")
        print(f"[OK] Saved -> {out}")
        print("Review before applying.")
'@

Write-Host ""
Write-Host "Prompt Upgrade Installed" -ForegroundColor Cyan
