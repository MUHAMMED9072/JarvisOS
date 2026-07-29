from __future__ import annotations

import json
import os
import tempfile

from app.agents.marketplace.packaging import AgentPackage, PackageError, PackageVerificationResult
from app.agents.marketplace.registry import MarketplaceEntry, MarketplaceRegistry, RemoteRepository


_SAMPLE_MANIFEST = {
    "name": "test_pkg",
    "version": "1.0.0",
    "description": "Test package",
    "agent_type": "domain",
    "capabilities": [{"name": "greet", "description": "Greets"}],
    "entry_point": "module:TestAgent",
}


class TestAgentPackage:
    def test_build_and_load_roundtrip(self) -> None:
        pkg = AgentPackage(_SAMPLE_MANIFEST)
        pkg.add_code_file("main.py", "print('hello')")
        pkg.add_test_file("test_main.py", "def test(): pass")
        pkg.add_asset("icon.png", b"fake_png_data")

        data = pkg.build()
        loaded = AgentPackage.load(data)
        assert loaded.name == "test_pkg"
        assert loaded.version == "1.0.0"

    def test_verify_valid_package(self) -> None:
        pkg = AgentPackage(_SAMPLE_MANIFEST)
        pkg.add_code_file("main.py", "print('ok')")
        result = pkg.verify()
        assert result.valid

    def test_verify_invalid_manifest(self) -> None:
        pkg = AgentPackage({})
        result = pkg.verify()
        assert not result.valid
        assert len(result.errors) > 0

    def test_extract_to_directory(self) -> None:
        pkg = AgentPackage(_SAMPLE_MANIFEST)
        pkg.add_code_file("main.py", "code_content")
        pkg.add_test_file("test.py", "test_content")
        pkg.add_asset("data.txt", b"binary_content")

        with tempfile.TemporaryDirectory() as td:
            count = pkg.extract_to(td)
            assert count == 3
            assert os.path.exists(os.path.join(td, "code", "main.py"))
            assert os.path.exists(os.path.join(td, "tests", "test.py"))
            assert os.path.exists(os.path.join(td, "assets", "data.txt"))

    def test_load_bad_zip_raises_error(self) -> None:
        import pytest
        with pytest.raises(PackageError):
            AgentPackage.load(b"not a zip file")

    def test_package_format(self) -> None:
        pkg = AgentPackage(_SAMPLE_MANIFEST)
        fmt = pkg.to_package_format()
        assert fmt.package_version == "1.0"
        assert fmt.manifest["name"] == "test_pkg"

    def test_build_includes_checksums(self) -> None:
        import zipfile, io
        pkg = AgentPackage(_SAMPLE_MANIFEST)
        pkg.add_code_file("main.py", "x")
        data = pkg.build()
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            assert "checksums.sha256" in zf.namelist()

    def test_signature_handling(self) -> None:
        pkg = AgentPackage(_SAMPLE_MANIFEST)
        pkg.set_signature("FAKE-SIGNATURE")
        result = pkg.verify()
        assert result.signature_ok

    def test_manifest_getters(self) -> None:
        pkg = AgentPackage(_SAMPLE_MANIFEST)
        assert pkg.name == "test_pkg"
        assert pkg.version == "1.0.0"


class TestMarketplaceRegistry:
    def test_register_and_get(self) -> None:
        reg = MarketplaceRegistry(storage_path=tempfile.mktemp())
        entry = MarketplaceEntry(package_name="pkg_a", version="1.0.0", agent_type="domain")
        reg.register(entry)
        retrieved = reg.get("pkg_a", "1.0.0")
        assert retrieved is not None
        assert retrieved.package_name == "pkg_a"

    def test_get_latest_version(self) -> None:
        reg = MarketplaceRegistry(storage_path=tempfile.mktemp())
        reg.register(MarketplaceEntry(package_name="pkg_a", version="1.0.0", agent_type="domain"))
        reg.register(MarketplaceEntry(package_name="pkg_a", version="2.0.0", agent_type="domain"))
        latest = reg.get("pkg_a")
        assert latest is not None
        assert latest.version == "2.0.0"

    def test_search(self) -> None:
        reg = MarketplaceRegistry(storage_path=tempfile.mktemp())
        reg.register(MarketplaceEntry(package_name="hello_world", version="1.0", agent_type="domain"))
        reg.register(MarketplaceEntry(package_name="goodbye", version="1.0", agent_type="domain"))
        results = reg.search("hello")
        assert len(results) == 1
        assert results[0].package_name == "hello_world"

    def test_list_by_type(self) -> None:
        reg = MarketplaceRegistry(storage_path=tempfile.mktemp())
        reg.register(MarketplaceEntry(package_name="a", version="1.0", agent_type="system"))
        reg.register(MarketplaceEntry(package_name="b", version="1.0", agent_type="domain"))
        system_pkgs = reg.list_by_type("system")
        assert len(system_pkgs) == 1

    def test_remove_by_version(self) -> None:
        reg = MarketplaceRegistry(storage_path=tempfile.mktemp())
        reg.register(MarketplaceEntry(package_name="pkg", version="1.0", agent_type="domain"))
        assert reg.remove("pkg", "1.0")
        assert reg.get("pkg", "1.0") is None

    def test_remove_all_versions(self) -> None:
        reg = MarketplaceRegistry(storage_path=tempfile.mktemp())
        reg.register(MarketplaceEntry(package_name="pkg", version="1.0", agent_type="domain"))
        reg.register(MarketplaceEntry(package_name="pkg", version="2.0", agent_type="domain"))
        assert reg.remove("pkg")
        assert reg.count() == 0

    def test_repository_management(self) -> None:
        reg = MarketplaceRegistry(storage_path=tempfile.mktemp())
        repo = RemoteRepository(url="https://example.com/repo", name="example")
        reg.add_repository(repo)
        repos = reg.list_repositories()
        assert len(repos) == 1
        assert reg.remove_repository("https://example.com/repo")
        assert len(reg.list_repositories()) == 0

    def test_health(self) -> None:
        reg = MarketplaceRegistry(storage_path=tempfile.mktemp())
        h = reg.health()
        assert h["alive"]

    def test_remote_sync_fails_for_unregistered(self) -> None:
        reg = MarketplaceRegistry(storage_path=tempfile.mktemp())
        import pytest
        with pytest.raises(Exception):
            reg.sync_repository("https://unknown.example.com")
