"""
JARVIS Evolution Engine - Version Manager

``Config.VERSION`` is the single authoritative source of truth for the
project version. ``VersionManager`` reads it on first run (when
``data/version.json`` does not yet exist) and preserves its pre-release
suffix across bumps. ``Config.VERSION`` itself is never mutated at
runtime — see ``app/core/config.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    suffix: str = ""

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.suffix:
            return f"{base}-{self.suffix}"
        return base

    @classmethod
    def from_string(cls, version_str: str) -> "Version":
        """Parse a ``major.minor.patch[-suffix]`` string into a ``Version``.

        Falls back to ``Version(0, 0, 0)`` for unparseable input so a bad
        ``Config.VERSION`` never crashes the version manager; the
        authoritative default still comes from ``Config.VERSION`` upstream
        via :class:`VersionManager`.
        """
        match = re.match(
            r"^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$",
            (version_str or "").strip(),
        )
        if not match:
            return cls(0, 0, 0)
        return cls(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            (match.group(4) or "").strip(),
        )


class VersionManager:
    def __init__(self, file: str = "data/version.json") -> None:
        self.path = Path(file)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            # Defer import to avoid a circular import at module load
            # (config.py is already safe to import here — app.evolution
            # is not imported by app.core — but keeping the import local
            # documents the dependency clearly).
            from app.core.config import Config

            self.save(Version.from_string(Config.VERSION))

    def load(self) -> Version:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        # Backward compat: older files store only major/minor/patch.
        # ``Version.suffix`` defaults to "" so a 3-key payload still
        # round-trips correctly.
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
