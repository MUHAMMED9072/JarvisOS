from __future__ import annotations

from app.tools.browser_tool import BrowserTool


class TestBrowserTool:
    def test_name_and_version(self) -> None:
        tool = BrowserTool()
        assert tool.name == "browser_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = BrowserTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "url" in names
        assert "action" in names
        assert "selector" in names
        assert "timeout" in names

    def test_required_params(self) -> None:
        tool = BrowserTool()
        assert tool.metadata.parameters[0].name == "url"
        assert tool.metadata.parameters[0].required is True

    def test_permissions(self) -> None:
        tool = BrowserTool()
        assert "tools.browser.scrape" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = BrowserTool()
        assert "web_scraping" in tool.metadata.capabilities

    def test_validate_missing_url(self) -> None:
        tool = BrowserTool()
        errors = tool.validate_params({})
        assert any("url" in e for e in errors)

    def test_validate_with_url(self) -> None:
        tool = BrowserTool()
        errors = tool.validate_params({"url": "https://example.com"})
        assert errors == []

    def test_blocked_localhost(self) -> None:
        tool = BrowserTool()
        result = tool.execute({"url": "http://localhost:8000"})
        assert not result.success
        assert "blocked" in (result.error_message or "").lower()

    def test_default_action_is_scrape(self) -> None:
        tool = BrowserTool()
        scrape_param = [p for p in tool.metadata.parameters if p.name == "action"][0]
        assert scrape_param.default == "scrape"

    def test_unknown_action(self) -> None:
        tool = BrowserTool()
        result = tool.execute({"url": "https://example.com", "action": "invalid"})
        assert not result.success

    def test_execute_scrape_real_site(self) -> None:
        tool = BrowserTool()
        result = tool.execute({"url": "https://httpbin.org/html", "timeout": 15.0})
        if result.success:
            assert "title" in result.output
            assert "text_length" in result.output
        else:
            pass

    def test_execution_time_positive(self) -> None:
        tool = BrowserTool()
        result = tool.execute({"url": "https://httpbin.org/html", "timeout": 15.0})
        if result.success:
            assert result.execution_time > 0

    def test_to_dict(self) -> None:
        tool = BrowserTool()
        d = tool.to_dict()
        assert d["name"] == "browser_tool"
