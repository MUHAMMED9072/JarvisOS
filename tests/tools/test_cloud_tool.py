from __future__ import annotations

from app.tools.cloud_tool import CloudTool


class TestCloudTool:
    def test_name_and_version(self) -> None:
        tool = CloudTool()
        assert tool.name == "cloud_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = CloudTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "action" in names
        assert "provider" in names

    def test_permissions(self) -> None:
        tool = CloudTool()
        assert "tools.cloud.manage" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = CloudTool()
        assert "cloud_operations" in tool.metadata.capabilities

    def test_validate_missing_action(self) -> None:
        tool = CloudTool()
        errors = tool.validate_params({})
        assert any("action" in e for e in errors)

    def test_unknown_action(self) -> None:
        tool = CloudTool()
        result = tool.execute({"action": "nonexistent", "provider": "aws"})
        assert not result.success

    def test_unsupported_provider(self) -> None:
        tool = CloudTool()
        result = tool.execute({"action": "list_instances", "provider": "oracle"})
        assert result.success
        assert result.output["provider"] == "oracle"

    def test_aws_list_unconfigured(self) -> None:
        tool = CloudTool()
        result = tool.execute({"action": "list_instances", "provider": "aws"})
        assert result.success
        assert result.output["provider"] == "aws"

    def test_execution_time_positive_on_failure(self) -> None:
        tool = CloudTool()
        result = tool.execute({"action": "nonexistent", "provider": "aws"})
        assert result.execution_time >= 0

    def test_to_dict(self) -> None:
        tool = CloudTool()
        d = tool.to_dict()
        assert d["name"] == "cloud_tool"
