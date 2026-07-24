"""
JARVIS Evolution Engine - Rollback

Backup and restore a single file or directory to/from a backup
directory. The backup directory contains a ``.rollback.json`` marker
that records what was backed up, so :meth:`RollbackManager.restore`
can restore the correct type without guessing.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RollbackResult:
    success: bool
    message: str


class RollbackManager:
    """Backup and restore a single file or directory for one-step rollback."""

    MARKER = ".rollback.json"

    def create_backup(self, source: str, backup_dir: str) -> RollbackResult:
        src = Path(source)
        dst = Path(backup_dir)

        if not src.exists():
            return RollbackResult(False, f"Source not found: {src}")

        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=False)

        if src.is_file():
            shutil.copy2(src, dst / src.name)
            source_type = "file"
        else:
            shutil.copytree(src, dst / src.name)
            source_type = "directory"

        (dst / self.MARKER).write_text(
            json.dumps({"source_type": source_type, "source_name": src.name}),
            encoding="utf-8",
        )
        return RollbackResult(True, f"Backup created: {dst}")

    def restore(self, backup_dir: str, destination: str) -> RollbackResult:
        bkp = Path(backup_dir)
        dst = Path(destination)

        if not bkp.exists():
            return RollbackResult(False, f"Backup not found: {bkp}")

        marker = bkp / self.MARKER
        if not marker.exists():
            return RollbackResult(False, f"Backup marker missing: {marker}")

        info = json.loads(marker.read_text(encoding="utf-8"))
        source_name = info["source_name"]
        source_type = info["source_type"]
        backup_item = bkp / source_name

        if not backup_item.exists():
            return RollbackResult(False, f"Backup item not found: {backup_item}")

        if source_type == "file":
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_item, dst)
        else:
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(backup_item, dst)

        return RollbackResult(True, f"Restored to: {dst}")


if __name__ == "__main__":
    rb = RollbackManager()
    print("Rollback manager ready.")
