from pathlib import Path
import ast
import importlib.util
import re

class PatchValidator:

    def validate(self, patch_path="data/generated_patch.py"):
        report=[]
        ok=True

        code=Path(patch_path).read_text(encoding="utf-8")

        if code.startswith("```"):
            lines=code.splitlines()
            if lines and lines[0].startswith("```"):
                lines=lines[1:]
            if lines and lines[-1].startswith("```"):
                lines=lines[:-1]
            code="\n".join(lines)

        try:
            ast.parse(code)
            report.append("[OK] Syntax")
        except Exception as e:
            ok=False
            report.append(f"[FAIL] Syntax: {e}")

        imports=re.findall(r"^(?:from|import)\s+([a-zA-Z0-9_\.]+)",code,re.MULTILINE)

        for mod in imports:
            if mod.startswith("app."):
                spec=importlib.util.find_spec(mod)
                if spec is None:
                    ok=False
                    report.append(f"[FAIL] Missing module: {mod}")

        Path("data/validation_report.txt").write_text(
            "\n".join(report),
            encoding="utf-8"
        )

        return ok,report
