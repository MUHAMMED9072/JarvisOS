from pathlib import Path

from .ai import EvolutionAI
from .context_builder import ContextBuilder


class CodeGenerator:

    def __init__(self, registry):
        self._ai = EvolutionAI(registry)

    def generate_task(self, task: str, target_file: str, output="data/generated_patch.py"):
        tree = ContextBuilder().build().read_text(encoding="utf-8")
        source = Path(target_file).read_text(encoding="utf-8")

        prompt = f"""
You are editing an EXISTING JARVIS OS project.

{tree}

TARGET FILE:
{target_file}

RULES:
- Never invent files or modules.
- Only reference paths from PROJECT TREE.
- Preserve class names and public methods.
- Return ONLY the complete replacement Python file.

TASK:
{task}

CURRENT FILE:

```python
{source}
```
"""
        print("[AI] Building project-aware patch...")
        code = self._ai.generate(prompt)
        Path(output).write_text(str(code), encoding="utf-8")
        return output
