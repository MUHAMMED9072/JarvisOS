from __future__ import annotations

import threading
from typing import Any, Callable, Optional


class ServiceLifecycle:
    """Manages startup and shutdown callbacks for a registered service."""

    def __init__(self) -> None:
        self._on_startup: list[Callable[[], None]] = []
        self._on_shutdown: list[Callable[[], None]] = []

    def on_startup(self, callback: Callable[[], None]) -> None:
        self._on_startup.append(callback)

    def on_shutdown(self, callback: Callable[[], None]) -> None:
        self._on_shutdown.append(callback)

    def run_startup(self) -> None:
        for cb in self._on_startup:
            cb()

    def run_shutdown(self) -> None:
        for cb in reversed(self._on_shutdown):
            cb()


class ServiceRegistry:
    """
    Thread-safe service registry with lifecycle support.

    All public operations are protected by a reentrant lock so the
    registry is safe for concurrent access from multiple threads.

    Supports optional lifecycle hooks per service for ordered
    startup and graceful shutdown.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._services: dict[str, Any] = {}
        self._lifecycles: dict[str, ServiceLifecycle] = {}
        self._startup_order: list[str] = []

    def register(self, name: str, service: Any) -> None:
        with self._lock:
            if name in self._services:
                raise ValueError(f"Service '{name}' is already registered.")
            self._services[name] = service

    def get(self, name: str) -> Any:
        with self._lock:
            if name not in self._services:
                raise KeyError(f"Service '{name}' not found.")
            return self._services[name]

    def exists(self, name: str) -> bool:
        with self._lock:
            return name in self._services

    def get_optional(self, name: str) -> Any | None:
        with self._lock:
            return self._services.get(name)

    def remove(self, name: str) -> None:
        with self._lock:
            self._services.pop(name, None)
            self._lifecycles.pop(name, None)

    def list_services(self) -> list[str]:
        with self._lock:
            return sorted(self._services.keys())

    def register_lifecycle(self, name: str, lifecycle: ServiceLifecycle) -> None:
        """Attach lifecycle hooks to an already-registered service."""
        with self._lock:
            if name not in self._services:
                raise KeyError(f"Cannot attach lifecycle: service '{name}' not found.")
            self._lifecycles[name] = lifecycle

    def get_lifecycle(self, name: str) -> Optional[ServiceLifecycle]:
        with self._lock:
            return self._lifecycles.get(name)

    def start_all(self) -> None:
        """Run startup hooks for all registered services.

        Services are started in registration order. Each service's
        ``on_startup`` hooks are called in the order they were added.
        """
        with self._lock:
            self._startup_order = list(self._services.keys())
        for name in self._startup_order:
            lifecycle = self.get_lifecycle(name)
            if lifecycle:
                lifecycle.run_startup()

    def shutdown_all(self) -> None:
        """Run shutdown hooks for all registered services.

        Services are shut down in reverse registration order. Errors
        from individual shutdown hooks are caught and isolated so that
        a single failure never prevents remaining services from
        shutting down.
        """
        with self._lock:
            order = list(reversed(self._startup_order)) if self._startup_order else list(reversed(list(self._services.keys())))
        for name in order:
            lifecycle = self.get_lifecycle(name)
            if lifecycle:
                try:
                    lifecycle.run_shutdown()
                except Exception:
                    continue
