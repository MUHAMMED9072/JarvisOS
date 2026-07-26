"""Tests for the Plugin Loader Framework."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.plugins.sdk import (
    DiscoveredPlugin,
    Plugin,
    PluginDependency,
    PluginLoader,
    PluginManager,
    PluginManifest,
    validate_manifest,
)


# ==========================================================================
# Helpers
# ==========================================================================


def _make_plugin_dir(
    tmp_path: Path,
    name: str,
    version: str = "1.0.0",
    dependencies: list[dict[str, str]] | None = None,
    min_core_version: str = "0.4.0",
    capabilities: list[str] | None = None,
    has_module: bool = True,
    invalid_json: bool = False,
) -> Path:
    plugin_dir = tmp_path / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    if invalid_json:
        (plugin_dir / "plugin.json").write_text("not json", encoding="utf-8")
    else:
        manifest: dict[str, Any] = {
            "name": name,
            "version": version,
            "min_core_version": min_core_version,
        }
        if dependencies:
            manifest["dependencies"] = dependencies
        if capabilities:
            manifest["capabilities"] = capabilities
        (plugin_dir / "plugin.json").write_text(
            json.dumps(manifest), encoding="utf-8",
        )
    if has_module:
        (plugin_dir / "main.py").write_text(
            f"""from app.plugins.sdk import Plugin

class {name.capitalize().replace("-","")}Plugin(Plugin):
    name = {name!r}
    version = {version!r}
