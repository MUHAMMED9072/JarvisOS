from __future__ import annotations

import ast
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Config
from app.core.logger import JarvisLogger
from app.plugins.sdk.base import Plugin
from app.plugins.sdk.config import PluginConfig
from app.plugins.sdk.models import (
    PluginDependency,
    PluginManifest,
    validate_manifest,
)
from app.plugins.sdk.package import (
    InstallMetadata,
    PackageManager,
)
from app.plugins.sdk.security import Permission, PermissionManager

PLUGIN_TEMPLATE_MAIN_PY = '''from app.plugins.sdk import Plugin


class {class_name}(Plugin):
    name = "{name}"
    version = "{version}"

    def on_load(self) -> None:
        self.log_info("{name} loaded")

    def on_enable(self) -> None:
        self.log_info("{name} enabled")

    def on_disable(self) -> None:
        self.log_info("{name} disabled")

    def on_uninstall(self) -> None:
        self.log_info("{name} uninstalled")
'''

PLUGIN_TEMPLATE_INIT_PY = '''from .main import {class_name}

__all__ = ["{class_name}"]
'''

PLUGIN_MANIFEST_TEMPLATE = {
    "name": "",
    "version": "1.0.0",
    "description": "",
    "author": "",
    "min_core_version": "0.4.0",
    "dependencies": [],
    "capabilities": [],
    "config_schema": None,
    "permissions": [],
}


@dataclass
class PluginProject:
    """Represents a scaffolded plugin project on disk."""
    name: str
    path: Path
    manifest: PluginManifest


