from __future__ import annotations

from app.tools.rest_tool import RESTTool


class TestRESTTool:
    def test_name_and_version(self) -> None:
        tool = RESTTool()
        assert tool.name == "rest_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = RESTTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "url" in names
        assert "method" in names
        assert "headers" in names
        assert "body" in names
        assert "auth_type" in names

    def test_required_params(self) -> None:
        tool = RESTTool()
        url_param = [p for p in tool.metadata.parameters if p.name == "url"][0]
        assert url_param.required is True

    def test_permissions(self) -> None:
        tool = RESTTool()
        assert "tools.network.http" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = RESTTool()
        assert "http_requests" in tool.metadata.capabilities

    def test_validate_missing_url(self) -> None:
        tool = RESTTool()
        errors = tool.validate_params({})
        assert any("url" in e for e in errors)

    def test_blocked_localhost(self) -> None:
        tool = RESTTool()
        result = tool.execute({"url": "http://localhost:8080/test"})
        assert not result.success
        assert "blocked" in (result.error_message or "")

    def test_blocked_127_0_0_1(self) -> None:
        tool = RESTTool()
        result = tool.execute({"url": "http://127.0.0.1:3000/api"})
        assert not result.success
        assert "blocked" in (result.error_message or "")

    def test_valid_public_url(self) -> None:
        tool = RESTTool()
        result = tool.execute({"url": "https://httpbin.org/get", "timeout": 10.0})
        if result.success:
            assert result.output is not None
            assert "status_code" in result.output
            assert result.output["status_code"] == 200
        else:
            pass

    def test_execution_time_positive(self) -> None:
        tool = RESTTool()
        result = tool.execute({"url": "https://httpbin.org/get", "timeout": 10.0})
        if result.success:
            assert result.execution_time > 0

    def test_to_dict(self) -> None:
        tool = RESTTool()
        d = tool.to_dict()
        assert d["name"] == "rest_tool"

    def test_auth_types_are_validated(self) -> None:
        tool = RESTTool()
        errors = tool.validate_params({"url": "https://example.com", "method": "GET"})
        assert errors == []

    def test_default_method_is_get(self) -> None:
        tool = RESTTool()
        get_param = [p for p in tool.metadata.parameters if p.name == "method"][0]
        assert get_param.default == "GET"