""",
            encoding="utf-8",
        )
    return plugin_dir


class _SimplePlugin(Plugin):
    name = "simple"
    version = "1.0.0"


# ==========================================================================
# Discovery
# ==========================================================================


class TestPluginDiscovery:
    """PluginLoader discovers plugins from configured directories."""

    def test_discover_single_plugin(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "test-plugin")
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        names = loader.discover()
        assert "test-plugin" in names

    def test_discover_multiple_plugins(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "alpha")
        _make_plugin_dir(tmp_path, "beta")
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        names = loader.discover()
        assert "alpha" in names
        assert "beta" in names

    def test_discover_skip_missing_manifest(self, tmp_path: Path):
        (tmp_path / "no-manifest").mkdir()
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        names = loader.discover()
        assert names == []

    def test_discover_skip_invalid_manifest(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "bad", invalid_json=True)
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        names = loader.discover()
        assert names == []

    def test_discover_skip_duplicate(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "dup")
        _make_plugin_dir(tmp_path / "sub" / "dup", "dup")
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        names = loader.discover()
        assert names == ["dup"]
        assert len(loader.list_discovered()) == 1

    def test_discover_empty_directory(self, tmp_path: Path):
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        names = loader.discover()
        assert names == []

    def test_discover_nonexistent_directory(self):
        loader = PluginLoader(PluginManager())
        loader.add_directory("/nonexistent/path")
        names = loader.discover()
        assert names == []

    def test_list_discovered(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "my-plugin")
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        discovered = loader.list_discovered()
        assert "my-plugin" in discovered
        assert isinstance(discovered["my-plugin"], DiscoveredPlugin)

    def test_get_discovered(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "my-plugin")
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        dp = loader.get_discovered("my-plugin")
        assert dp is not None
        assert dp.name == "my-plugin"


# ==========================================================================
# Manifest loading
# ==========================================================================


class TestManifestLoading:
    """PluginLoader loads manifests from plugin.json / manifest.json."""

    def test_loads_plugin_json(self, tmp_path: Path):
        d = _make_plugin_dir(tmp_path, "p1", version="2.0.0")
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        dp = loader.get_discovered("p1")
        assert dp is not None
        assert dp.manifest.version == "2.0.0"

    def test_loads_manifest_json(self, tmp_path: Path):
        plugin_dir = tmp_path / "p1"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text(
            json.dumps({"name": "p1", "version": "1.0.0"}),
            encoding="utf-8",
        )
        (plugin_dir / "main.py").write_text(
            "from app.plugins.sdk import Plugin\n"
            "class P1Plugin(Plugin):\n"
            "    name = 'p1'\n"
            "    version = '1.0.0'\n",
        )
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        assert loader.get_discovered("p1") is not None

    def test_loads_dependencies(self, tmp_path: Path):
        _make_plugin_dir(
            tmp_path, "p1",
            dependencies=[{"name": "dep-a", "version": "1.0.0"}],
        )
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        dp = loader.get_discovered("p1")
        assert dp is not None
        assert len(dp.manifest.dependencies) == 1
        assert dp.manifest.dependencies[0].name == "dep-a"

    def test_loads_capabilities(self, tmp_path: Path):
        _make_plugin_dir(
            tmp_path, "p1", capabilities=["logging", "ai"],
        )
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        dp = loader.get_discovered("p1")
        assert dp is not None
        assert dp.manifest.capabilities == ["logging", "ai"]


# ==========================================================================
# Dependency resolution
# ==========================================================================


class TestDependencyResolution:
    """PluginLoader resolves dependencies in correct order."""

    def test_single_plugin(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "only")
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        order = loader.resolve_dependencies()
        assert order == ["only"]

    def test_independent_plugins(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "a")
        _make_plugin_dir(tmp_path, "b")
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        order = loader.resolve_dependencies()
        assert set(order) == {"a", "b"}

    def test_dependency_order(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "depended")
        _make_plugin_dir(
            tmp_path, "dependent",
            dependencies=[{"name": "depended", "version": "1.0.0"}],
        )
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        order = loader.resolve_dependencies()
        assert order.index("depended") < order.index("dependent")

    def test_chained_dependencies(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "base")
        _make_plugin_dir(
            tmp_path, "middle",
            dependencies=[{"name": "base", "version": "1.0.0"}],
        )
        _make_plugin_dir(
            tmp_path, "top",
            dependencies=[{"name": "middle", "version": "1.0.0"}],
        )
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        order = loader.resolve_dependencies()
        assert order.index("base") < order.index("middle")
        assert order.index("middle") < order.index("top")

    def test_missing_dependency_skipped(self, tmp_path: Path):
        _make_plugin_dir(
            tmp_path, "orphan",
            dependencies=[{"name": "ghost", "version": "1.0.0"}],
        )
        loader = PluginLoader(PluginManager())
        loader.add_directory(tmp_path)
        loader.discover()
        order = loader.resolve_dependencies()
        assert "orphan" in order


# ==========================================================================
# Load all
# ==========================================================================


class TestLoadAll:
    """PluginLoader.load_all registers, loads, and enables plugins."""

    def test_load_single_plugin(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "hello")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loaded = loader.load_all()
        assert "hello" in loaded
        assert mgr.get_plugin("hello") is not None
        assert mgr.get_plugin("hello").enabled is True

    def test_load_multiple_plugins(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "a")
        _make_plugin_dir(tmp_path, "b")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loaded = loader.load_all()
        assert "a" in loaded
        assert "b" in loaded

    def test_load_skips_invalid_manifest(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "good")
        _make_plugin_dir(tmp_path, "bad", invalid_json=True)
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loaded = loader.load_all()
        assert "good" in loaded
        assert "bad" not in loaded

    def test_load_without_enable(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "off")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loaded = loader.load_all(enable=False)
        assert "off" in loaded
        assert mgr.get_plugin("off").enabled is False

    def test_load_enabled_by_default(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "on")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loader.load_all()
        assert mgr.get_plugin("on").enabled is True


# ==========================================================================
# Unload
# ==========================================================================


class TestUnload:
    """PluginLoader.unload removes a plugin cleanly."""

    def test_unload_loaded_plugin(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "gone")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loader.load_all()
        assert mgr.get_plugin("gone") is not None
        result = loader.unload("gone")
        assert result is True
        assert mgr.get_plugin("gone") is None

    def test_unload_not_discovered(self):
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        result = loader.unload("ghost")
        assert result is False

    def test_unload_calls_lifecycle(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "bye")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loader.load_all()
        loader.unload("bye")
        assert mgr.get_plugin("bye") is None


# ==========================================================================
# Hot reload
# ==========================================================================


class TestHotReload:
    """PluginLoader.reload re-imports and re-enables a plugin."""

    def test_reload_loaded_plugin(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "refresh")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loader.load_all()
        result = loader.reload("refresh")
        assert result is True

    def test_reload_not_discovered(self):
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        result = loader.reload("ghost")
        assert result is False

    def test_reload_keeps_enabled(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "stay-on")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loader.load_all()
        loader.reload("stay-on")
        assert mgr.get_plugin("stay-on") is not None
        assert mgr.get_plugin("stay-on").enabled is True


# ==========================================================================
# Error handling
# ==========================================================================


class TestErrorHandling:
    """PluginLoader handles errors gracefully."""

    def test_load_no_module(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "nomod", has_module=False)
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loaded = loader.load_all()
        assert "nomod" not in loaded

    def test_load_bad_module(self, tmp_path: Path):
        plugin_dir = tmp_path / "broken"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "broken", "version": "1.0.0"}),
        )
        (plugin_dir / "main.py").write_text(
            "import does_not_exist_xyz\n",
        )
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loaded = loader.load_all()
        assert "broken" not in loaded

    def test_version_mismatch_fails(self, tmp_path: Path):
        _make_plugin_dir(
            tmp_path, "oldy", min_core_version="99.0.0",
        )
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loaded = loader.load_all()
        assert "oldy" not in loaded


# ==========================================================================
# Duplicate detection
# ==========================================================================


class TestDuplicateDetection:
    """PluginLoader prevents duplicate plugin registrations."""

    def test_duplicate_name_across_dirs(self, tmp_path: Path):
        d1 = tmp_path / "dir1"
        d2 = tmp_path / "dir2"
        d1.mkdir()
        d2.mkdir()
        _make_plugin_dir(d1, "dup")
        _make_plugin_dir(d2, "dup")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(d1)
        loader.add_directory(d2)
        names = loader.discover()
        assert names == ["dup"]

    def test_duplicate_in_manager(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "twice")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loader.load_all()
        new_loader = PluginLoader(mgr)
        new_loader.add_directory(tmp_path)
        loaded = new_loader.load_all()
        assert "twice" not in loaded


# ==========================================================================
# Failure isolation
# ==========================================================================


class TestFailureIsolation:
    """One failing plugin does not prevent others from loading."""

    def test_bad_plugin_does_not_block_good(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "good")
        _make_plugin_dir(
            tmp_path, "bad", has_module=False,
        )
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(tmp_path)
        loaded = loader.load_all()
        assert "good" in loaded
        assert "bad" not in loaded


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestBackwardCompatibility:
    """PluginLoader exports match expected public API."""

    def test_plugin_loader_importable(self):
        from app.plugins import PluginLoader
        assert PluginLoader is not None

    def test_discovered_plugin_importable(self):
        from app.plugins import DiscoveredPlugin
        assert DiscoveredPlugin is not None

    def test_loader_reuses_manager(self):
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        assert loader._manager is mgr

    def test_loader_add_directory_accepts_string(self, tmp_path: Path):
        _make_plugin_dir(tmp_path, "str")
        mgr = PluginManager()
        loader = PluginLoader(mgr)
        loader.add_directory(str(tmp_path))
        names = loader.discover()
        assert "str" in names
