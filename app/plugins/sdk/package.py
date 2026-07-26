from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Config
from app.core.logger import JarvisLogger
from app.plugins.sdk.loader import PluginLoader
from app.plugins.sdk.manager import PluginManager
from app.plugins.sdk.models import (
    PluginManifest,
    check_version_compatibility,
    validate_manifest,
)

_INSTALLED_META = "installed.json"


class PackageError(Exception):
    """Base exception for packaging errors."""


class PackageValidationError(PackageError):
    """Raised when a package fails validation."""


class PackageExistsError(PackageError):
    """Raised when a package is already installed."""


class PackageNotFoundError(PackageError):
    """Raised when a package is not found."""


class PackageCompatibilityError(PackageError):
    """Raised when version compatibility check fails."""


@dataclass
class InstallMetadata:
    name: str
    version: str
    installed_at: str
    package_hash: str
    manifest: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "installed_at": self.installed_at,
            "package_hash": self.package_hash,
            "manifest": self.manifest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstallMetadata:
        return cls(
            name=data["name"],
            version=data["version"],
            installed_at=data["installed_at"],
            package_hash=data["package_hash"],
            manifest=data["manifest"],
        )


@dataclass
class PluginPackage:
    """Represents a packaged plugin (.jarvis-plugin file)."""

    name: str
    version: str
    manifest: PluginManifest
    path: Path
    file_hash: str
    errors: list[str] = field(default_factory=list)


def _installed_meta_path() -> Path:
    return Config.DATA_DIR / "plugins" / _INSTALLED_META


