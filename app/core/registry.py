from __future__ import annotations

import threading
from typing import Any


class ServiceRegistry:
    """
    Central registry for all JARVIS services.

    All public operations are protected by a reentrant lock so the
    registry is safe for concurrent access from multiple threads.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._services: dict[str, Any] = {}

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

    def remove(self, name: str) -> None:
        with self._lock:
            self._services.pop(name, None)

    def list_services(self) -> list[str]:
        with self._lock:
            return sorted(self._services.keys())
