from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthSession:
    session_id: str = ""
    client_id: str = ""
    authenticated_at: float = 0.0
    expires_at: float = 0.0
    roles: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    auth_method: str = "anonymous"
    is_authenticated: bool = False

    # Reconnection support (P12-09)
    reconnect_token: str = ""
    reconnect_token_expires: float = 0.0
    state_snapshot: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at

    @property
    def time_remaining(self) -> float:
        return max(0.0, self.expires_at - time.monotonic())

    def set_reconnect_token(
        self, token: str, ttl: float = 300.0,
    ) -> None:
        self.reconnect_token = token
        self.reconnect_token_expires = time.monotonic() + ttl

    @property
    def reconnect_token_valid(self) -> bool:
        if not self.reconnect_token:
            return False
        return time.monotonic() < self.reconnect_token_expires


class SessionStore:
    def __init__(self, session_expiry: float = 3600.0):
        self._sessions: dict[str, AuthSession] = {}
        self._client_sessions: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()
        self._session_expiry = session_expiry
        self._cleanup_task: asyncio.Task[None] | None = None

    async def create_session(
        self,
        client_id: str,
        roles: list[str] | None = None,
        permissions: set[str] | None = None,
        auth_method: str = "anonymous",
        is_authenticated: bool = False,
        ttl: float | None = None,
    ) -> AuthSession:
        now = time.monotonic()
        ttl = ttl if ttl is not None else self._session_expiry
        session = AuthSession(
            session_id=f"sess-{uuid.uuid4().hex[:12]}",
            client_id=client_id,
            authenticated_at=now,
            expires_at=now + ttl,
            roles=roles or [],
            permissions=permissions or set(),
            auth_method=auth_method,
            is_authenticated=is_authenticated,
        )
        async with self._lock:
            self._sessions[session.session_id] = session
            self._client_sessions.setdefault(client_id, set()).add(session.session_id)
        return session

    async def get_session(self, session_id: str) -> AuthSession | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired:
                del self._sessions[session_id]
                cs = self._client_sessions.get(session.client_id)
                if cs:
                    cs.discard(session_id)
                return None
            return session

    async def remove_session(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return False
            cs = self._client_sessions.get(session.client_id)
            if cs:
                cs.discard(session_id)
                if not cs:
                    del self._client_sessions[session.client_id]
            return True

    async def get_client_sessions(self, client_id: str) -> list[AuthSession]:
        async with self._lock:
            sids = self._client_sessions.get(client_id, set())
            result = []
            for sid in list(sids):
                session = self._sessions.get(sid)
                if session is None or session.is_expired:
                    sids.discard(sid)
                    if session is None:
                        self._sessions.pop(sid, None)
                    continue
                result.append(session)
            return result

    async def remove_client_sessions(self, client_id: str) -> int:
        count = 0
        async with self._lock:
            sids = self._client_sessions.pop(client_id, set())
            for sid in sids:
                if sid in self._sessions:
                    del self._sessions[sid]
                    count += 1
        return count

    async def cleanup_expired(self) -> int:
        count = 0
        now = time.monotonic()
        async with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if s.expires_at <= now
            ]
            for sid in expired:
                session = self._sessions.pop(sid, None)
                if session:
                    cs = self._client_sessions.get(session.client_id)
                    if cs:
                        cs.discard(sid)
                        if not cs:
                            del self._client_sessions[session.client_id]
                    count += 1
        return count

    async def update_metadata(
        self,
        client_id: str,
        connection_info: Any,
    ) -> None:
        sessions = await self.get_client_sessions(client_id)
        if not sessions:
            return
        latest = sessions[-1]
        connection_info.metadata["session_id"] = latest.session_id
        connection_info.metadata["client_id"] = latest.client_id
        connection_info.metadata["authenticated_at"] = latest.authenticated_at
        connection_info.metadata["expires_at"] = latest.expires_at
        connection_info.metadata["roles"] = latest.roles
        connection_info.metadata["permissions"] = set(latest.permissions)
        connection_info.metadata["auth_method"] = latest.auth_method
        connection_info.metadata["is_authenticated"] = latest.is_authenticated

    async def start_cleanup_loop(self, interval: float = 60.0) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(interval)
                count = await self.cleanup_expired()
                if count:
                    pass

        self._cleanup_task = asyncio.create_task(_loop())

    async def stop_cleanup_loop(self) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def shutdown(self) -> None:
        await self.stop_cleanup_loop()
        async with self._lock:
            self._sessions.clear()
            self._client_sessions.clear()
