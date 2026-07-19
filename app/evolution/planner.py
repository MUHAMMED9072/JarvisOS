import json
from pathlib import Path
from app.ai.manager import AIManager

class EvolutionPlanner:

    def create_plan(self):
        prompt = Path("data/ai_prompt.txt").read_text(encoding="utf-8")

        print("[AI] Sending prompt to Qwen2.5-Coder...")

        answer = AIManager().ask("ollama", prompt)

        Path("data").mkdir(exist_ok=True)

        Path("data/improvement_plan.md").write_text(
            answer,
            encoding="utf-8"
        )

        return answer
