from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.logger import JarvisLogger
from app.ws.rate_limiter import RateLimiter
from app.ws.schemas import ServerMessage, WSMessageType
from app.ws.session import AuthSession, SessionStore


class WSAuthenticator:
    def __init__(
        self,
        session_store: SessionStore | None = None,
        rate_limiter: RateLimiter | None = None,
        event_bus: Any = None,
        config: Any = None,
    ) -> None:
        self._session_store = session_store or SessionStore()
        self._rate_limiter = rate_limiter or RateLimiter()
        self._event_bus = event_bus
        self._config = config
        self._pending_auth: dict[str, float] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Handshake authentication
    # ------------------------------------------------------------------

    async def authenticate(
        self,
        client_id: str,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        if token:
            session = await self._authenticate_token(client_id, token)
            if session is not None:
                await self._publish_auth_event("auth.success", client_id, session)
                return self._session_to_metadata(session)
            await self._publish_auth_event(
                "auth.failure", client_id, None,
                extra={"reason": "invalid_token"},
            )

        cfg = self._config
        anonymous_enabled = True
        if cfg is not None:
            anonymous_enabled = getattr(cfg, "WS_ANONYMOUS_ENABLED", True)

        if anonymous_enabled:
            session = await self._create_anonymous_session(client_id)
            return self._session_to_metadata(session)

        return None

    async def _authenticate_token(
        self,
        client_id: str,
        token: str,
    ) -> AuthSession | None:
        if token.startswith("bearer ") or token.startswith("Bearer "):
            return await self._authenticate_bearer(client_id, token.split(" ", 1)[1])
        if token.startswith("apikey ") or token.startswith("apikey:"):
            token_val = token.split(" ", 1)[1] if " " in token else token.split(":", 1)[1]
            return await self._authenticate_api_key(client_id, token_val)
        session = await self._authenticate_api_key(client_id, token)
        if session is not None:
            return session
        session = await self._authenticate_bearer(client_id, token)
        if session is not None:
            return session
        return None

    async def _authenticate_api_key(
        self,
        client_id: str,
        api_key: str,
    ) -> AuthSession | None:
        if not api_key:
            return None
        cfg = self._config
        if cfg is None:
            return None
        api_keys = getattr(cfg, "WS_AUTH_API_KEYS", {})
        roles = api_keys.get(api_key)
        if roles is None:
            return None
        permissions = self._roles_to_permissions(roles)
        session = await self._session_store.create_session(
            client_id=client_id,
            roles=list(roles),
            permissions=permissions,
            auth_method="api_key",
            is_authenticated=True,
            ttl=getattr(cfg, "WS_TOKEN_EXPIRY", 86400.0) if cfg else 86400.0,
        )
        return session

    async def _authenticate_bearer(
        self,
        client_id: str,
        bearer_token: str,
    ) -> AuthSession | None:
        if not bearer_token:
            return None
        cfg = self._config
        if cfg is None:
            return None
        secret = getattr(cfg, "WS_AUTH_BEARER_SECRET", "change-me-in-production")
        expected = hashlib.sha256(secret.encode()).hexdigest()
        try:
            payload = self._decode_bearer(bearer_token, secret)
        except Exception:
            return None
        if payload is None:
            return None
        roles = payload.get("roles", ["user"])
        permissions = self._roles_to_permissions(roles)
        ttl = payload.get("exp", getattr(cfg, "WS_TOKEN_EXPIRY", 86400.0))
        session = await self._session_store.create_session(
            client_id=client_id,
            roles=list(roles),
            permissions=permissions,
            auth_method="bearer",
            is_authenticated=True,
            ttl=float(ttl),
        )
        return session

    def _decode_bearer(self, token: str, secret: str) -> dict[str, Any] | None:
        try:
            parts = token.split(".")
            if len(parts) == 2:
                payload_b64, sig = parts
            elif len(parts) == 3:
                payload_b64 = parts[1]
                sig = parts[2]
            else:
                return None
            import base64
            padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
            try:
                decoded = base64.urlsafe_b64decode(padded)
            except Exception:
                decoded = base64.b64decode(padded)
            payload = json.loads(decoded)
            expected_sig = hmac.new(
                secret.encode(), payload_b64.encode(), hashlib.sha256,
            ).hexdigest()[:16]
            if sig != expected_sig:
                return None
            exp = payload.get("exp")
            if exp is not None and time.time() > float(exp):
                return None
            return payload
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Anonymous session
    # ------------------------------------------------------------------

    async def _create_anonymous_session(
        self,
        client_id: str,
    ) -> AuthSession:
        cfg = self._config
        default_roles = ["user"]
        default_permissions = {
            "admin.ping", "admin.status", "admin.info",
            "command.*", "ai.*", "filesystem.*",
        }
        if cfg is not None:
            default_roles = getattr(cfg, "WS_DEFAULT_ANONYMOUS_ROLES", default_roles)
            default_permissions = set(
                getattr(cfg, "WS_DEFAULT_ANONYMOUS_PERMISSIONS", list(default_permissions))
            )
        session = await self._session_store.create_session(
            client_id=client_id,
            roles=list(default_roles),
            permissions=default_permissions,
            auth_method="anonymous",
            is_authenticated=False,
            ttl=getattr(cfg, "WS_SESSION_EXPIRY", 3600.0) if cfg else 3600.0,
        )
        return session

    # ------------------------------------------------------------------
    # Auth message handling (auth.request, auth.refresh, auth.logout)
    # ------------------------------------------------------------------

    async def try_handle_auth_message(
        self,
        client_id: str,
        ws_manager: Any,
        raw: str,
    ) -> bool:
        try:
            data = json.loads(raw)
            msg_type = data.get("type")
        except json.JSONDecodeError:
            return False

        payload: dict = data.get("payload") or {}

        if msg_type == "auth.request":
            await self._handle_auth_request(client_id, ws_manager, payload)
            return True
        if msg_type == "auth.refresh":
            await self._handle_auth_refresh(client_id, ws_manager, payload)
            return True
        if msg_type == "auth.logout":
            await self._handle_auth_logout(client_id, ws_manager, payload)
            return True

        return False

    async def _handle_auth_request(
        self,
        client_id: str,
        ws_manager: Any,
        payload: dict[str, Any],
    ) -> None:
        token = payload.get("token", "")
        if not token:
            await self._send_auth_response(
                ws_manager, client_id, "auth.failure",
                {"error": "token is required"},
            )
            return

        session = await self._authenticate_token(client_id, token)
        if session is None:
            await self._send_auth_response(
                ws_manager, client_id, "auth.failure",
                {"error": "invalid credentials"},
            )
            await self._publish_auth_event("auth.failure", client_id, None)
            return

        info = ws_manager.get_connection(client_id)
        if info is not None:
            await self._session_store.update_metadata(client_id, info)

        await self._send_auth_response(
            ws_manager, client_id, "auth.success",
            {
                "session_id": session.session_id,
                "roles": session.roles,
                "permissions": list(session.permissions),
                "auth_method": session.auth_method,
                "expires_at": session.expires_at,
            },
        )
        await self._publish_auth_event("auth.success", client_id, session)

    async def _handle_auth_refresh(
        self,
        client_id: str,
        ws_manager: Any,
        payload: dict[str, Any],
    ) -> None:
        session_id = payload.get("session_id", "")
        if not session_id:
            return

        session = await self._session_store.get_session(session_id)
        if session is None or session.client_id != client_id:
            return

        cfg = self._config
        ttl = getattr(cfg, "WS_SESSION_EXPIRY", 3600.0) if cfg else 3600.0
        new_expiry = time.monotonic() + ttl
        session.expires_at = new_expiry

        info = ws_manager.get_connection(client_id)
        if info is not None:
            await self._session_store.update_metadata(client_id, info)

        await self._send_auth_response(
            ws_manager, client_id, "auth.response",
            {
                "session_id": session.session_id,
                "expires_at": new_expiry,
                "time_remaining": ttl,
            },
        )

    async def _handle_auth_logout(
        self,
        client_id: str,
        ws_manager: Any,
        payload: dict[str, Any],
    ) -> None:
        await self._session_store.remove_client_sessions(client_id)

        new_session = await self._create_anonymous_session(client_id)
        info = ws_manager.get_connection(client_id)
        if info is not None:
            await self._session_store.update_metadata(client_id, info)

        await self._send_auth_response(
            ws_manager, client_id, "auth.response",
            {"message": "logged out", "session_id": new_session.session_id},
        )
        await self._publish_auth_event(
            "auth.logout", client_id, None,
            extra={"new_session_id": new_session.session_id},
        )

    # ------------------------------------------------------------------
    # Session/connection helpers
    # ------------------------------------------------------------------

    def get_session_store(self) -> SessionStore:
        return self._session_store

    async def update_connection_metadata(
        self,
        client_id: str,
        ws_manager: Any,
    ) -> None:
        info = ws_manager.get_connection(client_id)
        if info is None:
            return
        await self._session_store.update_metadata(client_id, info)

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def check_rate_limit(self, client_id: str) -> bool:
        return await self._rate_limiter.check(client_id)

    async def record_message(self, client_id: str) -> None:
        await self._rate_limiter.record(client_id)

    # ------------------------------------------------------------------
    # EventBus publishing
    # ------------------------------------------------------------------

    async def _publish_auth_event(
        self,
        event: str,
        client_id: str,
        session: AuthSession | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self._event_bus is None:
            return
        data: dict[str, Any] = {
            "client_id": client_id,
            "timestamp": time.time(),
        }
        if session is not None:
            data["session_id"] = session.session_id
            data["auth_method"] = session.auth_method
            data["roles"] = list(session.roles)
        if extra:
            data.update(extra)
        try:
            self._event_bus.publish(event, **data)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Backward-compatible lifecycle hooks
    # ------------------------------------------------------------------

    async def on_connect(self, client_id: str, metadata: dict[str, Any]) -> None:
        JarvisLogger.info("WebSocket client connected: %s", client_id)

    async def on_disconnect(self, client_id: str) -> None:
        JarvisLogger.info("WebSocket client disconnected: %s", client_id)
        await self._session_store.remove_client_sessions(client_id)

    # ------------------------------------------------------------------
    # Permission checking helper
    # ------------------------------------------------------------------

    async def check_permission(
        self,
        client_id: str,
        ws_manager: Any,
        required_permission: str,
    ) -> bool:
        info = ws_manager.get_connection(client_id)
        if info is None:
            return False
        metadata = info.metadata or {}
        if not isinstance(metadata, dict):
            return True
        session_id = metadata.get("session_id")
        if not session_id:
            return True
        roles = metadata.get("roles", [])
        if "admin" in roles:
            return True
        permissions = metadata.get("permissions", set())
        if isinstance(permissions, list):
            permissions = set(permissions)
        if required_permission in permissions:
            return True
        for perm_pattern in permissions:
            if fnmatch.fnmatch(required_permission, perm_pattern):
                return True
        return False

    def _session_to_metadata(self, session: AuthSession) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "client_id": session.client_id,
            "authenticated_at": session.authenticated_at,
            "expires_at": session.expires_at,
            "roles": list(session.roles),
            "permissions": set(session.permissions),
            "auth_method": session.auth_method,
            "is_authenticated": session.is_authenticated,
        }

    def _roles_to_permissions(self, roles: list[str]) -> set[str]:
        all_permissions: set[str] = set()
        role_perms: dict[str, list[str]] = {
            "admin": ["admin.*", "command.*", "ai.*", "filesystem.*", "monitor.*"],
            "user": ["admin.ping", "admin.status", "admin.info", "command.*", "ai.*", "filesystem.*"],
            "monitor": ["system.metrics", "system.health"],
        }
        for role in roles:
            perms = role_perms.get(role, [])
            all_permissions.update(perms)
        return all_permissions

    async def _send_auth_response(
        self,
        ws_manager: Any,
        client_id: str,
        msg_type: str,
        payload: dict[str, Any],
    ) -> None:
        if not await ws_manager.is_connected(client_id):
            return
        type_map = {
            "auth.success": WSMessageType.AUTH_SUCCESS,
            "auth.failure": WSMessageType.AUTH_FAILURE,
            "auth.response": WSMessageType.AUTH_RESPONSE,
            "auth.expired": WSMessageType.AUTH_EXPIRED,
            "auth.denied": WSMessageType.AUTH_DENIED,
        }
        ws_type = type_map.get(msg_type, WSMessageType.AUTH_RESPONSE)
        await ws_manager.send(
            client_id,
            ServerMessage(type=ws_type, payload=payload),
        )
