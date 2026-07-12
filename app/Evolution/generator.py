"""
JARVIS Evolution Engine - Code Generator
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime


@dataclass
class GeneratedFile:
    path: str
    created: str
    size: int


class CodeGenerator:
    """Writes generated source code to disk."""

    def generate(self, output_path: str, source: str) -> GeneratedFile:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(source, encoding="utf-8")

        return GeneratedFile(
            path=str(path),
            created=datetime.now().isoformat(timespec="seconds"),
            size=path.stat().st_size,
        )

    def exists(self, output_path: str) -> bool:
        return Path(output_path).exists()


if __name__ == "__main__":
    generator = CodeGenerator()

    sample = """def hello():
    return 'Hello from JARVIS'
"""

    result = generator.generate("generated/sample.py", sample)

    print(result)
