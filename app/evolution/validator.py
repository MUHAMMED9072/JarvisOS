from pathlib import Path
import importlib.util
import re

class PatchValidator:

    def validate(self, patch_path="data/generated_patch.py", review=None):
        report=[]
        ok=True

        if review:
            if not review.syntax:
                ok = False
                report.append("[FAIL] Syntax check failed in reviewer")
            code = review.clean_code
        else:
            code=Path(patch_path).read_text(encoding="utf-8")

            if code.startswith("```"):
                lines=code.splitlines()
                if lines and lines[0].startswith("```"):
                    lines=lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines=lines[:-1]
                code="\n".join(lines)

        # Validation logic for Syntax/AST parsing is handled exclusively
        # by PatchReviewer to prevent logic duplication.

        imports=re.findall(r"^(?:from|import)\s+([a-zA-Z0-9_\.]+)",code,re.MULTILINE)

        for mod in imports:
            if mod.startswith("app."):
                spec=importlib.util.find_spec(mod)
                if spec is None:
                    ok=False
                    report.append(f"[FAIL] Missing module: {mod}")

        if ok:
            report.append("[OK] Module imports validated")

        Path("data/validation_report.txt").write_text(
            "\n".join(report),
            encoding="utf-8"
        )

        return ok,report
