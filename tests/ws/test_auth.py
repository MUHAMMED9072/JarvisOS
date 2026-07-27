"""Tests for WebSocket Authentication & Security (P12-08)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ws.auth import WSAuthenticator
from app.ws.manager import WebSocketConnectionManager
from app.ws.rate_limiter import RateLimiter
from app.ws.schemas import WSMessageType
from app.ws.session import AuthSession, SessionStore


# ==========================================================================
# Helpers
# ==========================================================================


class _MockConfig:
    WS_AUTH_ENABLED = True
    WS_ANONYMOUS_ENABLED = True
    WS_AUTH_TIMEOUT = 30.0
    WS_SESSION_EXPIRY = 3600.0
    WS_TOKEN_EXPIRY = 86400.0
    WS_MAX_MESSAGES_PER_MINUTE = 120
    WS_AUTH_API_KEYS = {
        "admin-key": ["admin"],
        "user-key": ["user"],
        "monitor-key": ["monitor"],
    }
    WS_AUTH_BEARER_SECRET = "test-secret"
    WS_DEFAULT_ANONYMOUS_ROLES = ["user"]
    WS_DEFAULT_ANONYMOUS_PERMISSIONS = [
        "admin.ping", "admin.status", "admin.info",
        "command.*", "ai.*", "filesystem.*",
    ]


def _make_bearer_token(
    payload: dict[str, Any],
    secret: str = "test-secret",
) -> str:
    import base64
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode().rstrip("=")
    sig = hmac.new(
        secret.encode(), payload_b64.encode(), hashlib.sha256,
    ).hexdigest()[:16]
    return f"header.{payload_b64}.{sig}"


def _make_env(
    config: Any = None,
    event_bus: Any = None,
) -> WSAuthenticator:
    config = config or _MockConfig()
    session_store = SessionStore(session_expiry=config.WS_SESSION_EXPIRY)
    return WSAuthenticator(
        session_store=session_store,
        rate_limiter=RateLimiter(max_messages=120),
        event_bus=event_bus,
        config=config,
    )


def _make_ws_manager(
    authenticator: WSAuthenticator | None = None,
) -> WebSocketConnectionManager:
    return WebSocketConnectionManager(authenticator=authenticator or WSAuthenticator())


def _make_connection(
    ws_manager: WebSocketConnectionManager,
    client_id: str = "test-client",
    metadata: dict | None = None,
) -> MagicMock:
    info = MagicMock()
    info.client_id = client_id
    info.metadata = metadata or {}
    info.rooms = set()
    info.subscriptions = set()
    info.connected_at = time.monotonic()
    ws_manager._connections[client_id] = info
    return info


# ==========================================================================
# Session Tests
# ==========================================================================


class TestSessionStore:
    """Session creation, retrieval, expiration, and cleanup."""

    @pytest.mark.asyncio
    async def test_create_and_get_session(self) -> None:
        store = SessionStore()
        session = await store.create_session(
            client_id="client-1",
            roles=["admin"],
            permissions={"admin.*", "command.*"},
            auth_method="api_key",
            is_authenticated=True,
        )
        assert session.session_id.startswith("sess-")
        assert session.client_id == "client-1"
        assert "admin" in session.roles
        assert "admin.*" in session.permissions
        assert session.auth_method == "api_key"
        assert session.is_authenticated is True

        retrieved = await store.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self) -> None:
        store = SessionStore()
        result = await store.get_session("no-such-session")
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_session(self) -> None:
        store = SessionStore()
        session = await store.create_session(client_id="client-1")
        removed = await store.remove_session(session.session_id)
        assert removed is True

        retrieved = await store.get_session(session.session_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_session(self) -> None:
        store = SessionStore()
        removed = await store.remove_session("no-such-session")
        assert removed is False

    @pytest.mark.asyncio
    async def test_expired_session_returns_none(self) -> None:
        store = SessionStore(session_expiry=0.01)
        session = await store.create_session(client_id="client-1")
        assert session.session_id is not None
        await asyncio.sleep(0.02)
        retrieved = await store.get_session(session.session_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self) -> None:
        store = SessionStore(session_expiry=0.01)
        s1 = await store.create_session(client_id="client-1")
        s2 = await store.create_session(client_id="client-2")
        await asyncio.sleep(0.02)
        count = await store.cleanup_expired()
        assert count == 2
        assert await store.get_session(s1.session_id) is None
        assert await store.get_session(s2.session_id) is None

    @pytest.mark.asyncio
    async def test_get_client_sessions(self) -> None:
        store = SessionStore()
        s1 = await store.create_session(client_id="client-1")
        s2 = await store.create_session(client_id="client-1")
        sessions = await store.get_client_sessions("client-1")
        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_remove_client_sessions(self) -> None:
        store = SessionStore()
        await store.create_session(client_id="client-1")
        await store.create_session(client_id="client-1")
        count = await store.remove_client_sessions("client-1")
        assert count == 2
        assert await store.get_client_sessions("client-1") == []

    @pytest.mark.asyncio
    async def test_session_expiry_property(self) -> None:
        session = AuthSession(
            session_id="sess-test",
            client_id="client-1",
            authenticated_at=time.monotonic(),
            expires_at=time.monotonic() + 3600,
        )
        assert session.is_expired is False
        assert session.time_remaining > 0

        session.expires_at = time.monotonic() - 1
        assert session.is_expired is True
        assert session.time_remaining == 0.0


# ==========================================================================
# Rate Limiter Tests
# ==========================================================================


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_within_limit(self) -> None:
        limiter = RateLimiter(max_messages=5, window_seconds=60)
        for _ in range(5):
            assert await limiter.check("client-1") is True

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self) -> None:
        limiter = RateLimiter(max_messages=3, window_seconds=60)
        for _ in range(3):
            assert await limiter.check("client-1") is True
        assert await limiter.check("client-1") is False

    @pytest.mark.asyncio
    async def test_reset_clears_limit(self) -> None:
        limiter = RateLimiter(max_messages=2, window_seconds=60)
        assert await limiter.check("client-1") is True
        assert await limiter.check("client-1") is True
        assert await limiter.check("client-1") is False
        await limiter.reset("client-1")
        assert await limiter.check("client-1") is True

    @pytest.mark.asyncio
    async def test_different_clients_independent(self) -> None:
        limiter = RateLimiter(max_messages=1, window_seconds=60)
        assert await limiter.check("client-1") is True
        assert await limiter.check("client-1") is False
        assert await limiter.check("client-2") is True

    @pytest.mark.asyncio
    async def test_get_count(self) -> None:
        limiter = RateLimiter(max_messages=10, window_seconds=60)
        for _ in range(5):
            await limiter.check("client-1")
        count = await limiter.get_count("client-1")
        assert count == 5

    @pytest.mark.asyncio
    async def test_reset_all(self) -> None:
        limiter = RateLimiter(max_messages=1, window_seconds=60)
        await limiter.check("client-1")
        await limiter.check("client-2")
        await limiter.reset_all()
        assert await limiter.check("client-1") is True
        assert await limiter.check("client-2") is True


# ==========================================================================
# Authenticator Tests
# ==========================================================================


class TestHandshakeAuth:
    @pytest.mark.asyncio
    async def test_anonymous_auth_succeeds(self) -> None:
        auth = _make_env()
        metadata = await auth.authenticate(client_id="client-1")
        assert metadata is not None
        assert metadata.get("auth_method") == "anonymous"
        assert "session_id" in metadata
        assert metadata.get("is_authenticated") is False

    @pytest.mark.asyncio
    async def test_api_key_auth(self) -> None:
        auth = _make_env()
        metadata = await auth.authenticate(client_id="client-1", token="admin-key")
        assert metadata is not None
        assert metadata.get("auth_method") == "api_key"
        assert metadata.get("is_authenticated") is True
        assert "admin" in metadata.get("roles", [])

    @pytest.mark.asyncio
    async def test_api_key_auth_with_prefix(self) -> None:
        auth = _make_env()
        metadata = await auth.authenticate(client_id="client-1", token="apikey:admin-key")
        assert metadata is not None
        assert metadata.get("is_authenticated") is True

    @pytest.mark.asyncio
    async def test_bearer_token_auth(self) -> None:
        auth = _make_env()
        token = _make_bearer_token({"sub": "test", "roles": ["admin"]})
        metadata = await auth.authenticate(client_id="client-1", token=f"bearer {token}")
        assert metadata is not None
        assert metadata.get("auth_method") == "bearer"
        assert metadata.get("is_authenticated") is True
        assert "admin" in metadata.get("roles", [])

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_none(self) -> None:
        config = _MockConfig()
        config.WS_ANONYMOUS_ENABLED = False
        auth = _make_env(config=config)
        metadata = await auth.authenticate(client_id="client-1", token="wrong-key")
        assert metadata is None

    @pytest.mark.asyncio
    async def test_invalid_bearer_token_returns_anonymous(self) -> None:
        auth = _make_env()
        metadata = await auth.authenticate(client_id="client-1", token="bearer invalid.token.sig")
        assert metadata is not None
        assert metadata.get("auth_method") == "anonymous"

    @pytest.mark.asyncio
    async def test_no_anonymous_rejects(self) -> None:
        config = _MockConfig()
        config.WS_ANONYMOUS_ENABLED = False
        auth = _make_env(config=config)
        metadata = await auth.authenticate(client_id="client-1")
        assert metadata is None

    @pytest.mark.asyncio
    async def test_no_anonymous_with_valid_token_succeeds(self) -> None:
        config = _MockConfig()
        config.WS_ANONYMOUS_ENABLED = False
        auth = _make_env(config=config)
        metadata = await auth.authenticate(client_id="client-1", token="admin-key")
        assert metadata is not None
        assert metadata.get("is_authenticated") is True

    @pytest.mark.asyncio
    async def test_user_role_api_key(self) -> None:
        auth = _make_env()
        metadata = await auth.authenticate(client_id="client-1", token="user-key")
        assert metadata is not None
        assert "user" in metadata.get("roles", [])
        assert "admin" not in metadata.get("roles", [])

    @pytest.mark.asyncio
    async def test_bearer_with_expired_token_uses_anonymous(self) -> None:
        auth = _make_env()
        expired_token = _make_bearer_token(
            {"sub": "test", "roles": ["admin"], "exp": time.time() - 100},
        )
        metadata = await auth.authenticate(client_id="client-1", token=f"bearer {expired_token}")
        assert metadata is not None
        assert metadata.get("auth_method") == "anonymous"

    @pytest.mark.asyncio
    async def test_bearer_with_wrong_secret_uses_anonymous(self) -> None:
        auth = _make_env()
        wrong_token = _make_bearer_token({"roles": ["admin"]}, secret="wrong-secret")
        metadata = await auth.authenticate(client_id="client-1", token=f"bearer {wrong_token}")
        assert metadata is not None
        assert metadata.get("auth_method") == "anonymous"

    @pytest.mark.asyncio
    async def test_api_key_prefixes(self) -> None:
        auth = _make_env()
        for prefix in ["apikey ", "apikey:", ""]:
            metadata = await auth.authenticate(
                client_id="client-1", token=f"{prefix}admin-key",
            )
            assert metadata is not None
            assert metadata.get("is_authenticated") is True


class TestAuthMessageHandling:
    @pytest.mark.asyncio
    async def test_auth_request_with_valid_api_key(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        raw = json.dumps({
            "type": "auth.request",
            "payload": {"token": "admin-key"},
        })
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, raw)
        assert handled is True
        assert ws_mgr.send.called
        sent_type = ws_mgr.send.call_args[0][1].type
        assert sent_type == WSMessageType.AUTH_SUCCESS

    @pytest.mark.asyncio
    async def test_auth_request_with_valid_bearer(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        token = _make_bearer_token({"sub": "test", "roles": ["admin"]})
        raw = json.dumps({
            "type": "auth.request",
            "payload": {"token": f"bearer {token}"},
        })
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, raw)
        assert handled is True
        assert ws_mgr.send.called
        sent_type = ws_mgr.send.call_args[0][1].type
        assert sent_type == WSMessageType.AUTH_SUCCESS

    @pytest.mark.asyncio
    async def test_auth_request_with_invalid_token(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        raw = json.dumps({
            "type": "auth.request",
            "payload": {"token": "wrong-key"},
        })
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, raw)
        assert handled is True
        assert ws_mgr.send.called
        sent_type = ws_mgr.send.call_args[0][1].type
        assert sent_type == WSMessageType.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_auth_request_without_token(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        raw = json.dumps({"type": "auth.request", "payload": {}})
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, raw)
        assert handled is True
        sent_type = ws_mgr.send.call_args[0][1].type
        assert sent_type == WSMessageType.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_auth_refresh(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        session = await auth._session_store.create_session(
            client_id="client-1",
            auth_method="api_key",
            is_authenticated=True,
        )
        raw = json.dumps({
            "type": "auth.refresh",
            "payload": {"session_id": session.session_id},
        })
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, raw)
        assert handled is True
        assert ws_mgr.send.called

    @pytest.mark.asyncio
    async def test_auth_refresh_nonexistent_session(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        raw = json.dumps({
            "type": "auth.refresh",
            "payload": {"session_id": "no-such-session"},
        })
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, raw)
        assert handled is True
        assert ws_mgr.send.call_count == 0

    @pytest.mark.asyncio
    async def test_auth_logout(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        session = await auth._session_store.create_session(
            client_id="client-1",
            auth_method="api_key",
            is_authenticated=True,
        )
        raw = json.dumps({
            "type": "auth.logout",
            "payload": {},
        })
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, raw)
        assert handled is True
        assert ws_mgr.send.called
        assert await auth._session_store.get_session(session.session_id) is None

    @pytest.mark.asyncio
    async def test_auth_logout_creates_new_anonymous_session(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        info = _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        await auth._session_store.create_session(
            client_id="client-1",
            auth_method="api_key",
            is_authenticated=True,
        )
        raw = json.dumps({"type": "auth.logout", "payload": {}})
        await auth.try_handle_auth_message("client-1", ws_mgr, raw)

        assert "session_id" in info.metadata
        assert info.metadata.get("auth_method") == "anonymous"

    @pytest.mark.asyncio
    async def test_non_auth_message_not_handled(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        raw = json.dumps({"type": "ping"})
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, raw)
        assert handled is False

        raw = json.dumps({"type": "subscribe", "event": "test"})
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, raw)
        assert handled is False

    @pytest.mark.asyncio
    async def test_invalid_json_not_handled(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        handled = await auth.try_handle_auth_message("client-1", ws_mgr, "not json{{{")
        assert handled is False

    @pytest.mark.asyncio
    async def test_re_authentication_upgrades_permissions(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        raw = json.dumps({
            "type": "auth.request",
            "payload": {"token": "admin-key"},
        })
        await auth.try_handle_auth_message("client-1", ws_mgr, raw)

        info = ws_mgr.get_connection("client-1")
        assert info is not None
        assert "admin" in info.metadata.get("roles", [])


# ==========================================================================
# Permission Enforcement Tests
# ==========================================================================


class TestPermissionEnforcement:
    @pytest.mark.asyncio
    async def test_admin_permission_allows_all(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "admin-1", {
            "session_id": "sess-1",
            "roles": ["admin"],
            "permissions": {"admin.*", "command.*"},
        })
        assert await auth.check_permission("admin-1", ws_mgr, "admin.shutdown") is True
        assert await auth.check_permission("admin-1", ws_mgr, "admin.plugins") is True
        assert await auth.check_permission("admin-1", ws_mgr, "command.execute") is True
        assert await auth.check_permission("admin-1", ws_mgr, "filesystem.upload") is True

    @pytest.mark.asyncio
    async def test_user_permission_restricted(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "user-1", {
            "session_id": "sess-2",
            "roles": ["user"],
            "permissions": {"command.*", "ai.*", "filesystem.*", "admin.ping"},
        })
        assert await auth.check_permission("user-1", ws_mgr, "admin.ping") is True
        assert await auth.check_permission("user-1", ws_mgr, "command.execute") is True
        assert await auth.check_permission("user-1", ws_mgr, "ai.stream") is True
        assert await auth.check_permission("user-1", ws_mgr, "filesystem.upload") is True
        assert await auth.check_permission("user-1", ws_mgr, "admin.shutdown") is False

    @pytest.mark.asyncio
    async def test_unknown_client_no_permission(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        assert await auth.check_permission("unknown", ws_mgr, "admin.ping") is False

    @pytest.mark.asyncio
    async def test_legacy_no_session_allows_all(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "legacy-1", {})
        assert await auth.check_permission("legacy-1", ws_mgr, "admin.shutdown") is True
        assert await auth.check_permission("legacy-1", ws_mgr, "command.execute") is True
        assert await auth.check_permission("legacy-1", ws_mgr, "filesystem.upload") is True

    @pytest.mark.asyncio
    async def test_wildcard_permission_admin_dot_star(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "op-1", {
            "session_id": "sess-3",
            "roles": ["operator"],
            "permissions": {"admin.*", "command.*"},
        })
        assert await auth.check_permission("op-1", ws_mgr, "admin.shutdown") is True
        assert await auth.check_permission("op-1", ws_mgr, "admin.plugins") is True
        assert await auth.check_permission("op-1", ws_mgr, "admin.config") is True
        assert await auth.check_permission("op-1", ws_mgr, "admin.nonexistent") is True

    @pytest.mark.asyncio
    async def test_command_dot_star_permission(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "cmd-1", {
            "session_id": "sess-4",
            "roles": ["user"],
            "permissions": {"command.*"},
        })
        assert await auth.check_permission("cmd-1", ws_mgr, "command.execute") is True
        assert await auth.check_permission("cmd-1", ws_mgr, "command.cancel") is True
        assert await auth.check_permission("cmd-1", ws_mgr, "admin.ping") is False

    @pytest.mark.asyncio
    async def test_ai_dot_star_permission(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "ai-1", {
            "session_id": "sess-5",
            "roles": ["user"],
            "permissions": {"ai.*"},
        })
        assert await auth.check_permission("ai-1", ws_mgr, "ai.stream") is True
        assert await auth.check_permission("ai-1", ws_mgr, "ai.chat") is True
        assert await auth.check_permission("ai-1", ws_mgr, "command.execute") is False

    @pytest.mark.asyncio
    async def test_filesystem_dot_star_permission(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "fs-1", {
            "session_id": "sess-6",
            "roles": ["user"],
            "permissions": {"filesystem.*"},
        })
        assert await auth.check_permission("fs-1", ws_mgr, "filesystem.upload") is True
        assert await auth.check_permission("fs-1", ws_mgr, "filesystem.download") is True
        assert await auth.check_permission("fs-1", ws_mgr, "ai.stream") is False

    @pytest.mark.asyncio
    async def test_permissions_as_list(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "list-1", {
            "session_id": "sess-7",
            "roles": ["user"],
            "permissions": ["admin.ping", "command.*"],
        })
        assert await auth.check_permission("list-1", ws_mgr, "admin.ping") is True
        assert await auth.check_permission("list-1", ws_mgr, "command.execute") is True
        assert await auth.check_permission("list-1", ws_mgr, "admin.shutdown") is False


# ==========================================================================
# Admin Manager Permission Integration
# ==========================================================================


class TestAdminManagerPermissions:
    """AdminManager._check_permission enforces session-based auth."""

    @pytest.mark.asyncio
    async def test_admin_with_session_has_access(self) -> None:
        from app.ws.admin import AdminManager
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "admin-1", {
            "session_id": "sess-a1",
            "roles": ["admin"],
            "permissions": {"admin.*"},
        })
        registry = MagicMock()
        mgr = AdminManager(ws_manager=ws_mgr, registry=registry)
        assert await mgr._check_permission("admin-1", "admin.shutdown") is True

    @pytest.mark.asyncio
    async def test_user_without_admin_permission_denied(self) -> None:
        from app.ws.admin import AdminManager
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "user-1", {
            "session_id": "sess-u1",
            "roles": ["user"],
            "permissions": {"admin.ping"},
        })
        registry = MagicMock()
        mgr = AdminManager(ws_manager=ws_mgr, registry=registry)
        assert await mgr._check_permission("user-1", "admin.ping") is True
        assert await mgr._check_permission("user-1", "admin.shutdown") is False

    @pytest.mark.asyncio
    async def test_legacy_no_session_has_full_access(self) -> None:
        from app.ws.admin import AdminManager
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "legacy-1", {})
        registry = MagicMock()
        mgr = AdminManager(ws_manager=ws_mgr, registry=registry)
        assert await mgr._check_permission("legacy-1", "admin.shutdown") is True
        assert await mgr._check_permission("legacy-1", "admin.plugins") is True

    @pytest.mark.asyncio
    async def test_disconnected_client_denied(self) -> None:
        from app.ws.admin import AdminManager
        ws_mgr = _make_ws_manager()
        registry = MagicMock()
        mgr = AdminManager(ws_manager=ws_mgr, registry=registry)
        assert await mgr._check_permission("no-such", "admin.ping") is False


# ==========================================================================
# EventBus Integration
# ==========================================================================


class TestEventBusIntegration:
    @pytest.mark.asyncio
    async def test_auth_success_event_published(self) -> None:
        event_bus = MagicMock()
        auth = _make_env(event_bus=event_bus)
        await auth.authenticate(client_id="client-1", token="admin-key")
        assert event_bus.publish.called
        call_args = event_bus.publish.call_args
        assert call_args[0][0] == "auth.success"

    @pytest.mark.asyncio
    async def test_auth_failure_event_published(self) -> None:
        event_bus = MagicMock()
        config = _MockConfig()
        config.WS_ANONYMOUS_ENABLED = False
        auth = _make_env(config=config, event_bus=event_bus)
        await auth.authenticate(client_id="client-1", token="wrong-key")
        assert event_bus.publish.called
        call_args = event_bus.publish.call_args
        assert call_args[0][0] == "auth.failure"

    @pytest.mark.asyncio
    async def test_auth_logout_event_published(self) -> None:
        event_bus = MagicMock()
        auth = _make_env(event_bus=event_bus)
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        raw = json.dumps({"type": "auth.logout", "payload": {}})
        await auth.try_handle_auth_message("client-1", ws_mgr, raw)

        logout_events = [
            c for c in event_bus.publish.call_args_list
            if c[0][0] == "auth.logout"
        ]
        assert len(logout_events) >= 1

    @pytest.mark.asyncio
    async def test_event_bus_exception_does_not_crash(self) -> None:
        event_bus = MagicMock()
        event_bus.publish.side_effect = RuntimeError("bus error")
        auth = _make_env(event_bus=event_bus)
        metadata = await auth.authenticate(client_id="client-1", token="admin-key")
        assert metadata is not None


# ==========================================================================
# Rate Limiting Integration
# ==========================================================================


class TestRateLimitIntegration:
    @pytest.mark.asyncio
    async def test_rate_limiter_check_and_record(self) -> None:
        auth = _make_env()
        for _ in range(5):
            assert await auth.check_rate_limit("client-1") is True
        assert await auth.check_rate_limit("client-1") is True  # 120 limit

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_excessive(self) -> None:
        auth = _make_env()
        # Create a limiter with very low max
        auth._rate_limiter = RateLimiter(max_messages=3, window_seconds=60)
        for _ in range(3):
            assert await auth.check_rate_limit("client-1") is True
        assert await auth.check_rate_limit("client-1") is False


# ==========================================================================
# Session Lifecycle
# ==========================================================================


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_sessions(self) -> None:
        auth = _make_env()
        session = await auth._session_store.create_session(client_id="client-1")
        assert await auth._session_store.get_session(session.session_id) is not None
        await auth.on_disconnect("client-1")
        assert await auth._session_store.get_session(session.session_id) is None

    @pytest.mark.asyncio
    async def test_multiple_sessions_per_client(self) -> None:
        auth = _make_env()
        s1 = await auth._session_store.create_session(client_id="client-1")
        s2 = await auth._session_store.create_session(client_id="client-1")
        assert s1.session_id != s2.session_id
        sessions = await auth._session_store.get_client_sessions("client-1")
        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_cleanup_loop(self) -> None:
        store = SessionStore(session_expiry=0.01)
        session = await store.create_session(client_id="client-1")
        await store.start_cleanup_loop(interval=0.01)
        await asyncio.sleep(0.05)
        assert await store.get_session(session.session_id) is None
        await store.stop_cleanup_loop()


# ==========================================================================
# Concurrent Clients
# ==========================================================================


class TestConcurrentClients:
    @pytest.mark.asyncio
    async def test_multiple_clients_independent_sessions(self) -> None:
        auth = _make_env()
        s1 = await auth._session_store.create_session(client_id="client-1")
        s2 = await auth._session_store.create_session(client_id="client-2")
        assert s1.session_id != s2.session_id

        c1_sessions = await auth._session_store.get_client_sessions("client-1")
        c2_sessions = await auth._session_store.get_client_sessions("client-2")
        assert len(c1_sessions) == 1
        assert len(c2_sessions) == 1

    @pytest.mark.asyncio
    async def test_concurrent_auth_requests(self) -> None:
        auth = _make_env()
        ws_mgr = _make_ws_manager()
        _make_connection(ws_mgr, "client-1", {})
        ws_mgr.is_connected = AsyncMock(return_value=True)
        ws_mgr.send = AsyncMock(return_value=True)

        results = await asyncio.gather(*[
            auth.try_handle_auth_message(
                "client-1",
                ws_mgr,
                json.dumps({"type": "auth.request", "payload": {"token": "admin-key"}}),
            )
            for _ in range(10)
        ])
        assert all(results)
        assert ws_mgr.send.call_count == 10

    @pytest.mark.asyncio
    async def test_rate_limiter_per_client(self) -> None:
        limiter = RateLimiter(max_messages=5, window_seconds=60)
        for _ in range(5):
            assert await limiter.check("client-1") is True
        assert await limiter.check("client-1") is False
        assert await limiter.check("client-2") is True


# ==========================================================================
# Backward Compatibility
# ==========================================================================


class TestBackwardCompatibility:
    def test_ws_authenticator_class_exists(self) -> None:
        from app.ws.auth import WSAuthenticator
        assert hasattr(WSAuthenticator, "authenticate")
        assert hasattr(WSAuthenticator, "on_connect")
        assert hasattr(WSAuthenticator, "on_disconnect")

    def test_original_authenticate_signature_preserved(self) -> None:
        import inspect
        sig = inspect.signature(WSAuthenticator.authenticate)
        params = list(sig.parameters.keys())
        assert "client_id" in params
        assert "token" in params
        assert "headers" in params

    @pytest.mark.asyncio
    async def test_health_still_works(self) -> None:
        from app.api.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_ws_message_types_extended(self) -> None:
        assert WSMessageType.AUTH_REQUEST.value == "auth.request"
        assert WSMessageType.AUTH_SUCCESS.value == "auth.success"
        assert WSMessageType.AUTH_FAILURE.value == "auth.failure"
        assert WSMessageType.AUTH_REFRESH.value == "auth.refresh"
        assert WSMessageType.AUTH_LOGOUT.value == "auth.logout"
        assert WSMessageType.AUTH_EXPIRED.value == "auth.expired"
        assert WSMessageType.AUTH_DENIED.value == "auth.denied"
        assert WSMessageType.AUTH_RESPONSE.value == "auth.response"
