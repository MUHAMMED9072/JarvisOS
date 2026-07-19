# ==========================================
# JARVIS Context Upgrade v6
# ==========================================

function Write-PyFile($Path,$Content){
 $Dir=Split-Path $Path
 New-Item -ItemType Directory -Force -Path $Dir | Out-Null
 Set-Content -Path $Path -Value $Content -Encoding UTF8
 Write-Host "Installed $Path" -ForegroundColor Green
}

Write-PyFile "app\evolution\context_builder.py" @'
from pathlib import Path

class ContextBuilder:

    def build(self, root="app"):
        lines=["PROJECT TREE"]
        for p in sorted(Path(root).rglob("*.py")):
            lines.append(str(p).replace("\\\\","/"))
        Path("data").mkdir(exist_ok=True)
        out=Path("data/project_tree.txt")
        out.write_text("\\n".join(lines),encoding="utf-8")
        return out
'@

Write-PyFile "app\evolution\generator.py" @'
from pathlib import Path
from app.ai.providers.ollama import OllamaProvider
from .context_builder import ContextBuilder

class CodeGenerator:

    def generate_task(self, task:str, target_file:str, output="data/generated_patch.py"):
        tree = ContextBuilder().build().read_text(encoding="utf-8")
        source = Path(target_file).read_text(encoding="utf-8")

        prompt=f"""
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
        code = OllamaProvider().generate(prompt)
        Path(output).write_text(code,encoding="utf-8")
        return output
'@

Write-Host ""
Write-Host "Context Upgrade Installed" -ForegroundColor Cyan
