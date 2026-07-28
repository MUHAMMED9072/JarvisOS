from __future__ import annotations

import contextvars
import threading
from typing import Any, Optional

from app.kernel.security.permissions import PermissionRegistry, get_permission_registry


class SecurityContext:
    """Request-scoped security context carrying actor identity and granted
    permissions.

    The context is propagated across async boundaries via
    ``SecurityContextVar`` (backed by ``contextvars``) and across
    thread boundaries via explicit ``copy()`` or ``threadlocal``
    storage.

    Usage::

        # Within a request handler
        ctx = SecurityContext(actor="user:alice", granted={"ai.ask", "memory.read"})
        SecurityContextVar.set(ctx)

        # In a callee deep in the call stack
        ctx = SecurityContextVar.get()
        ctx.require("ai.ask")

    Deny-by-default: any permission not in ``granted`` is denied.
    """

    def __init__(
        self,
        actor: str = "anonymous",
        granted: set[str] | frozenset[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._actor = actor
        self._granted: frozenset[str] = frozenset(granted or set())
        self._metadata: dict[str, Any] = dict(metadata or {})
        self._registry: PermissionRegistry = get_permission_registry()

    @property
    def actor(self) -> str:
        return self._actor

    @property
    def granted(self) -> frozenset[str]:
        return self._granted

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    def check(self, permission: str) -> bool:
        """Return ``True`` if the context grants *permission*."""
        return self._registry.check(permission, self._granted)

    def require(self, permission: str) -> None:
        """Raise ``PermissionError`` if *permission* is not granted."""
        if not self.check(permission):
            raise PermissionError(
                f"{self._actor} requires permission {permission!r}, "
                f"granted: {self._registry.describe(self._granted)}"
            )

    def copy(self) -> SecurityContext:
        """Create a copy for propagating across thread boundaries."""
        return SecurityContext(
            actor=self._actor,
            granted=set(self._granted),
            metadata=dict(self._metadata),
        )

    def merge(self, additional: set[str] | frozenset[str]) -> SecurityContext:
        """Return a new context with extra permissions added."""
        return SecurityContext(
            actor=self._actor,
            granted=self._granted | frozenset(additional),
            metadata=self._metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self._actor,
            "granted": sorted(self._granted),
            "metadata": self._metadata,
        }

    def __repr__(self) -> str:
        return (
            f"SecurityContext(actor={self._actor!r}, "
            f"permissions={len(self._granted)})"
        )


class _SecurityContextVar:
    """Context variable for propagating ``SecurityContext`` across async
    boundaries.  Also provides a thread-local fallback for synchronous
    code."""

    def __init__(self) -> None:
        self._ctx_var = contextvars.ContextVar[Optional[SecurityContext]](
            "security_context", default=None
        )
        self._thread_local = threading.local()

    def get(self) -> Optional[SecurityContext]:
        ctx = self._ctx_var.get(None)
        if ctx is not None:
            return ctx
        return getattr(self._thread_local, "context", None)

    def set(self, context: SecurityContext) -> None:
        self._ctx_var.set(context)
        self._thread_local.context = context

    def reset(self) -> None:
        self._ctx_var.set(None)
        if hasattr(self._thread_local, "context"):
            del self._thread_local.context


SecurityContextVar: _SecurityContextVar = _SecurityContextVar()


def require_permission(permission: str):
    """Decorator that checks a permission before allowing the function to
    execute.  The ``SecurityContext`` is read from ``SecurityContextVar``.

    Usage::

        @require_permission("ai.ask")
        def handle_ask(query: str) -> str:
            ...
    """
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            ctx = SecurityContextVar.get()
            if ctx is None:
                raise PermissionError(
                    f"No security context for permission {permission!r}"
                )
            ctx.require(permission)
            return func(*args, **kwargs)
        return wrapper
    return decorator
