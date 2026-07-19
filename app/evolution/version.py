"""
JARVIS Evolution Engine - Version Manager
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    suffix: str = ""

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.suffix:
            s += f"-{self.suffix}"
        return s

    @classmethod
    def from_string(cls, version_str: str) -> Version:
        import re
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$", version_str.strip())
        if m:
            return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "")
        return cls(0, 0, 0)


class VersionManager:
    def __init__(self, file: str = "data/version.json") -> None:
        self.path = Path(file)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            from app.core.config import Config
            self.save(Version.from_string(Config.VERSION))

    def load(self) -> Version:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return Version(**data)

    def save(self, version: Version) -> None:
        self.path.write_text(
            json.dumps(version.__dict__, indent=4),
            encoding="utf-8",
        )

    def bump_major(self) -> Version:
        v = self.load()
        n = Version(v.major + 1, 0, 0, v.suffix)
        self.save(n)
        return n

    def bump_minor(self) -> Version:
        v = self.load()
        n = Version(v.major, v.minor + 1, 0, v.suffix)
        self.save(n)
        return n

    def bump_patch(self) -> Version:
        v = self.load()
        n = Version(v.major, v.minor, v.patch + 1, v.suffix)
        self.save(n)
        return n

    def info(self) -> dict:
        return {
            "version": str(self.load()),
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
