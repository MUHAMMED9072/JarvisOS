from __future__ import annotations

import json
import tempfile

from app.agents.marketplace.importer import PackageImporter
from app.agents.marketplace.packaging import AgentPackage
from app.agents.marketplace.registry import MarketplaceRegistry
from app.agents.registry import AgentRegistry
from app.knowledge_graph.store import GraphStore


_SAMPLE_MANIFEST = {
    "name": "importer_test",
    "version": "1.0.0",
    "description": "Test import",
    "agent_type": "domain",
    "capabilities": [{"name": "test", "description": "test cap"}],
    "entry_point": "module:TestAgent",
}


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


class TestPackageImporter:
    def test_import_valid_package(self) -> None:
        store = _make_store()
        agent_reg = AgentRegistry(store)
        mreg = MarketplaceRegistry(storage_path=tempfile.mktemp())

        pkg = AgentPackage(_SAMPLE_MANIFEST)
        pkg.add_code_file("main.py", "x = 1")
        pkg.add_test_file("test_main.py", "def test(): pass")
        package_bytes = pkg.build()

        importer = PackageImporter(agent_reg, mreg, install_dir=tempfile.mktemp())
        result = importer.import_package(package_bytes)
        assert result.success
        assert result.agent_name == "importer_test"

    def test_import_corrupted_package(self) -> None:
        store = _make_store()
        agent_reg = AgentRegistry(store)
        importer = PackageImporter(agent_reg, install_dir=tempfile.mktemp())
        result = importer.import_package(b"not a zip file")
        assert not result.success

    def test_import_twice_fails(self) -> None:
        store = _make_store()
        agent_reg = AgentRegistry(store)
        install_dir = tempfile.mktemp()

        pkg = AgentPackage(_SAMPLE_MANIFEST)
        pkg.add_code_file("main.py", "x = 1")
        data = pkg.build()

        importer = PackageImporter(agent_reg, install_dir=install_dir)
        r1 = importer.import_package(data)
        assert r1.success

        r2 = importer.import_package(data)
        assert not r2.success
        assert "already installed" in r2.error_message

    def test_export_package_fails_if_not_found(self) -> None:
        store = _make_store()
        agent_reg = AgentRegistry(store)
        importer = PackageImporter(agent_reg, install_dir=tempfile.mktemp())
        from app.agents.marketplace.packaging import PackageError
        import pytest
        with pytest.raises(PackageError):
            importer.export_package("nonexistent")

    def test_result_to_dict(self) -> None:
        from app.agents.marketplace.importer import PackageImportResult
        r = PackageImportResult(success=True, agent_name="test", agent_version="1.0", files_installed=3, registered=True)
        d = r.to_dict()
        assert d["success"]
        assert d["agent_name"] == "test"
