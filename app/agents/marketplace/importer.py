from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.base import AgentCapability, AgentMetadata
from app.agents.discovery import AgentDiscovery
from app.agents.factory import AgentFactory
from app.agents.marketplace.packaging import AgentPackage, PackageError
from app.agents.marketplace.registry import MarketplaceEntry, MarketplaceRegistry
from app.agents.registry import AgentRegistry


@dataclass
class PackageImportResult:
    success: bool = False
    agent_name: str = ""
    agent_version: str = ""
    files_installed: int = 0
    registered: bool = False
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "files_installed": self.files_installed,
            "registered": self.registered,
            "error_message": self.error_message,
            "warnings": list(self.warnings),
        }


class PackageImporter:
    """Installs agent packages into the local system."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        marketplace_registry: MarketplaceRegistry | None = None,
        install_dir: str = "",
    ) -> None:
        self._agent_registry = agent_registry
        self._marketplace = marketplace_registry
        self._install_dir = Path(install_dir or "data/agents")

    def import_package(self, package_data: bytes) -> PackageImportResult:
        """Import a .jarvis-agent package from bytes."""
        try:
            pkg = AgentPackage.load(package_data)
        except PackageError as e:
            return PackageImportResult(success=False, error_message=str(e))

        verify = pkg.verify()
        if not verify.valid:
            return PackageImportResult(
                success=False,
                error_message="Package verification failed",
                warnings=[f"Verification: {e}" for e in verify.errors],
            )

        agent_dir = self._install_dir / pkg.name / pkg.version
        if agent_dir.exists():
            return PackageImportResult(
                success=False,
                error_message=f"Agent '{pkg.name}' version {pkg.version} already installed",
            )

        try:
            files = pkg.extract_to(str(agent_dir))
        except Exception as e:
            return PackageImportResult(success=False, error_message=f"Extraction failed: {e}")

        try:
            manifests = _find_manifests_in_package(pkg)
            registered = False

            for manifest_data in manifests:
                agent_meta = AgentMetadata(
                    name=manifest_data.get("name", pkg.name),
                    version=manifest_data.get("version", pkg.version),
                    description=manifest_data.get("description", ""),
                    agent_type=manifest_data.get("agent_type", "system"),
                    capabilities=[
                        AgentCapability(name=c.get("name", ""), description=c.get("description", ""))
                        for c in manifest_data.get("capabilities", [])
                    ],
                    dependencies=manifest_data.get("dependencies", []),
                    owner=manifest_data.get("owner", ""),
                    tags=manifest_data.get("tags", []),
                )
                agent = AgentFactory.create(
                    agent_type=agent_meta.agent_type,
                    name=agent_meta.name,
                    version=agent_meta.version,
                    description=agent_meta.description,
                )
                self._agent_registry.register(agent)
                registered = True

            if self._marketplace:
                self._marketplace.register(MarketplaceEntry(
                    package_name=pkg.name,
                    version=pkg.version,
                    description=pkg.manifest.get("description", ""),
                    agent_type=pkg.manifest.get("agent_type", ""),
                    capabilities=[c.get("name", "") for c in pkg.manifest.get("capabilities", [])],
                    published_at=__import__("time").time(),
                    source="local",
                ))

            return PackageImportResult(
                success=True,
                agent_name=pkg.name,
                agent_version=pkg.version,
                files_installed=files,
                registered=registered,
            )

        except Exception as e:
            shutil.rmtree(agent_dir, ignore_errors=True)
            return PackageImportResult(success=False, error_message=str(e))

    def export_package(self, agent_name: str, version: str = "", output_path: str = "") -> bytes:
        """Export an installed agent as a .jarvis-agent package."""
        from app.agents.discovery import Manifest
        agent_dir = self._install_dir / agent_name
        if not agent_dir.exists():
            raise PackageError(f"Agent '{agent_name}' not found in {self._install_dir}")

        versions_dir = agent_dir / version if version else max(
            (d for d in agent_dir.iterdir() if d.is_dir()),
            key=lambda d: d.name, default=None,
        )
        if versions_dir is None:
            raise PackageError(f"No versions found for agent '{agent_name}'")

        manifest_file = versions_dir / "code" / "manifest.json"
        if not manifest_file.exists():
            manifest_file = versions_dir / "manifest.json"

        if manifest_file.exists():
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        else:
            manifest = {"name": agent_name, "version": version or "0.0.0", "agent_type": "system"}

        pkg = AgentPackage(manifest)
        code_dir = versions_dir / "code"
        if code_dir.exists():
            for f in sorted(code_dir.rglob("*")):
                if f.is_file() and f.name != "manifest.json":
                    rel = f.relative_to(code_dir)
                    pkg.add_code_file(str(rel), f.read_text(encoding="utf-8"))

        tests_dir = versions_dir / "tests"
        if tests_dir.exists():
            for f in sorted(tests_dir.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(tests_dir)
                    pkg.add_test_file(str(rel), f.read_text(encoding="utf-8"))

        assets_dir = versions_dir / "assets"
        if assets_dir.exists():
            for f in sorted(assets_dir.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(assets_dir)
                    pkg.add_asset(str(rel), f.read_bytes())

        package_bytes = pkg.build()

        if output_path:
            Path(output_path).write_bytes(package_bytes)

        return package_bytes


def _find_manifests_in_package(pkg: AgentPackage) -> list[dict[str, Any]]:
    return [pkg.manifest]
