from __future__ import annotations

import tempfile
from pathlib import Path

from app.tools.ssh_tool import SSHTool


class TestSSHTool:
    def test_name_and_version(self) -> None:
        tool = SSHTool()
        assert tool.name == "ssh_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = SSHTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "action" in names
        assert "host" in names
        assert "command" in names

    def test_permissions(self) -> None:
        tool = SSHTool()
        assert "tools.ssh.execute" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = SSHTool()
        assert "ssh_execution" in tool.metadata.capabilities

    def test_validate_missing_action(self) -> None:
        tool = SSHTool()
        errors = tool.validate_params({})
        assert any("action" in e for e in errors)

    def test_validate_missing_host(self) -> None:
        tool = SSHTool()
        errors = tool.validate_params({"action": "exec"})
        assert any("host" in e for e in errors)

    def test_unknown_action(self) -> None:
        tool = SSHTool()
        result = tool.execute({"action": "bogus", "host": "localhost"})
        assert not result.success

    def test_exec_missing_command(self) -> None:
        tool = SSHTool()
        result = tool.execute({"action": "exec", "host": "localhost"})
        assert not result.success
        assert "command" in (result.error_message or "")

    def test_add_key_and_list_keys(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tool = SSHTool(keys_dir=td)
            result = tool.execute({"action": "add_key", "host": "x", "key_name": "test_key", "key_material": "ssh-rsa AAAAB3..."})
            assert result.success
            assert result.output["key_name"] == "test_key"

            result2 = tool.execute({"action": "list_keys", "host": "x"})
            assert result2.success
            assert len(result2.output["keys"]) == 1
            assert result2.output["keys"][0]["name"] == "test_key"

    def test_remove_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tool = SSHTool(keys_dir=td)
            tool.execute({"action": "add_key", "host": "x", "key_name": "remove_me", "key_material": "ssh-rsa AAAAB3..."})
            result = tool.execute({"action": "remove_key", "host": "x", "key_name": "remove_me"})
            assert result.success
            assert result.output["deleted"] is True

    def test_remove_nonexistent_key(self) -> None:
        tool = SSHTool()
        result = tool.execute({"action": "remove_key", "host": "x", "key_name": "no_such_key"})
        assert not result.success

    def test_execution_time_positive(self) -> None:
        tool = SSHTool()
        result = tool.execute({"action": "exec", "host": "localhost", "command": "echo hi"})
        assert result.execution_time >= 0

    def test_to_dict(self) -> None:
        tool = SSHTool()
        d = tool.to_dict()
        assert d["name"] == "ssh_tool"

    def test_upload_missing_params(self) -> None:
        tool = SSHTool()
        result = tool.execute({"action": "upload", "host": "localhost"})
        assert not result.success

    def test_download_missing_params(self) -> None:
        tool = SSHTool()
        result = tool.execute({"action": "download", "host": "localhost"})
        assert not result.success
