"""
JARVIS Evolution Engine - Analyzer
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib


@dataclass
class AnalysisResult:
    files: int
    lines: int
    sha256: str


class Analyzer:

    def analyze(self, root: str = "app") -> AnalysisResult:
        path = Path(root)

        total_files = 0
        total_lines = 0
        digest = hashlib.sha256()

        for file in path.rglob("*.py"):
            total_files += 1
            data = file.read_bytes()
            digest.update(data)
            total_lines += len(data.decode("utf-8", errors="ignore").splitlines())

        return AnalysisResult(
            files=total_files,
            lines=total_lines,
            sha256=digest.hexdigest(),
        )


if __name__ == "__main__":
    analyzer = Analyzer()
    result = analyzer.analyze()

    print("Files :", result.files)
    print("Lines :", result.lines)
    print("Hash  :", result.sha256)
