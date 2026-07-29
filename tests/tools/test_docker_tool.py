from __future__ import annotations

import subprocess

import pytest

from app.tools.docker_tool import DockerTool


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


SKIP_DOCKER = pytest.mark.skipif(not _docker_available(), reason="docker not available on PATH")


class TestDockerTool:
    def test_name_and_version(self) -> None:
        tool = DockerTool()
        assert tool.name == "docker_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = DockerTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "action" in names
        assert "image" in names
        assert "container_name" in names
        assert "timeout" in names

    def test_required_params(self) -> None:
        tool = DockerTool()
        assert tool.metadata.parameters[0].required is True

    def test_permissions(self) -> None:
        tool = DockerTool()
        assert "tools.docker.manage" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = DockerTool()
        assert "docker_operations" in tool.metadata.capabilities

    def test_validate_missing_action(self) -> None:
        tool = DockerTool()
        errors = tool.validate_params({})
        assert any("action" in e for e in errors)

    def test_unknown_action(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "unknown_action_xyz"})
        assert not result.success
        assert "unknown" in (result.error_message or "").lower()

    def test_pull_without_image(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "pull"})
        assert not result.success
        assert "image" in (result.error_message or "")

    def test_stop_without_container(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "stop"})
        assert not result.success
        assert "container_name" in (result.error_message or "")

    def test_logs_without_container(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "logs"})
        assert not result.success
        assert "container_name" in (result.error_message or "")

    def test_exec_without_container(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "exec"})
        assert not result.success
        assert "container_name" in (result.error_message or "")

    def test_exec_without_command(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "exec", "container_name": "test"})
        assert not result.success
        assert "command" in (result.error_message or "")

    def test_rm_without_container(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "rm"})
        assert not result.success
        assert "container_name" in (result.error_message or "")

    def test_rmi_without_image(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "rmi"})
        assert not result.success
        assert "image" in (result.error_message or "")

    def test_ps_handles_missing_docker(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "ps"})
        if not _docker_available():
            assert not result.success
            assert "docker" in (result.error_message or "").lower()
        else:
            pass

    @SKIP_DOCKER
    def test_ps_with_docker(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "ps"})
        assert result.success
        assert "containers" in result.output

    @SKIP_DOCKER
    def test_images_with_docker(self) -> None:
        tool = DockerTool()
        result = tool.execute({"action": "images"})
        assert result.success

    def test_to_dict(self) -> None:
        tool = DockerTool()
        d = tool.to_dict()
        assert d["name"] == "docker_tool"
