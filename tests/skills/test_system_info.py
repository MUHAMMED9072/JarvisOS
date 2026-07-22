# tests/skills/test_system_info.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.event_bus import EventBus
from app.core.registry import ServiceRegistry
from app.skills.base import Skill
from app.skills.loader import SkillLoader
from app.skills.manager import SkillManager
from app.skills.result import SkillResult
from app.skills.system.info import SystemInfoSkill


class TestSystemInfoSkill:
    @pytest.fixture
    def skill(self):
        return SystemInfoSkill()

    @pytest.fixture
    def skill_with_registry(self):
        skill = SystemInfoSkill()
        registry = ServiceRegistry()
        skill_manager = SkillManager()
        event_bus = EventBus()
        registry.register("skill_manager", skill_manager)
        registry.register("event_bus", event_bus)
        registry.register("memory", MagicMock())
        registry.register("cortex", MagicMock())
        registry.register("dispatcher", MagicMock())
        skill.setup(registry)
        return skill

    @pytest.fixture
    def mock_request(self):
        return MagicMock()

    def test_skill_attributes(self, skill):
        assert skill.name == "System Info"
        assert skill.intent == "system_info"
        assert skill.version == "1.0.0"
        assert skill.description == "Returns system diagnostics including CPU, RAM, disk, OS, and network status."
        assert skill.author == "JarvisOS"
        assert isinstance(skill, Skill)

    @patch("app.skills.system.info.cpu_usage", return_value="42 %")
    @patch("app.skills.system.info.ram_usage", return_value="65 %")
    @patch("app.skills.system.info.disk_usage", return_value="30 %")
    @patch("app.skills.system.info.operating_system", return_value="Windows 10")
    @patch("app.skills.system.info.python_version", return_value="3.12.0")
    @patch("app.skills.system.info.internet_status", return_value="Connected")
    @patch("app.skills.system.info.current_time", return_value="12:34:56 PM")
    def test_run_success_all_metrics(
        self,
        mock_time,
        mock_internet,
        mock_pyver,
        mock_os,
        mock_disk,
        mock_ram,
        mock_cpu,
        skill_with_registry,
        mock_request,
    ):
        result = skill_with_registry.execute(mock_request)

        assert isinstance(result, SkillResult)
        assert result.success is True
        assert result.skill == "System Info"
        assert result.execution_time >= 0

        data = result.data
        assert data["cpu_usage"] == "42 %"
        assert data["ram_usage"] == "65 %"
        assert data["disk_usage"] == "30 %"
        assert data["os"] == "Windows 10"
        assert data["python_version"] == "3.12.0"
        assert data["internet"] == "Connected"
        assert data["current_time"] == "12:34:56 PM"
        assert data["jarvis_version"] == "0.4.0-alpha"
        assert data["skills_loaded"] >= 0
        assert data["errors"] == []

    @patch("app.skills.system.info.cpu_usage", side_effect=RuntimeError("psutil error"))
    @patch("app.skills.system.info.ram_usage", return_value="65 %")
    @patch("app.skills.system.info.disk_usage", return_value="30 %")
    @patch("app.skills.system.info.operating_system", return_value="Windows 10")
    @patch("app.skills.system.info.python_version", return_value="3.12.0")
    @patch("app.skills.system.info.internet_status", return_value="Connected")
    @patch("app.skills.system.info.current_time", return_value="12:34:56 PM")
    def test_run_partial_failure_cpu(
        self,
        mock_time,
        mock_internet,
        mock_pyver,
        mock_os,
        mock_disk,
        mock_ram,
        mock_cpu,
        skill_with_registry,
        mock_request,
    ):
        result = skill_with_registry.execute(mock_request)

        assert result.success is True
        data = result.data
        assert data["cpu_usage"] == "unavailable"
        assert data["ram_usage"] == "65 %"
        assert data["disk_usage"] == "30 %"
        assert data["os"] == "Windows 10"
        assert len(data["errors"]) == 1
        assert "cpu_usage" in data["errors"][0]

    @patch("app.skills.system.info.cpu_usage", side_effect=RuntimeError("cpu fail"))
    @patch("app.skills.system.info.ram_usage", side_effect=RuntimeError("ram fail"))
    @patch("app.skills.system.info.disk_usage", return_value="30 %")
    @patch("app.skills.system.info.operating_system", return_value="Windows 10")
    @patch("app.skills.system.info.python_version", return_value="3.12.0")
    @patch("app.skills.system.info.internet_status", return_value="Connected")
    @patch("app.skills.system.info.current_time", return_value="12:34:56 PM")
    def test_run_multiple_failures(
        self,
        mock_time,
        mock_internet,
        mock_pyver,
        mock_os,
        mock_disk,
        mock_ram,
        mock_cpu,
        skill_with_registry,
        mock_request,
    ):
        result = skill_with_registry.run(mock_request)

        assert result.success is True
        data = result.data
        assert data["cpu_usage"] == "unavailable"
        assert data["ram_usage"] == "unavailable"
        assert data["disk_usage"] == "30 %"
        assert len(data["errors"]) == 2
        assert any("cpu_usage" in e for e in data["errors"])
        assert any("ram_usage" in e for e in data["errors"])

    @patch("app.skills.system.info.cpu_usage", return_value="42 %")
    @patch("app.skills.system.info.ram_usage", return_value="65 %")
    @patch("app.skills.system.info.disk_usage", return_value="30 %")
    @patch("app.skills.system.info.operating_system", return_value="Windows 10")
    @patch("app.skills.system.info.python_version", return_value="3.12.0")
    @patch("app.skills.system.info.internet_status", return_value="Connected")
    @patch("app.skills.system.info.current_time", return_value="12:34:56 PM")
    def test_run_without_skill_manager(
        self,
        mock_time,
        mock_internet,
        mock_pyver,
        mock_os,
        mock_disk,
        mock_ram,
        mock_cpu,
        skill,
        mock_request,
    ):
        result = skill.run(mock_request)

        assert result.success is True
        assert result.data["skills_loaded"] == 0
        assert any("skill_manager not injected" in e for e in result.data["errors"])

    @patch("app.skills.system.info.cpu_usage", return_value="42 %")
    @patch("app.skills.system.info.ram_usage", return_value="65 %")
    @patch("app.skills.system.info.disk_usage", return_value="30 %")
    @patch("app.skills.system.info.operating_system", return_value="Windows 10")
    @patch("app.skills.system.info.python_version", return_value="3.12.0")
    @patch("app.skills.system.info.internet_status", return_value="Connected")
    @patch("app.skills.system.info.current_time", return_value="12:34:56 PM")
    def test_skill_result_structure(
        self,
        mock_time,
        mock_internet,
        mock_pyver,
        mock_os,
        mock_disk,
        mock_ram,
        mock_cpu,
        skill_with_registry,
        mock_request,
    ):
        result = skill_with_registry.run(mock_request)

        assert hasattr(result, "success")
        assert hasattr(result, "message")
        assert hasattr(result, "data")
        assert hasattr(result, "execution_time")
        assert hasattr(result, "skill")

        assert isinstance(result.data, dict)
        expected_keys = {
            "cpu_usage", "ram_usage", "disk_usage", "os",
            "python_version", "internet", "current_time",
            "jarvis_version", "skills_loaded", "errors"
        }
        assert set(result.data.keys()) == expected_keys
        assert isinstance(result.data["errors"], list)


