# ==========================================
# JARVIS Ollama AI Planner v2
# ==========================================

function Write-PyFile($Path,$Content){
 $Dir=Split-Path $Path
 New-Item -ItemType Directory -Force -Path $Dir|Out-Null
 Set-Content -Path $Path -Value $Content -Encoding UTF8
 Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\ai\providers\ollama.py" @'
from ollama import chat

class OllamaProvider:
    def generate(self, prompt:str, model="qwen2.5-coder"):
        r = chat(
            model=model,
            messages=[{"role":"user","content":prompt}]
        )
        return r["message"]["content"]
'@

Write-PyFile "app\evolution\planner.py" @'
import json
from pathlib import Path
from app.ai.providers.ollama import OllamaProvider

class EvolutionPlanner:

    def create_plan(self):
        prompt = Path("data/ai_prompt.txt").read_text(encoding="utf-8")

        print("[AI] Sending prompt to Qwen2.5-Coder...")

        provider = OllamaProvider()
        answer = provider.generate(prompt)

        Path("data").mkdir(exist_ok=True)

        Path("data/improvement_plan.md").write_text(
            answer,
            encoding="utf-8"
        )

        return answer
'@

Write-PyFile "app\evolution\brain.py" @'
from .scanner import ProjectScanner
from .planner import EvolutionPlanner

class EvolutionBrain:

    def evolve(self):
        ProjectScanner().scan()
        plan = EvolutionPlanner().create_plan()

        print("="*50)
        print("AI EVOLUTION PLAN")
        print("="*50)
        print(plan)
        print("="*50)
        print("Saved -> data/improvement_plan.md")
        return plan
'@

Write-Host ""
Write-Host "Ollama Evolution Installed" -ForegroundColor Cyan
