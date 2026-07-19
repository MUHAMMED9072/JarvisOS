from pathlib import Path
import ast

class PatchReviewer:

    def review(self,
               patch="data/generated_patch.py",
               original="app/skills/loader.py"):

        result={
            "syntax":False,
            "imports_ok":True,
            "errors":[],
            "warnings":[]
        }

        code=Path(patch).read_text(encoding="utf-8")

        if code.startswith("```"):
            lines=code.splitlines()
            if lines and lines[0].startswith("```"):
                lines=lines[1:]
            if lines and lines[-1].startswith("```"):
                lines=lines[:-1]
            code="\n".join(lines)

        try:
            ast.parse(code)
            result["syntax"]=True
        except Exception as e:
            result["errors"].append(f"Syntax: {e}")

        if "package = app.skills" in code and "import app.skills" not in code:
            result["warnings"].append(
                "Uses app.skills without importing app.skills"
            )

        Path("data/review_report.txt").write_text(
            "\n".join(
                ["PATCH REVIEW",
                 f"Syntax OK: {result['syntax']}",
                 *["ERROR: "+e for e in result["errors"]],
                 *["WARNING: "+w for w in result["warnings"]]]
            ),
            encoding="utf-8"
        )

        return result
