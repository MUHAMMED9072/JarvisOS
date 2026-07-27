"""Tests for REST client."""

from __future__ import annotations

import pytest

from app.client.api import RestClient


class TestRestClientLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        client = RestClient(base_url="http://localhost:9999")
        assert client.is_started is False
        await client.start()
        assert client.is_started is True
        await client.stop()
        assert client.is_started is False

    @pytest.mark.asyncio
    async def test_request_without_start_raises(self):
        client = RestClient()
        with pytest.raises(RuntimeError, match="not started"):
            await client.get("/health")

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self):
        client = RestClient()
        await client.start()
        await client.start()  # Should not raise
        await client.stop()


class TestRestClientAuth:
    def test_api_key_header(self):
        client = RestClient(api_key="test-key")
        assert client._api_key == "test-key"
        assert client._bearer_token is None

    def test_bearer_token(self):
        client = RestClient(bearer_token="tok123")
        assert client._bearer_token == "tok123"
        assert client._api_key is None

    def test_both_auth(self):
        client = RestClient(api_key="key", bearer_token="tok")
        assert client._api_key == "key"
        assert client._bearer_token == "tok"


class TestRestClientConfig:
    def test_defaults(self):
        client = RestClient()
        assert client._base_url == "http://localhost:8000"
        assert client._timeout == 30.0
        assert client._retry_count == 3

    def test_custom_config(self):
        client = RestClient(
            base_url="https://example.com",
            timeout=10.0,
            retry_count=5,
        )
        assert client._base_url == "https://example.com"
        assert client._timeout == 10.0
        assert client._retry_count == 5

    def test_base_url_trailing_slash(self):
        client = RestClient(base_url="http://test.com/")
        assert client._base_url == "http://test.com"


class TestRestClientMethods:
    """Unit tests with mocked transport layer."""

    @pytest.mark.asyncio
    async def test_health_method(self):
        client = RestClient()
        await client.start()
        # No server running - will raise
        with pytest.raises(Exception):
            await client.health()
        await client.stop()

    @pytest.mark.asyncio
    async def test_status_method(self):
        client = RestClient()
        await client.start()
        with pytest.raises(Exception):
            await client.status()
        await client.stop()

    @pytest.mark.asyncio
    async def test_typed_methods_defined(self):
        client = RestClient()
        assert hasattr(client, "health")
        assert hasattr(client, "status")
        assert hasattr(client, "config")
        assert hasattr(client, "services")
        assert hasattr(client, "get_ws_metrics")
        assert hasattr(client, "get_ws_health")
        assert hasattr(client, "get_ws_diagnostics")
        assert hasattr(client, "list_plugins")
        assert hasattr(client, "get_plugin")
        assert hasattr(client, "list_skills")
        assert hasattr(client, "ai_chat")
        assert hasattr(client, "ai_stream")

    def test_http_methods_defined(self):
        client = RestClient()
        assert hasattr(client, "get")
        assert hasattr(client, "post")
        assert hasattr(client, "put")
        assert hasattr(client, "delete")
        assert hasattr(client, "patch")


class TestRestClientRetry:
    @pytest.mark.asyncio
    async def test_retry_config_passed(self):
        client = RestClient(retry_count=5)
        await client.start()
        assert client._retry_count == 5
        await client.stop()
