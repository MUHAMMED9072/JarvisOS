from __future__ import annotations

from typing import Any, Optional

from app.core.event_bus import EventBus
from app.core.registry import ServiceRegistry
from app.kernel.security.context import SecurityContext, SecurityContextVar
from app.kernel.security.permissions import PermissionRegistry, get_permission_registry


class SecurityEventBus:
    """A security-aware wrapper around ``EventBus``.

    Wraps ``subscribe``, ``publish``, and ``unsubscribe`` to enforce
    permission checks before delegating to the underlying bus.

    Usage::

        secure_bus = SecurityEventBus(event_bus, registry)
        secure_bus.publish("system.shutdown")  # checks events.publish
    """

    def __init__(
        self,
        bus: EventBus,
        perm_registry: Optional[PermissionRegistry] = None,
    ) -> None:
        self._bus = bus
        self._perm_registry = perm_registry or get_permission_registry()

    @property
    def listener_count(self) -> int:
        return self._bus.listener_count

    @property
    def pattern_count(self) -> int:
        return self._bus.pattern_count

    def subscribe(self, event: str, callback: Any) -> None:
        self._check("events.subscribe")
        self._bus.subscribe(event, callback)

    def subscribe_wildcard(self, pattern: str, callback: Any) -> None:
        self._check("events.subscribe")
        self._bus.subscribe_wildcard(pattern, callback)

    def unsubscribe(self, event: str, callback: Any) -> None:
        self._check("events.unsubscribe")
        self._bus.unsubscribe(event, callback)

    def publish(self, event: str, *args: Any, **kwargs: Any) -> None:
        self._check("events.publish")
        self._bus.publish(event, *args, **kwargs)

    def clear(self) -> None:
        self._check("admin.agents.manage")
        self._bus.clear()

    def _check(self, permission: str) -> None:
        ctx = SecurityContextVar.get()
        if ctx is None:
            return
        ctx.require(permission)


class SecurityServiceRegistry:
    """A security-aware wrapper around ``ServiceRegistry``.

    Wraps ``register``, ``get``, and ``remove`` to enforce permission
    checks.
    """

    def __init__(
        self,
        registry: ServiceRegistry,
        perm_registry: Optional[PermissionRegistry] = None,
    ) -> None:
        self._registry = registry
        self._perm_registry = perm_registry or get_permission_registry()

    def register(self, name: str, service: Any) -> None:
        self._check("services.register")
        self._registry.register(name, service)

    def get(self, name: str) -> Any:
        self._check("services.get")
        return self._registry.get(name)

    def exists(self, name: str) -> bool:
        return self._registry.exists(name)

    def get_optional(self, name: str) -> Any | None:
        return self._registry.get_optional(name)

    def remove(self, name: str) -> None:
        self._check("admin.agents.manage")
        self._registry.remove(name)

    def list_services(self) -> list[str]:
        self._check("services.list")
        return self._registry.list_services()

    def register_lifecycle(self, name: str, lifecycle: Any) -> None:
        self._check("services.register")
        self._registry.register_lifecycle(name, lifecycle)

    def get_lifecycle(self, name: str) -> Any | None:
        return self._registry.get_lifecycle(name)

    def start_all(self) -> None:
        self._check("admin.agents.manage")
        self._registry.start_all()

    def shutdown_all(self) -> None:
        self._check("admin.agents.manage")
        self._registry.shutdown_all()

    def _check(self, permission: str) -> None:
        ctx = SecurityContextVar.get()
        if ctx is None:
            return
        ctx.require(permission)
