"""
JARVIS Evolution Engine - Rollback
"""

from __future__ import annotations

import shutil
from pathlib import Path
from dataclasses import dataclass


@dataclass
class RollbackResult:
    success: bool
    message: str


class RollbackManager:
    """Restore files from a backup directory."""

    def create_backup(self, source: str, backup: str) -> RollbackResult:
        src = Path(source)
        dst = Path(backup)

        if not src.exists():
            return RollbackResult(False, "Source not found.")

        if dst.exists():
            shutil.rmtree(dst)

        shutil.copytree(src, dst)
        return RollbackResult(True, f"Backup created: {dst}")

    def restore(self, backup: str, destination: str) -> RollbackResult:
        src = Path(backup)
        dst = Path(destination)

        if not src.exists():
            return RollbackResult(False, "Backup not found.")

        if dst.exists():
            shutil.rmtree(dst)

        shutil.copytree(src, dst)
        return RollbackResult(True, f"Restored to: {dst}")


if __name__ == "__main__":
    rb = RollbackManager()
    print("Rollback manager ready.")
