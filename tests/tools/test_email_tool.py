from __future__ import annotations

from app.tools.email_tool import EmailTool


class TestEmailTool:
    def test_name_and_version(self) -> None:
        tool = EmailTool()
        assert tool.name == "email_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = EmailTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "action" in names
        assert "smtp_server" in names
        assert "from_addr" in names
        assert "to_addrs" in names
        assert "subject" in names
        assert "body" in names

    def test_permissions(self) -> None:
        tool = EmailTool()
        assert "tools.email.send" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = EmailTool()
        assert "email_operations" in tool.metadata.capabilities

    def test_validate_missing_action(self) -> None:
        tool = EmailTool()
        errors = tool.validate_params({})
        assert any("action" in e for e in errors)

    def test_validate_missing_smtp_server(self) -> None:
        tool = EmailTool()
        errors = tool.validate_params({"action": "send"})
        assert any("smtp_server" in e for e in errors)

    def test_unknown_action(self) -> None:
        tool = EmailTool()
        result = tool.execute({"action": "purge", "smtp_server": "smtp.example.com"})
        assert not result.success

    def test_read_action_not_implemented(self) -> None:
        tool = EmailTool()
        result = tool.execute({"action": "read", "smtp_server": "imap.example.com"})
        assert not result.success

    def test_send_missing_auth(self) -> None:
        tool = EmailTool()
        result = tool.execute({
            "action": "send",
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
            "from_addr": "test@example.com",
            "to_addrs": "recipient@example.com",
            "subject": "Test",
            "body": "Hello",
        })
        assert not result.success

    def test_execution_time_positive_on_failure(self) -> None:
        tool = EmailTool()
        result = tool.execute({"action": "send", "smtp_server": "smtp.example.com", "from_addr": "a@b.com", "to_addrs": "c@d.com"})
        assert result.execution_time >= 0

    def test_to_dict(self) -> None:
        tool = EmailTool()
        d = tool.to_dict()
        assert d["name"] == "email_tool"
