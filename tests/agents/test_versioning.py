from __future__ import annotations

import pytest

from app.agents.versioning import AgentVersionManager, Version


class TestVersion:
    def test_semver(self):
        v = Version(agent_id="a1", major=1, minor=2, patch=3)
        assert v.semver == "1.2.3"

    def test_to_dict(self):
        v = Version(agent_id="a1", major=2, minor=0, patch=1, snapshot={"key": "val"})
        d = v.to_dict()
        assert d["semver"] == "2.0.1"
        assert d["snapshot"]["key"] == "val"


class TestAgentVersionManager:
    @pytest.fixture
    def mgr(self):
        return AgentVersionManager()

    def test_create_first_version(self, mgr):
        v = mgr.create_version("agent-1", snapshot={"name": "agent-1"})
        assert v.semver == "1.0.0"
        assert v.changelog == "Initial version"

    def test_create_second_version_minor(self, mgr):
        mgr.create_version("agent-1", snapshot={"name": "agent-1"})
        v2 = mgr.create_version("agent-1", snapshot={"name": "agent-1-v2"}, changelog="Updated")
        assert v2.semver == "1.1.0"

    def test_create_major_bump(self, mgr):
        mgr.create_version("agent-1")
        v = mgr.create_version("agent-1", bump="major")
        assert v.semver == "2.0.0"

    def test_create_patch_bump(self, mgr):
        mgr.create_version("agent-1")
        v = mgr.create_version("agent-1", bump="patch")
        assert v.semver == "1.0.1"

    def test_get_current(self, mgr):
        mgr.create_version("agent-1")
        v = mgr.get_current("agent-1")
        assert v is not None
        assert v.semver == "1.0.0"

    def test_get_current_nonexistent(self, mgr):
        assert mgr.get_current("nobody") is None

    def test_get_version(self, mgr):
        mgr.create_version("agent-1")
        v = mgr.get_version("agent-1", "1.0.0")
        assert v is not None

    def test_get_version_nonexistent(self, mgr):
        assert mgr.get_version("agent-1", "9.9.9") is None

    def test_list_versions(self, mgr):
        mgr.create_version("agent-1")
        mgr.create_version("agent-1")
        mgr.create_version("agent-1")
        versions = mgr.list_versions("agent-1")
        assert len(versions) == 3
        assert versions[0].semver == "1.0.0"
        assert versions[-1].semver == "1.2.0"

    def test_list_versions_empty(self, mgr):
        assert mgr.list_versions("nobody") == []

    def test_diff(self, mgr):
        mgr.create_version("agent-1", snapshot={"key": "old_value", "unchanged": "x"})
        mgr.create_version("agent-1", snapshot={"key": "new_value", "added_key": "y", "unchanged": "x"})
        d = mgr.diff("agent-1", "1.0.0", "1.1.0")
        assert d["changed"]["key"]["from"] == "old_value"
        assert d["changed"]["key"]["to"] == "new_value"
        assert "added_key" in d["added"]
        assert d["agent_id"] == "agent-1"

    def test_diff_nonexistent(self, mgr):
        d = mgr.diff("agent-1", "1.0.0", "2.0.0")
        assert "error" in d

    def test_rollback(self, mgr):
        mgr.create_version("agent-1", snapshot={"version": 1})
        mgr.create_version("agent-1", snapshot={"version": 2})
        mgr.create_version("agent-1", snapshot={"version": 3})
        # rollback to 1.0.0
        rolled = mgr.rollback("agent-1", "1.0.0")
        assert rolled is not None
        assert rolled.semver == "1.0.0"
        assert rolled.snapshot["version"] == 1
        assert "Rolled back to" in rolled.changelog
        # current should be the rollback version
        current = mgr.get_current("agent-1")
        assert current.semver == "1.0.0"

    def test_rollback_nonexistent(self, mgr):
        assert mgr.rollback("agent-1", "9.9.9") is None

    def test_set_compatibility(self, mgr):
        mgr.create_version("agent-1")
        assert mgr.set_compatibility("agent-1", "1.0.0", ["1.0", "2.0"]) is True
        assert mgr.is_compatible("agent-1", "1.0") is True
        assert mgr.is_compatible("agent-1", "3.0") is False

    def test_set_compatibility_nonexistent(self, mgr):
        assert mgr.set_compatibility("agent-1", "9.9.9", ["1.0"]) is False

    def test_is_compatible_no_agent(self, mgr):
        assert mgr.is_compatible("nobody", "1.0") is False

    def test_health(self, mgr):
        mgr.create_version("agent-1")
        mgr.create_version("agent-2")
        h = mgr.health()
        assert h["alive"] is True
        assert h["tracked_agents"] == 2
        assert h["total_versions"] == 2


class TestAgentVersionManagerConcurrency:
    def test_concurrent_create(self):
        import threading
        mgr = AgentVersionManager()
        barrier = threading.Barrier(5)
        results: list[bool] = [False] * 5

        def create(idx: int) -> None:
            barrier.wait()
            mgr.create_version("agent-1", snapshot={"idx": idx})
            results[idx] = True

        threads = [threading.Thread(target=create, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(results)
        assert len(mgr.list_versions("agent-1")) == 5
