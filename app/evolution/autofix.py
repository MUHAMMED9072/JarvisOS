from pathlib import Path
from app.ai.manager import AIManager

class AutoFixer:

    def fix(self,
            review_file="data/review_report.txt",
            patch_file="data/generated_patch.py"):

        review = Path(review_file).read_text(encoding="utf-8")
        patch = Path(patch_file).read_text(encoding="utf-8")

        if "WARNING" not in review and "ERROR" not in review:
            print("[AutoFix] Patch already passed review.")
            return patch_file

        prompt=f"""
You are fixing a generated Python patch.

Review:
{review}

Patch:
{patch}

Rules:
- Fix every warning/error.
- Keep the same filename and public API.
- Return ONLY valid Python code.
"""

        print("[AutoFix] Asking AI to repair patch...")
        fixed = AIManager().ask("ollama", prompt)
        Path(patch_file).write_text(fixed, encoding="utf-8")
        return patch_file
