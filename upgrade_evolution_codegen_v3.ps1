# ==========================================
# JARVIS Evolution Code Generator v3
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

    def generate(self,
                 improvement_file="data/improvement_plan.md",
                 output="data/generated_patch.py"):

        plan = Path(improvement_file).read_text(encoding="utf-8")

        prompt = f"""
You are improving JARVIS OS.

Read this improvement plan.

Return ONLY valid Python code.

Plan:
{plan}
"""

        print("[AI] Generating Python code...")

        code = OllamaProvider().generate(prompt)

        Path(output).write_text(code, encoding="utf-8")

        return output
'@

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner
from .planner import EvolutionPlanner
from .generator import CodeGenerator

class EvolutionBrain:

    def evolve(self):
        ProjectScanner().scan()
        EvolutionPlanner().create_plan()

        generated = CodeGenerator().generate()

        print("="*50)
        print("JARVIS EVOLUTION")
        print("="*50)
        print("[OK] Project scanned")
        print("[OK] AI improvement plan created")
        print("[OK] AI generated Python code")
        print(f"[OK] Saved -> {generated}")
        print()
        print("NEXT: Sandbox -> Tests -> Approval -> Install")
        print("="*50)
        return generated
'@

Write-Host ""
Write-Host "Evolution Code Generator Installed" -ForegroundColor Cyan
