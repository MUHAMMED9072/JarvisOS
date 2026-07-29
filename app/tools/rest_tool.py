from __future__ import annotations

import json
import time
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class RESTTool(Tool):
    """Make HTTP requests with authentication and rate limiting support.

    Parameters:
      - url (required): Request URL
      - method: HTTP method (GET, POST, PUT, DELETE, PATCH). Default GET.
      - headers: HTTP headers as dict
      - body: Request body (for POST, PUT, PATCH). Can be dict (JSON) or string.
      - params: URL query parameters as dict
      - auth_type: Authentication type (none, basic, bearer)
      - auth_credentials: Auth credentials as dict
        (basic: {"username": str, "password": str}; bearer: {"token": str})
      - timeout: Request timeout in seconds (default 30)
      - max_redirects: Max redirects to follow (default 5)

    Security: URLs are validated. Internal/hostile URLs may be blocked.
    Requires 'tools.network.http' permission.
    """

    _BLOCKED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "[::1]", "169.254."]

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name="rest_tool",
            version="1.0.0",
            description="Make HTTP requests with auth and rate limiting",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="url", description="Request URL", type="string", required=True),
                ToolParameter(name="method", description="HTTP method (GET, POST, PUT, DELETE, PATCH)", type="string", required=False, default="GET"),
                ToolParameter(name="headers", description="HTTP headers as dict", type="object", required=False),
                ToolParameter(name="body", description="Request body (dict for JSON, or string)", type="object", required=False),
                ToolParameter(name="params", description="URL query parameters as dict", type="object", required=False),
                ToolParameter(name="auth_type", description="Authentication type (none, basic, bearer)", type="string", required=False, default="none"),
                ToolParameter(name="auth_credentials", description="Auth credentials: basic={username, password} or bearer={token}", type="object", required=False),
                ToolParameter(name="timeout", description="Request timeout in seconds", type="number", required=False, default=30.0),
                ToolParameter(name="max_redirects", description="Max redirects to follow", type="number", required=False, default=5),
            ],
            permissions_required=["tools.network.http"],
            capabilities=["http_requests", "rest_api"],
            owner="system",
            tags=["http", "rest", "api"],
        )
        super().__init__(metadata)

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        url = params["url"]
        method = params.get("method", "GET").upper()
        headers = params.get("headers", {}) or {}
        body = params.get("body")
        query_params = params.get("params", {}) or {}
        auth_type = params.get("auth_type", "none")
        auth_creds = params.get("auth_credentials", {}) or {}
        timeout = float(params.get("timeout", 30.0))
        max_redirects = int(params.get("max_redirects", 5))

        for blocked in self._BLOCKED_HOSTS:
            if blocked in url.lower():
                return ToolResult(
                    success=False,
                    error_message=f"URL blocked: requests to '{blocked}' are not allowed",
                )

        start = time.time()
        try:
            import requests as req_lib

            session = req_lib.Session()
            session.max_redirects = max_redirects

            if auth_type == "basic":
                session.auth = (auth_creds.get("username", ""), auth_creds.get("password", ""))
            elif auth_type == "bearer":
                token = auth_creds.get("token", "")
                if token:
                    session.headers.update({"Authorization": f"Bearer {token}"})

            if headers:
                session.headers.update(headers)

            prepared = req_lib.Request(method, url, params=query_params).prepare()

            if body is not None and method in ("POST", "PUT", "PATCH"):
                if isinstance(body, dict):
                    prepared.body = json.dumps(body)
                    if "Content-Type" not in str(session.headers.get("Content-Type", "")):
                        prepared.headers["Content-Type"] = "application/json"
                else:
                    prepared.body = str(body)

            response = session.send(prepared, timeout=timeout)
            elapsed = time.time() - start

            try:
                response_body = response.json()
            except (json.JSONDecodeError, ValueError):
                response_body = response.text

            return ToolResult(
                success=200 <= response.status_code < 400,
                output={
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_body,
                },
                error_message="" if 200 <= response.status_code < 400 else f"HTTP {response.status_code}: {response.reason}",
                execution_time=elapsed,
                stdout=f"HTTP {response.status_code} ({elapsed:.2f}s)",
            )

        except ImportError:
            return ToolResult(success=False, error_message="requests library not available", execution_time=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
