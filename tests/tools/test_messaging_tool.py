from __future__ import annotations

from app.tools.messaging_tool import MessagingTool


class TestMessagingTool:
    def test_name_and_version(self) -> None:
        tool = MessagingTool()
        assert tool.name == "messaging_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = MessagingTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "action" in names
        assert "platform" in names
        assert "message" in names

    def test_permissions(self) -> None:
        tool = MessagingTool()
        assert "tools.messaging.send" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = MessagingTool()
        assert "messaging" in tool.metadata.capabilities

    def test_validate_missing_action(self) -> None:
        tool = MessagingTool()
        errors = tool.validate_params({})
        assert any("action" in e for e in errors)

    def test_validate_missing_message(self) -> None:
        tool = MessagingTool()
        errors = tool.validate_params({"action": "send", "platform": "slack"})
        assert any("message" in e for e in errors)

    def test_unknown_action(self) -> None:
        tool = MessagingTool()
        result = tool.execute({"action": "broadcast", "platform": "slack", "message": "hi"})
        assert not result.success

    def test_unsupported_platform(self) -> None:
        tool = MessagingTool()
        result = tool.execute({"action": "send", "platform": "teams", "message": "hi"})
        assert not result.success

    def test_slack_missing_webhook(self) -> None:
        tool = MessagingTool()
        result = tool.execute({"action": "send", "platform": "slack", "message": "hello"})
        assert not result.success

    def test_discord_missing_webhook(self) -> None:
        tool = MessagingTool()
        result = tool.execute({"action": "send", "platform": "discord", "message": "hello"})
        assert not result.success

    def test_telegram_missing_token(self) -> None:
        tool = MessagingTool()
        result = tool.execute({"action": "send", "platform": "telegram", "message": "hello"})
        assert not result.success

    def test_execution_time_positive_on_failure(self) -> None:
        tool = MessagingTool()
        result = tool.execute({"action": "send", "platform": "slack", "message": "test"})
        assert result.execution_time >= 0

    def test_to_dict(self) -> None:
        tool = MessagingTool()
        d = tool.to_dict()
        assert d["name"] == "messaging_tool"