@dataclass
class ValidationResult:
    """Result of a plugin validation."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PluginDiagnosticsResult:
    """Full diagnostics for a plugin."""
    name: str
    version: str
    manifest_valid: bool
    manifest_errors: list[str]
    source_valid: bool
    source_errors: list[str]
    config_valid: bool
    config_errors: list[str]
    permission_summary: str
    services: list[str]
    dependencies: list[dict[str, str]]
    capabilities: list[str]
    disk_usage: int
    file_count: int


@dataclass
class HealthCheckResult:
    """Health check result for a plugin."""
    healthy: bool
    name: str
    version: str
    manifest_ok: bool
    source_ok: bool
    config_ok: bool
    permissions_ok: bool
    errors: list[str] = field(default_factory=list)


# ------------------------------------------------------------------
# Scaffolding
# ------------------------------------------------------------------

def scaffold_plugin(
    name: str,
    output_dir: str | Path,
    *,
    version: str = "1.0.0",
    description: str = "",
    author: str = "",
    min_core_version: str = "0.4.0",
    permissions: list[str] | None = None,
    capabilities: list[str] | None = None,
    dependencies: list[PluginDependency] | None = None,
    config_schema: dict[str, Any] | None = None,
) -> PluginProject:
    """Create a complete plugin project directory with template files."""
    output = Path(output_dir).resolve()
    if not output.is_dir():
        raise ValueError(f"Output directory does not exist: {output}")

    manifest = PluginManifest(
        name=name,
        version=version,
        description=description,
        author=author,
        min_core_version=min_core_version,
        permissions=permissions or [],
        capabilities=capabilities or [],
        dependencies=dependencies or [],
        config_schema=config_schema,
    )

    errs = validate_manifest(manifest)
    if errs:
        raise ValueError(f"Invalid manifest: {errs}")

    plugin_dir = output / name
    if plugin_dir.exists():
        raise FileExistsError(f"Plugin directory already exists: {plugin_dir}")

    plugin_dir.mkdir(parents=True)

    class_name = _to_class_name(name)
    (plugin_dir / "main.py").write_text(
        PLUGIN_TEMPLATE_MAIN_PY.format(
            class_name=class_name, name=name, version=version,
        ),
        encoding="utf-8",
    )
    (plugin_dir / "__init__.py").write_text(
        PLUGIN_TEMPLATE_INIT_PY.format(class_name=class_name),
        encoding="utf-8",
    )
    _write_manifest_json(plugin_dir, manifest)

    JarvisLogger.info("Plugin scaffold created: %s", plugin_dir)
    return PluginProject(name=name, path=plugin_dir, manifest=manifest)


def _to_class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.replace("-", "_").split("_")) + "Plugin"


def _write_manifest_json(plugin_dir: Path, manifest: PluginManifest) -> None:
    deps = [{"name": d.name, "version": d.version} for d in manifest.dependencies]
    data = {
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
    (plugin_dir / "plugin.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ------------------------------------------------------------------
# Manifest Generator
# ------------------------------------------------------------------

def generate_manifest(
    name: str,
    *,
    version: str = "1.0.0",
    description: str = "",
    author: str = "",
    min_core_version: str = "0.4.0",
    permissions: list[str] | None = None,
    capabilities: list[str] | None = None,
    dependencies: list[PluginDependency] | None = None,
    config_schema: dict[str, Any] | None = None,
) -> PluginManifest:
    """Create a validated PluginManifest with the given fields."""
    manifest = PluginManifest(
        name=name,
        version=version,
        description=description,
        author=author,
        min_core_version=min_core_version,
        permissions=permissions or [],
        capabilities=capabilities or [],
        dependencies=dependencies or [],
        config_schema=config_schema,
    )
    errs = validate_manifest(manifest)
    if errs:
        raise ValueError(f"Invalid manifest: {errs}")
    return manifest


def manifest_to_json(manifest: PluginManifest) -> str:
    """Serialize a PluginManifest to pretty-printed JSON."""
    deps = [{"name": d.name, "version": d.version} for d in manifest.dependencies]
    data = {
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
    return json.dumps(data, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------
# Manifest Validator (extended)
# ------------------------------------------------------------------

def validate_plugin_manifest(manifest: PluginManifest) -> ValidationResult:
    """Validate a PluginManifest, returning detailed errors and warnings."""
    errors = list(validate_manifest(manifest))
    warnings: list[str] = []

    if not manifest.author:
        warnings.append("No author specified")

    if not manifest.description:
        warnings.append("No description specified")

    if not manifest.permissions:
        warnings.append("No permissions declared (all permissions granted by default)")

    if not manifest.dependencies:
        warnings.append("No dependencies declared")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ------------------------------------------------------------------
# Package Inspector
# ------------------------------------------------------------------

def inspect_package(package_path: str | Path) -> dict[str, Any]:
    """Inspect a .jarvis-plugin package file and return its metadata."""
    path = Path(package_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Package not found: {path}")

    from app.plugins.sdk.package import compute_hash, load_manifest_from_zip
    import zipfile

    file_hash = compute_hash(path)
    with zipfile.ZipFile(path, "r") as zf:
        manifest = load_manifest_from_zip(zf)
        contents = sorted(zf.namelist())

    errs = validate_manifest(manifest)
    dep_list = [{"name": d.name, "version": d.version} for d in manifest.dependencies]

    return {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "author": manifest.author,
        "min_core_version": manifest.min_core_version,
        "file_size": path.stat().st_size,
        "file_hash": file_hash,
        "permissions": manifest.permissions,
        "capabilities": manifest.capabilities,
        "dependencies": dep_list,
        "config_schema": manifest.config_schema,
        "contents": contents,
        "validation_errors": errs,
        "valid": len(errs) == 0,
    }


# ------------------------------------------------------------------
# Dependency Inspector
# ------------------------------------------------------------------

def inspect_dependencies(
    manifest: PluginManifest,
    *,
    plugin_manager: Any = None,
) -> list[dict[str, Any]]:
    """Inspect dependencies of a plugin manifest."""
    result: list[dict[str, Any]] = []
    for dep in manifest.dependencies:
        entry: dict[str, Any] = {
            "name": dep.name,
            "version_spec": dep.version,
            "resolved": None,
            "resolved_version": None,
            "satisfied": None,
        }
        if plugin_manager is not None:
            resolved = plugin_manager.get_manifest(dep.name)
            if resolved is not None:
                entry["resolved"] = resolved.name
                entry["resolved_version"] = resolved.version
                from app.plugins.sdk.models import check_version_compatibility
                entry["satisfied"] = check_version_compatibility(
                    resolved.version, dep.version,
                ) if dep.version != "*" else True
        result.append(entry)
    return result


# ------------------------------------------------------------------
# Permission Inspector
# ------------------------------------------------------------------

def inspect_permissions(
    manifest: PluginManifest,
) -> dict[str, Any]:
    """Inspect and analyze the permission declarations of a plugin."""
    declared = list(manifest.permissions) if manifest.permissions else []
    all_perms = Permission.all_permissions()

    known = [p for p in declared if Permission.is_valid(p)]
    unknown = [p for p in declared if not Permission.is_valid(p)]
    missing = [p for p in all_perms if p not in declared]

    return {
        "declared": declared,
        "known": known,
        "unknown": unknown,
        "missing": missing,
        "has_all": not declared or len(known) == len(all_perms),
        "summary": ", ".join(known) if known else "(none declared - all granted)",
    }


# ------------------------------------------------------------------
# Configuration Inspector
# ------------------------------------------------------------------

def inspect_config_schema(
    manifest: PluginManifest,
) -> dict[str, Any]:
    """Inspect and analyze the config schema of a plugin manifest."""
    schema = manifest.config_schema
    if schema is None:
        return {
            "has_schema": False,
            "fields": [],
            "required_fields": [],
            "summary": "No configuration schema defined",
        }

    properties = schema.get("properties", {})
    required = schema.get("required", [])

    fields = []
    for name, prop in properties.items():
        if isinstance(prop, dict):
            fields.append({
                "name": name,
                "type": prop.get("type", "any"),
                "description": prop.get("description", ""),
                "default": prop.get("default"),
                "required": name in required,
            })

    return {
        "has_schema": True,
        "title": schema.get("title", ""),
        "description": schema.get("description", ""),
        "fields": fields,
        "required_fields": required,
        "field_count": len(fields),
        "required_count": len(required),
    }


# ------------------------------------------------------------------
# Plugin Diagnostics
# ------------------------------------------------------------------

def diagnose_plugin(
    name: str,
    plugin_manager: Any,
    *,
    plugin_dir: str | Path | None = None,
) -> PluginDiagnosticsResult:
    """Run full diagnostics on a plugin by name."""
    manifest = plugin_manager.get_manifest(name) if plugin_manager else None

    manifest_errors: list[str] = []
    manifest_valid = True
    if manifest is not None:
        manifest_errors = list(validate_manifest(manifest))
        manifest_valid = len(manifest_errors) == 0
    else:
        manifest_errors = [f"Plugin {name!r} not registered with PluginManager"]
        manifest_valid = False

    source_valid = True
    source_errors: list[str] = []
    config_valid = True
    config_errors: list[str] = []

    version = manifest.version if manifest else "unknown"
    perms: list[str] = []
    services: list[str] = []
    caps: list[str] = []
    deps: list[dict[str, str]] = []
    plugin_path: Path | None = None

    if plugin_dir is not None:
        plugin_path = Path(plugin_dir).resolve()

    if plugin_path is not None and plugin_path.is_dir():
        source_errors = _check_source_files(plugin_path)
        source_valid = len(source_errors) == 0
        config_path = plugin_path / "config.json"
        config_valid = not config_path.is_file() or _validate_json_file(config_path)
        if not config_valid:
            config_errors.append(f"Invalid config file: {config_path}")
    else:
        source_errors = [f"Plugin directory not found: {plugin_path}"]
        source_valid = False

    if manifest is not None:
        deps = [{"name": d.name, "version": d.version} for d in manifest.dependencies]
        caps = list(manifest.capabilities or [])
        perms = list(manifest.permissions or [])

    if plugin_manager is not None:
        services = plugin_manager.get_plugin_services(name)

    return PluginDiagnosticsResult(
        name=name,
        version=version,
        manifest_valid=manifest_valid,
        manifest_errors=manifest_errors,
        source_valid=source_valid,
        source_errors=source_errors,
        config_valid=config_valid,
        config_errors=config_errors,
        permission_summary=inspect_permissions(manifest)["summary"] if manifest else "(unknown)",
        services=services,
        dependencies=deps,
        capabilities=caps,
        disk_usage=0,
        file_count=0,
    )


def _check_source_files(plugin_path: Path) -> list[str]:
    errors: list[str] = []
    has_main = False

    for name in ("main.py", "__init__.py"):
        candidate = plugin_path / name
        if candidate.is_file():
            has_main = True
            try:
                ast.parse(candidate.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                errors.append(f"Syntax error in {name}: {exc}")

    if not has_main:
        errors.append("No main.py or __init__.py found")

    has_manifest = False
    for name in ("plugin.json", "manifest.json"):
        if (plugin_path / name).is_file():
            has_manifest = True
            try:
                json.loads((plugin_path / name).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception) as exc:
                errors.append(f"Invalid JSON in {name}: {exc}")

    if not has_manifest:
        errors.append("No plugin.json or manifest.json found")

    return errors


def _validate_json_file(path: Path) -> bool:
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except Exception:
        return False


# ------------------------------------------------------------------
# Plugin Health Check
# ------------------------------------------------------------------

def health_check_plugin(
    name: str,
    plugin_manager: Any,
    *,
    package_manager: PackageManager | None = None,
) -> HealthCheckResult:
    """Perform a health check on a plugin, returning pass/fail per category."""
    errors: list[str] = []

    manifest = plugin_manager.get_manifest(name) if plugin_manager else None
    manifest_ok = manifest is not None
    if not manifest_ok:
        errors.append(f"Plugin {name!r} has no manifest registered")
    else:
        manifest_errs = validate_manifest(manifest)
        manifest_ok = len(manifest_errs) == 0
        if not manifest_ok:
            errors.extend(f"Manifest: {e}" for e in manifest_errs)

    plugin = plugin_manager.get_plugin(name) if plugin_manager else None
    source_ok = plugin is not None
    if not source_ok:
        errors.append(f"Plugin {name!r} is not loaded")

    config_ok = True
    if plugin is not None and plugin.context is not None:
        cfg = plugin.context.config
        if cfg.loaded:
            config_errs = cfg.validate()
            config_ok = len(config_errs) == 0
            if not config_ok:
                errors.extend(f"Config: {e}" for e in config_errs)

    permissions_ok = True
    if manifest is not None and manifest.permissions:
        for p in manifest.permissions:
            if not Permission.is_valid(p):
                permissions_ok = False
                errors.append(f"Unknown permission: {p!r}")

    if package_manager is not None:
        installed = package_manager.get_installed(name)
        if installed is not None:
            dir_ok = (Config.PLUGIN_DIR / name).is_dir()
            if not dir_ok:
                errors.append(f"Plugin directory {Config.PLUGIN_DIR / name} not found")

    return HealthCheckResult(
        healthy=manifest_ok and source_ok and config_ok and permissions_ok and len(errors) == 0,
        name=name,
        version=manifest.version if manifest else "unknown",
        manifest_ok=manifest_ok,
        source_ok=source_ok,
        config_ok=config_ok,
        permissions_ok=permissions_ok,
        errors=errors,
    )


# ------------------------------------------------------------------
# Plugin Info Exporter
# ------------------------------------------------------------------

def export_plugin_info(
    name: str,
    plugin_manager: Any,
    *,
    package_manager: PackageManager | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    """Export comprehensive plugin information as a dictionary."""
    manifest = plugin_manager.get_manifest(name) if plugin_manager else None
    plugin = plugin_manager.get_plugin(name) if plugin_manager else None

    info: dict[str, Any] = {
        "name": name,
        "version": manifest.version if manifest else "unknown",
        "description": manifest.description if manifest else "",
        "author": manifest.author if manifest else "",
        "loaded": plugin is not None,
        "enabled": plugin.enabled if plugin else False,
        "capabilities": list(manifest.capabilities) if manifest else [],
        "permissions": list(manifest.permissions) if manifest else [],
        "dependencies": [
            {"name": d.name, "version": d.version}
            for d in (manifest.dependencies if manifest else [])
        ],
        "config_schema": manifest.config_schema if manifest else None,
        "services": [],
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    services: list[str] = []
    if plugin_manager is not None:
        info["services"] = plugin_manager.get_plugin_services(name)

    if package_manager is not None:
        installed = package_manager.get_installed(name)
        if installed is not None:
            info["installed_at"] = installed.installed_at
            info["package_hash"] = installed.package_hash
            info["plugin_dir"] = str(Config.PLUGIN_DIR / name)
        else:
            info["installed_at"] = None
            info["package_hash"] = None
            info["plugin_dir"] = None

    if include_raw and manifest is not None:
        info["raw_manifest"] = {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "min_core_version": manifest.min_core_version,
            "dependencies": [
                {"name": d.name, "version": d.version} for d in manifest.dependencies
            ],
            "capabilities": manifest.capabilities,
            "config_schema": manifest.config_schema,
            "permissions": manifest.permissions,
        }

    return info


# ------------------------------------------------------------------
# Plugin Documentation Generator
# ------------------------------------------------------------------

def generate_plugin_docs(
    name: str,
    plugin_manager: Any,
    *,
    package_manager: PackageManager | None = None,
) -> str:
    """Generate human-readable markdown documentation for a plugin."""
    manifest = plugin_manager.get_manifest(name) if plugin_manager else None
    if manifest is None:
        return f"# Plugin: {name}\n\n*No manifest available.*\n"

    lines: list[str] = []
    lines.append(f"# Plugin: {manifest.name}")
    lines.append("")
    lines.append(f"**Version:** {manifest.version}")
    if manifest.author:
        lines.append(f"**Author:** {manifest.author}")
    if manifest.description:
        lines.append("")
        lines.append(manifest.description)
    lines.append("")

    lines.append("## Dependencies")
    lines.append("")
    if manifest.dependencies:
        for dep in manifest.dependencies:
            lines.append(f"- `{dep.name}` (requires `{dep.version}`)")
    else:
        lines.append("*No dependencies.*")
    lines.append("")

    lines.append("## Capabilities")
    lines.append("")
    if manifest.capabilities:
        for cap in manifest.capabilities:
            lines.append(f"- `{cap}`")
    else:
        lines.append("*No capabilities declared.*")
    lines.append("")

    lines.append("## Permissions")
    lines.append("")
    perm_info = inspect_permissions(manifest)
    if perm_info["declared"]:
        for p in perm_info["known"]:
            lines.append(f"- `{p}`")
        if perm_info["unknown"]:
            lines.append("")
            lines.append("### Unknown Permissions")
            for p in perm_info["unknown"]:
                lines.append(f"- `{p}`")
    else:
        lines.append("*No permissions declared — all permissions granted by default.*")
    lines.append("")

    lines.append("## Configuration")
    lines.append("")
    cfg_info = inspect_config_schema(manifest)
    if cfg_info["has_schema"]:
        if cfg_info["description"]:
            lines.append(cfg_info["description"])
            lines.append("")
        lines.append("| Field | Type | Required | Default | Description |")
        lines.append("|-------|------|----------|---------|-------------|")
        for field in cfg_info["fields"]:
            req = "Yes" if field["required"] else "No"
            default = str(field["default"]) if field["default"] is not None else ""
            desc = field["description"] or ""
            lines.append(
                f"| `{field['name']}` | `{field['type']}` | {req} | "
                f"{default} | {desc} |",
            )
    else:
        lines.append("*No configuration schema defined.*")
    lines.append("")

    lines.append("## Core Requirements")
    lines.append("")
    lines.append(f"- Minimum core version: `{manifest.min_core_version}`")
    lines.append("")

    if package_manager is not None:
        installed = package_manager.get_installed(name)
        if installed is not None:
            lines.append("## Installation Info")
            lines.append("")
            lines.append(f"- Installed: `{installed.installed_at}`")
            lines.append(f"- Package hash: `{installed.package_hash[:16]}...`")
            lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Plugin Validator Service
# ------------------------------------------------------------------

def validate_plugin_project(
    plugin_dir: str | Path,
    *,
    plugin_manager: Any = None,
) -> ValidationResult:
    """Comprehensively validate a plugin project directory.

    Checks manifest validity, source file structure, Python syntax,
    permission declarations, and dependency resolution.
    """
    path = Path(plugin_dir).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not path.is_dir():
        return ValidationResult(valid=False, errors=[f"Directory not found: {path}"])

    manifest_paths = [path / "plugin.json", path / "manifest.json"]
    manifest: PluginManifest | None = None
    manifest_found = False

    for mp in manifest_paths:
        if mp.is_file():
            manifest_found = True
            try:
                data = json.loads(mp.read_text(encoding="utf-8"))
                deps = [PluginDependency(**d) for d in data.get("dependencies", [])]
                manifest = PluginManifest(
                    name=data.get("name", ""),
                    version=str(data.get("version", "1.0.0")),
                    description=data.get("description", ""),
                    author=data.get("author", ""),
                    min_core_version=str(data.get("min_core_version", "0.4.0")),
                    permissions=data.get("permissions", []),
                    capabilities=data.get("capabilities", []),
                    dependencies=deps,
                    config_schema=data.get("config_schema"),
                )
            except Exception as exc:
                errors.append(f"Failed to parse {mp.name}: {exc}")

    if not manifest_found:
        errors.append("No plugin.json or manifest.json found")
    elif manifest is not None:
        manifest_errs = validate_manifest(manifest)
        errors.extend(manifest_errs)

        if not manifest.author:
            warnings.append("No author specified")
        if not manifest.description:
            warnings.append("No description specified")
        if manifest.permissions:
            for p in manifest.permissions:
                if not Permission.is_valid(p):
                    errors.append(f"Unknown permission: {p!r}")

    source_errs = _check_source_files(path)
    errors.extend(source_errs)

    if plugin_manager is not None and manifest is not None:
        for dep in manifest.dependencies:
            resolved = plugin_manager.get_manifest(dep.name)
            if resolved is None:
                warnings.append(f"Dependency {dep.name!r} is not resolved")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ------------------------------------------------------------------
# Developer Helper Utilities
# ------------------------------------------------------------------

def discover_plugin_dirs(
    search_path: str | Path | None = None,
) -> list[Path]:
    """Discover plugin directories in a given path (or Config.PLUGIN_DIR)."""
    base = Path(search_path).resolve() if search_path else Config.PLUGIN_DIR
    if not base.is_dir():
        return []
    results: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        has_manifest = any(
            (entry / name).is_file()
            for name in ("plugin.json", "manifest.json")
        )
        has_source = any(
            (entry / name).is_file()
            for name in ("main.py", "__init__.py")
        )
        if has_manifest or has_source:
            results.append(entry)
    return results


def format_validation_result(result: ValidationResult) -> str:
    """Format a ValidationResult as a human-readable string."""
    lines: list[str] = []
    if result.valid:
        lines.append("VALID")
    else:
        lines.append("INVALID")
    if result.errors:
        lines.append("")
        lines.append("Errors:")
        for err in result.errors:
            lines.append(f"  - {err}")
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in result.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)


def list_plugin_permission_summary(
    plugin_manager: Any,
) -> list[dict[str, Any]]:
    """List all registered plugins with their permission summaries."""
    result: list[dict[str, Any]] = []
    if plugin_manager is None:
        return result
    for name in plugin_manager.list_plugins():
        manifest = plugin_manager.get_manifest(name)
        if manifest is not None:
            perm_info = inspect_permissions(manifest)
            result.append({
                "name": name,
                "version": manifest.version,
                "permissions": perm_info["declared"],
                "summary": perm_info["summary"],
                "has_all": perm_info["has_all"],
            })
    return result


def resolve_plugin_file(
    plugin_dir: str | Path,
    filename: str,
) -> Path | None:
    """Resolve a file within a plugin directory, returning the path or None."""
    base = Path(plugin_dir).resolve()
    target = (base / filename).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target if target.is_file() else None


__all__ = [
    "ConfigInspector",
    "DependencyInspector",
    "HealthCheckResult",
    "PermissionInspector",
    "PluginDiagnosticsResult",
    "PluginDocGenerator",
    "PluginInfoExporter",
    "PluginProject",
    "PluginValidator",
    "ValidationResult",
    "diagnose_plugin",
    "discover_plugin_dirs",
    "export_plugin_info",
    "format_validation_result",
    "generate_manifest",
    "generate_plugin_docs",
    "health_check_plugin",
    "inspect_config_schema",
    "inspect_dependencies",
    "inspect_package",
    "inspect_permissions",
    "list_plugin_permission_summary",
    "manifest_to_json",
    "resolve_plugin_file",
    "scaffold_plugin",
    "validate_plugin_manifest",
    "validate_plugin_project",
]


# ------------------------------------------------------------------
# Backward-compatible class aliases
# ------------------------------------------------------------------

class PluginValidator:
    @staticmethod
    def validate_project(
        plugin_dir: str | Path,
        *,
        plugin_manager: Any = None,
    ) -> ValidationResult:
        return validate_plugin_project(plugin_dir, plugin_manager=plugin_manager)

    @staticmethod
    def validate_manifest(manifest: PluginManifest) -> ValidationResult:
        return validate_plugin_manifest(manifest)


class PermissionInspector:
    @staticmethod
    def inspect(manifest: PluginManifest) -> dict[str, Any]:
        return inspect_permissions(manifest)


class DependencyInspector:
    @staticmethod
    def inspect(
        manifest: PluginManifest,
        *,
        plugin_manager: Any = None,
    ) -> list[dict[str, Any]]:
        return inspect_dependencies(manifest, plugin_manager=plugin_manager)


class ConfigInspector:
    @staticmethod
    def inspect(manifest: PluginManifest) -> dict[str, Any]:
        return inspect_config_schema(manifest)


class PluginInfoExporter:
    @staticmethod
    def export(
        name: str,
        plugin_manager: Any,
        *,
        package_manager: PackageManager | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        return export_plugin_info(
            name, plugin_manager,
            package_manager=package_manager,
            include_raw=include_raw,
        )


class PluginDocGenerator:
    @staticmethod
    def generate(
        name: str,
        plugin_manager: Any,
        *,
        package_manager: PackageManager | None = None,
    ) -> str:
        return generate_plugin_docs(
            name, plugin_manager,
            package_manager=package_manager,
        )
