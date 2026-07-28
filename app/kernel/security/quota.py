from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ResourceType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    API_CALLS = "api_calls"


@dataclass
class ResourceQuota:
    """Defines a resource limit for a particular resource type.

    ``soft_limit`` triggers a warning when exceeded.
    ``hard_limit`` is the absolute maximum (operations denied beyond this).
    ``window_seconds`` is only relevant for rate-limited resources
    (e.g. API calls per minute).

    A value of ``-1`` means "unlimited".
    """

    resource_type: ResourceType
    soft_limit: float = -1.0
    hard_limit: float = -1.0
    window_seconds: float = 60.0
    current_usage: float = 0.0
    peak_usage: float = 0.0

    def is_unlimited(self) -> bool:
        return self.hard_limit < 0

    def is_exceeded(self, usage: float | None = None) -> bool:
        if self.is_unlimited():
            return False
        return (usage if usage is not None else self.current_usage) > self.hard_limit

    def is_warning(self, usage: float | None = None) -> bool:
        if self.soft_limit < 0:
            return False
        return (usage if usage is not None else self.current_usage) > self.soft_limit

    def record(self, amount: float) -> None:
        self.current_usage += amount
        if self.current_usage > self.peak_usage:
            self.peak_usage = self.current_usage

    def reset(self) -> None:
        self.current_usage = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type.value,
            "soft_limit": self.soft_limit,
            "hard_limit": self.hard_limit,
            "window_seconds": self.window_seconds,
            "current_usage": self.current_usage,
            "peak_usage": self.peak_usage,
        }


class QuotaExceeded(Exception):
    """Raised when a hard quota limit is exceeded."""

    def __init__(
        self,
        actor: str,
        resource_type: ResourceType,
        limit: float,
        current: float,
    ) -> None:
        self.actor = actor
        self.resource_type = resource_type
        self.limit = limit
        self.current = current
        super().__init__(
            f"Quota exceeded for {actor!r} on {resource_type.value}: "
            f"{current:.1f} > {limit:.1f}"
        )


@dataclass
class QuotaResult:
    """Result of a quota check."""

    allowed: bool
    exceeded: bool = False
    warning: bool = False
    resource_type: Optional[ResourceType] = None
    current_usage: float = 0.0
    hard_limit: float = -1.0
    message: str = ""


class QuotaRegistry:
    """Thread-safe registry for resource quotas per actor.

    Supports:
    - Registration of quotas per actor (or default quotas)
    - Checking quotas before resource consumption
    - Recording resource usage
    - Periodic or explicit reset of windowed quotas
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._defaults: dict[ResourceType, ResourceQuota] = {}
        self._quotas: dict[str, dict[ResourceType, ResourceQuota]] = defaultdict(dict)
        self._window_starts: dict[str, dict[ResourceType, float]] = defaultdict(dict)

    def set_default(self, quota: ResourceQuota) -> None:
        with self._lock:
            self._defaults[quota.resource_type] = quota

    def get_default(self, resource_type: ResourceType) -> Optional[ResourceQuota]:
        with self._lock:
            return self._defaults.get(resource_type)

    def set_quota(self, actor: str, quota: ResourceQuota) -> None:
        with self._lock:
            self._quotas[actor][quota.resource_type] = quota
            if actor not in self._window_starts or quota.resource_type not in self._window_starts.get(actor, {}):
                self._window_starts[actor][quota.resource_type] = time.time()

    def get_quota(self, actor: str, resource_type: ResourceType) -> ResourceQuota:
        with self._lock:
            q = self._quotas.get(actor, {}).get(resource_type)
            if q is None:
                default = self._defaults.get(resource_type)
                if default is not None:
                    q = ResourceQuota(
                        resource_type=resource_type,
                        soft_limit=default.soft_limit,
                        hard_limit=default.hard_limit,
                        window_seconds=default.window_seconds,
                    )
                    self._quotas[actor][resource_type] = q
                else:
                    q = ResourceQuota(resource_type=resource_type)
                    self._quotas[actor][resource_type] = q
                self._window_starts[actor][resource_type] = time.time()
            return q

    def remove_actor(self, actor: str) -> None:
        with self._lock:
            self._quotas.pop(actor, None)
            self._window_starts.pop(actor, None)

    def list_actors(self) -> list[str]:
        with self._lock:
            return sorted(self._quotas.keys())

    def check(
        self,
        actor: str,
        resource_type: ResourceType,
        amount: float = 1.0,
    ) -> QuotaResult:
        """Check whether *actor* may consume *amount* of *resource_type*.

        This does **not** record the consumption — use ``consume()`` for that.
        """
        quota = self.get_quota(actor, resource_type)
        if quota.is_unlimited():
            return QuotaResult(allowed=True, resource_type=resource_type)

        self._check_window(actor, resource_type, quota)
        projected = quota.current_usage + amount

        if quota.is_exceeded(projected):
            return QuotaResult(
                allowed=False,
                exceeded=True,
                resource_type=resource_type,
                current_usage=quota.current_usage,
                hard_limit=quota.hard_limit,
                message=f"{resource_type.value} quota exceeded for {actor!r}",
            )
        if quota.is_warning(projected):
            return QuotaResult(
                allowed=True,
                warning=True,
                resource_type=resource_type,
                current_usage=quota.current_usage,
                hard_limit=quota.hard_limit,
                message=f"{resource_type.value} quota warning for {actor!r}",
            )
        return QuotaResult(allowed=True, resource_type=resource_type)

    def consume(
        self,
        actor: str,
        resource_type: ResourceType,
        amount: float = 1.0,
    ) -> QuotaResult:
        """Check quota and record consumption.  Raises ``QuotaExceeded``
        if the hard limit would be breached."""
        result = self.check(actor, resource_type, amount)
        if not result.allowed:
            raise QuotaExceeded(
                actor, resource_type, result.hard_limit, result.current_usage
            )
        with self._lock:
            quota = self._quotas.get(actor, {}).get(resource_type)
            if quota:
                quota.record(amount)
        return result

    def reset_actor(self, actor: str) -> None:
        with self._lock:
            quotas = self._quotas.get(actor, {})
            for q in quotas.values():
                q.reset()

    def reset_all(self) -> None:
        with self._lock:
            for quotas in self._quotas.values():
                for q in quotas.values():
                    q.reset()

    def get_stats(self, actor: str) -> dict[str, Any]:
        with self._lock:
            quotas = self._quotas.get(actor, {})
            return {
                rt.value: q.to_dict() for rt, q in quotas.items()
            }

    def _check_window(self, actor: str, resource_type: ResourceType, quota: ResourceQuota) -> None:
        """Reset windowed quotas if the time window has elapsed."""
        now = time.time()
        window_start = self._window_starts.get(actor, {}).get(resource_type, now)
        if now - window_start >= quota.window_seconds:
            with self._lock:
                self._window_starts[actor][resource_type] = now
                q = self._quotas.get(actor, {}).get(resource_type)
                if q:
                    q.reset()