def _load_installed_meta() -> dict[str, dict[str, Any]]:
    path = _installed_meta_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_installed_meta(meta: dict[str, dict[str, Any]]) -> None:
    path = _installed_meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def compute_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_manifest_from_zip(zf: zipfile.ZipFile) -> PluginManifest:
    for name in ("plugin.json", "manifest.json"):
        if name in zf.namelist():
            data = json.loads(zf.read(name))
            deps_raw = data.get("dependencies", [])
            from app.plugins.sdk.models import PluginDependency
            deps = [PluginDependency(**d) for d in deps_raw] if deps_raw else []
            return PluginManifest(
                name=data.get("name", ""),
                version=str(data.get("version", "1.0.0")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                min_core_version=str(data.get("min_core_version", "0.4.0")),
                dependencies=deps,
                capabilities=data.get("capabilities", []),
                config_schema=data.get("config_schema"),
                permissions=data.get("permissions", []),
            )
    raise PackageValidationError("Package has no plugin.json or manifest.json")


class PackageManager:
    """Install, uninstall, upgrade, export, and import local plugin packages.

    A plugin package is a ``.jarvis-plugin`` ZIP archive containing
    ``plugin.json`` (or ``manifest.json``) plus the plugin source files.
    """

    def __init__(
        self,
        manager: PluginManager,
        loader: PluginLoader | None = None,
    ) -> None:
        self._manager = manager
        self._loader = loader

    # ------------------------------------------------------------------
    # Package inspection
    # ------------------------------------------------------------------

    def inspect(self, package_path: str | Path) -> PluginPackage:
        path = Path(package_path).resolve()
        if not path.is_file():
            raise PackageNotFoundError(f"Package not found: {path}")
        try:
            file_hash = compute_hash(path)
            with zipfile.ZipFile(path, "r") as zf:
                manifest = load_manifest_from_zip(zf)
            errs = validate_manifest(manifest)
            return PluginPackage(
                name=manifest.name,
                version=manifest.version,
                manifest=manifest,
                path=path,
                file_hash=file_hash,
                errors=errs,
            )
        except (zipfile.BadZipFile, json.JSONDecodeError, PackageValidationError) as exc:
            raise PackageValidationError(
                f"Invalid package {path.name}: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def install(
        self,
        package_path: str | Path,
        enable: bool = True,
    ) -> str:
        pkg = self.inspect(package_path)
        if pkg.errors:
            raise PackageValidationError(
                f"Package {pkg.name!r} has validation errors: {pkg.errors}",
            )
        _ensure_compatible(pkg.manifest)

        meta = _load_installed_meta()
        if pkg.name in meta:
            raise PackageExistsError(
                f"Plugin {pkg.name!r} is already installed "
                f"(version {meta[pkg.name]['version']}). "
                f"Use upgrade() to update.",
            )

        target_dir = Config.PLUGIN_DIR / pkg.name
        if target_dir.is_dir():
            raise PackageExistsError(
                f"Directory {target_dir} already exists",
            )

        backup_dir: Path | None = None
        try:
            _extract_package(pkg.path, target_dir)
            _load_plugin(pkg.name, self._manager, self._loader, enable)
            meta[pkg.name] = InstallMetadata(
                name=pkg.name,
                version=pkg.version,
                installed_at=datetime.now(timezone.utc).isoformat(),
                package_hash=pkg.file_hash,
                manifest=_manifest_to_dict(pkg.manifest),
            ).to_dict()
            _save_installed_meta(meta)
            JarvisLogger.info(
                "Package installed: %s v%s", pkg.name, pkg.version,
            )
            return pkg.name
        except Exception as exc:
            _cleanup_failed_install(pkg.name, target_dir, backup_dir)
            raise PackageError(
                f"Installation of {pkg.name!r} failed: {exc}",
            ) from exc

    def uninstall(self, name: str) -> None:
        meta = _load_installed_meta()
        if name not in meta:
            raise PackageNotFoundError(f"Plugin {name!r} is not installed")

        target_dir = Config.PLUGIN_DIR / name

        self._manager.unload(name, remove=True)

        plugin_data_dir = Config.DATA_DIR / "plugins" / name
        if plugin_data_dir.is_dir():
            try:
                shutil.rmtree(plugin_data_dir)
            except Exception as exc:
                JarvisLogger.warning(
                    "Failed to remove plugin data dir %r: %s",
                    plugin_data_dir, exc,
                )

        if target_dir.is_dir():
            try:
                shutil.rmtree(target_dir)
            except Exception as exc:
                JarvisLogger.warning(
                    "Failed to remove plugin dir %r: %s",
                    target_dir, exc,
                )

        meta.pop(name, None)
        _save_installed_meta(meta)
        JarvisLogger.info("Package uninstalled: %s", name)

    def upgrade(
        self,
        name: str,
        package_path: str | Path,
        enable: bool = True,
    ) -> str:
        meta = _load_installed_meta()
        if name not in meta:
            raise PackageNotFoundError(
                f"Plugin {name!r} is not installed. Use install() first.",
            )

        pkg = self.inspect(package_path)
        if pkg.errors:
            raise PackageValidationError(
                f"Package {pkg.name!r} has validation errors: {pkg.errors}",
            )
        _ensure_compatible(pkg.manifest)

        old_version = meta[name]["version"]
        target_dir = Config.PLUGIN_DIR / name
        backup_path: Path | None = None

        if target_dir.is_dir():
            backup_path = Path(tempfile.mkdtemp()) / name
            try:
                shutil.copytree(target_dir, backup_path)
            except Exception as exc:
                raise PackageError(
                    f"Failed to backup {name}: {exc}",
                ) from exc

        try:
            self._manager.unload(name, remove=True)
            if target_dir.is_dir():
                shutil.rmtree(target_dir)
            _extract_package(pkg.path, target_dir)
            _load_plugin(name, self._manager, self._loader, enable)
            meta[name] = InstallMetadata(
                name=pkg.name,
                version=pkg.version,
                installed_at=datetime.now(timezone.utc).isoformat(),
                package_hash=pkg.file_hash,
                manifest=_manifest_to_dict(pkg.manifest),
            ).to_dict()
            _save_installed_meta(meta)
            JarvisLogger.info(
                "Package upgraded: %s v%s -> %s",
                name, old_version, pkg.version,
            )
            return name
        except Exception as exc:
            JarvisLogger.error(
                "Upgrade of %r failed: %s. Rolling back.", name, exc,
            )
            _rollback_upgrade(name, target_dir, backup_path, self._manager, self._loader)
            raise PackageError(
                f"Upgrade of {name!r} failed and was rolled back: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, name: str, output_path: str | Path) -> Path:
        meta = _load_installed_meta()
        if name not in meta:
            raise PackageNotFoundError(f"Plugin {name!r} is not installed")

        source_dir = Config.PLUGIN_DIR / name
        if not source_dir.is_dir():
            raise PackageNotFoundError(
                f"Plugin directory {source_dir} not found",
            )

        output = Path(output_path).resolve()
        if output.is_dir():
            output = output / f"{name}.jarvis-plugin"

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file() and file_path.name != "__pycache__":
                    arcname = str(file_path.relative_to(source_dir))
                    zf.write(file_path, arcname)

        JarvisLogger.info(
            "Package exported: %s -> %s", name, output,
        )
        return output

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_installed(self) -> list[InstallMetadata]:
        meta = _load_installed_meta()
        return [
            InstallMetadata.from_dict(v)
            for v in sorted(meta.values(), key=lambda x: x["name"])
        ]

    def get_installed(self, name: str) -> InstallMetadata | None:
        meta = _load_installed_meta()
        raw = meta.get(name)
        if raw is None:
            return None
        return InstallMetadata.from_dict(raw)

    def verify(self, name: str) -> bool:
        meta = _load_installed_meta()
        raw = meta.get(name)
        if raw is None:
            return False
        target_dir = Config.PLUGIN_DIR / name
        if not target_dir.is_dir():
            return False
        if not (target_dir / "plugin.json").is_file() and not (target_dir / "manifest.json").is_file():
            return False
        return True


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _ensure_compatible(manifest: PluginManifest) -> None:
    if manifest.min_core_version:
        if not check_version_compatibility(
            manifest.min_core_version, Config.VERSION,
        ):
            raise PackageCompatibilityError(
                f"Plugin {manifest.name!r} requires core "
                f"{manifest.min_core_version}, current is {Config.VERSION}",
            )


def _extract_package(pkg_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "r") as zf:
        for member in zf.namelist():
            if member.startswith("/") or ".." in member:
                continue
            zf.extract(member, target_dir)


def _load_plugin(
    name: str,
    manager: PluginManager,
    loader: PluginLoader | None,
    enable: bool,
) -> None:
    if loader is not None:
        loader.discover()
        loader.load_all(enable=enable)
    else:
        manager.discover(None)


def _manifest_to_dict(manifest: PluginManifest) -> dict[str, Any]:
    deps = [{"name": d.name, "version": d.version} for d in manifest.dependencies]
    return {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "author": manifest.author,
        "min_core_version": manifest.min_core_version,
        "dependencies": deps,
        "capabilities": manifest.capabilities,
        "config_schema": manifest.config_schema,
        "permissions": manifest.permissions,
    }


def _cleanup_failed_install(
    name: str, target_dir: Path, backup_dir: Path | None,
) -> None:
    if target_dir.is_dir():
        try:
            shutil.rmtree(target_dir)
        except Exception:
            pass
    if backup_dir and backup_dir.is_dir():
        try:
            shutil.copytree(backup_dir, target_dir)
        except Exception:
            pass


def _rollback_upgrade(
    name: str,
    target_dir: Path,
    backup_path: Path | None,
    manager: PluginManager,
    loader: PluginLoader | None,
) -> None:
    if target_dir.is_dir():
        try:
            shutil.rmtree(target_dir)
        except Exception:
            pass
    if backup_path and backup_path.is_dir():
        try:
            shutil.copytree(backup_path, target_dir)
            _load_plugin(name, manager, loader, enable=False)
        except Exception:
            pass