class TestSystemInfoSkillDiscovery:
    @pytest.fixture
    def registry(self):
        registry = ServiceRegistry()
        skill_manager = SkillManager()
        event_bus = EventBus()
        registry.register("skill_manager", skill_manager)
        registry.register("event_bus", event_bus)
        registry.register("memory", MagicMock())
        registry.register("cortex", MagicMock())
        registry.register("dispatcher", MagicMock())
        return registry

    def test_skill_loader_discovers_system_info(self, registry):
        manager = registry.get("skill_manager")
        loader = SkillLoader()
        loader.load(manager, registry)

        assert "system_info" in manager.skills
        skill = manager.skills["system_info"]
        assert isinstance(skill, SystemInfoSkill)
        assert skill.intent == "system_info"

    def test_skill_manager_get_returns_system_info(self, registry):
        manager = registry.get("skill_manager")
        loader = SkillLoader()
        loader.load(manager, registry)

        skill = manager.get("system_info")
        assert skill is not manager.fallback
        assert skill.intent == "system_info"

    def test_unknown_intent_returns_fallback(self, registry):
        manager = registry.get("skill_manager")
        loader = SkillLoader()
        loader.load(manager, registry)

        skill = manager.get("nonexistent_intent")
        assert skill is manager.fallback
        assert skill.intent == "unknown"