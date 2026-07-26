from pathlib import Path

from .ai import EvolutionAI


class EvolutionPlanner:

    def __init__(self, registry):
        self._ai = EvolutionAI(registry)

    def create_plan(self):
        prompt = Path("data/ai_prompt.txt").read_text(encoding="utf-8")

        print("[AI] Creating evolution plan...")

        answer = self._ai.plan(prompt)

        Path("data").mkdir(exist_ok=True)

        Path("data/improvement_plan.md").write_text(
            str(answer),
            encoding="utf-8",
        )

        return str(answer)
