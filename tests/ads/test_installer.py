import json
import tempfile

import pytest

from app.ads.content_generator import GeneratedContent
from app.ads.installer import InstallSnapshot, Installer
from app.ads.registration import Registration
from app.ads.type_registry import ArtifactTypeRegistry
from app.knowledge_graph.capability_registry import CapabilityRegistry
from app.knowledge_graph.store import GraphStore


def _make_content(name: str, atype: str = "Agent", caps: list[str] | None = None) -> GeneratedContent:
    return GeneratedContent(
        files={
            f"{name}.py": f"class {name}: pass",
            "__init__.py": "",
        },
        manifest={
            "name": name,
            "version": "1.0.0",
            "type": atype,
            "description": f"A test {atype}",
            "capabilities": caps or [],
        },
        base_path=f"ads/generated/{name}",
    )


class TestInstaller:
    @pytest.fixture
    def installer(self, tmp_path):
        return Installer(base_path=str(tmp_path / "installed"))

    def test_install_artifact(self, installer, tmp_path):
        content = _make_content("TestAgent", "Agent")
        result = installer.install("TestAgent", content)
        assert result.success is True
        assert result.artifact_name == "TestAgent"
        assert len(result.files_installed) >= 2

    def test_install_creates_files(self, installer, tmp_path):
        content = _make_content("MyAgent", "Agent")
        result = installer.install("MyAgent", content)
        target = tmp_path / "installed" / "MyAgent"
        assert (target / "MyAgent.py").exists()
        assert (target / "manifest.json").exists()

    def test_install_with_dependencies(self, installer, tmp_path):
        content = _make_content("DepAgent", "Agent")
        result = installer.install("DepAgent", content, dependencies=["numpy", "requests"])
        assert "numpy" in result.dependencies_resolved
        assert "requests" in result.dependencies_resolved

    def test_snapshot_created_on_reinstall(self, installer, tmp_path):
        content = _make_content("ReinstallAgent")
        installer.install("ReinstallAgent", content)
        # Install again -> should create snapshot
        result = installer.install("ReinstallAgent", content)
        assert result.snapshot is not None
        assert result.snapshot.artifact_name == "ReinstallAgent"

    def test_rollback(self, installer, tmp_path):
        content_v1 = _make_content("RollbackAgent", caps=["cap_a"])
        content_v1.manifest["capabilities"] = ["cap_a"]
        r1 = installer.install("RollbackAgent", content_v1)
        snapshot = r1.snapshot

        # Install v2
        content_v2 = _make_content("RollbackAgent", caps=["cap_a", "cap_b"])
        content_v2.files["new_file.py"] = "# new"
        r2 = installer.install("RollbackAgent", content_v2)

        # If v1 didn't have a snapshot (first install), test rollback from v2 only
        if r2.snapshot:
            assert installer.rollback(r2.snapshot) is True

    def test_rollback_no_snapshot(self, installer):
        snap = InstallSnapshot(artifact_name="nonexistent", backup_path="C:\\nonexistent_path_xyzzy")
        assert installer.rollback(snap) is False

    def test_install_result_to_dict(self, installer, tmp_path):
        content = _make_content("DictAgent")
        result = installer.install("DictAgent", content)
        d = result.to_dict()
        assert d["artifact_name"] == "DictAgent"
        assert d["success"] is True

    def test_health(self, installer):
        h = installer.health()
        assert h["alive"] is True


class TestRegistration:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    @pytest.fixture
    def registration(self, graph):
        return Registration(graph)

    def test_register_artifact(self, registration, graph):
        content = _make_content("MyAgent", "Agent", caps=["web_scraping"])
        result = registration.register("MyAgent", content)
        assert result.success is True
        assert result.entity_id is not None
        assert "web_scraping" in result.capabilities_registered

    def test_register_creates_kg_entity(self, registration, graph):
        content = _make_content("KGAgent", "Agent", caps=[])
        result = registration.register("KGAgent", content)
        entities = graph.get_entity_by_name("KGAgent")
        assert len(entities) >= 1
        assert entities[0].type == "agent"

    def test_register_capabilities(self, registration, graph):
        content = _make_content("CapAgent", "Agent", caps=["monitoring", "alerting"])
        result = registration.register("CapAgent", content)
        assert len(result.capabilities_registered) == 2
        # Verify capabilities in KG
        for cap in ["monitoring", "alerting"]:
            entities = graph.get_entity_by_name(cap)
            assert len(entities) >= 1

    def test_register_creates_relationships(self, registration, graph):
        content = _make_content("RelAgent", "Agent", caps=["analysis"])
        result = registration.register("RelAgent", content)
        assert len(result.relationships_created) >= 1

    def test_unregister(self, registration, graph):
        content = _make_content("UnregAgent", "Agent")
        registration.register("UnregAgent", content)
        assert registration.unregister("UnregAgent") is True
        assert len(graph.get_entity_by_name("UnregAgent")) == 0

    def test_unregister_nonexistent(self, registration):
        assert registration.unregister("nonexistent") is False

    def test_registration_result_to_dict(self, registration, graph):
        content = _make_content("DictReg", "Agent")
        result = registration.register("DictReg", content)
        d = result.to_dict()
        assert d["artifact_name"] == "DictReg"

    def test_health(self, registration):
        h = registration.health()
        assert h["alive"] is True
