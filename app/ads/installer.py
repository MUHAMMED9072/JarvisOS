from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ads.content_generator import GeneratedContent
from app.ads.paths import INSTALLED_DIR


@dataclass
class InstallSnapshot:
    """Pre-installation snapshot for rollback."""

    artifact_name: str = ""
    timestamp: float = field(default_factory=time.time)
    backup_path: str = ""
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "timestamp": self.timestamp,
            "backup_path": self.backup_path,
            "files": list(self.files),
        }


@dataclass
class InstallResult:
    """Result of artifact installation."""

    artifact_name: str = ""
    install_path: str = ""
    files_installed: list[str] = field(default_factory=list)
    dependencies_resolved: list[str] = field(default_factory=list)
    success: bool = True
    snapshot: InstallSnapshot | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "install_path": self.install_path,
            "files_installed": list(self.files_installed),
            "dependencies_resolved": list(self.dependencies_resolved),
            "success": self.success,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "error": self.error,
        }


class Installer:
    """Install approved artifacts to the filesystem with rollback support."""

    def __init__(self, base_path: str | None = None) -> None:
        self._base_path = Path(base_path) if base_path is not None else INSTALLED_DIR

    def install(
        self,
        artifact_name: str,
        content: GeneratedContent,
        dependencies: list[str] | None = None,
    ) -> InstallResult:
        target_dir = self._base_path / artifact_name

        # Create snapshot for rollback if directory exists
        snapshot = None
        if target_dir.exists():
            backup = self._base_path / f".backup_{artifact_name}_{int(time.time())}"
            shutil.copytree(target_dir, backup)
            snapshot = InstallSnapshot(
                artifact_name=artifact_name,
                backup_path=str(backup),
                files=[str(p.relative_to(target_dir)) for p in target_dir.rglob("*") if p.is_file()],
            )

        # Install files
        target_dir.mkdir(parents=True, exist_ok=True)
        files_installed: list[str] = []
        for filename, file_content in content.files.items():
            filepath = target_dir / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(file_content, encoding="utf-8")
            files_installed.append(str(filepath))

        # Install manifest
        manifest_path = target_dir / "manifest.json"
        manifest_path.write_text(json.dumps(content.manifest, indent=2), encoding="utf-8")
        files_installed.append(str(manifest_path))

        # Resolve dependencies (simulated)
        deps = list(dependencies or [])

        return InstallResult(
            artifact_name=artifact_name,
            install_path=str(target_dir),
            files_installed=files_installed,
            dependencies_resolved=deps,
            success=True,
            snapshot=snapshot,
        )

    def rollback(self, snapshot: InstallSnapshot) -> bool:
        """Rollback to pre-installation state."""
        backup = Path(snapshot.backup_path)
        if not backup.exists():
            return False
        target = self._base_path / snapshot.artifact_name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(backup, target)
        shutil.rmtree(backup, ignore_errors=True)
        return True

    def health(self) -> dict[str, Any]:
        return {"alive": True, "base_path": str(self._base_path)}
