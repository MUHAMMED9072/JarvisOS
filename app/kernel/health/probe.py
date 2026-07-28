from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Protocol


@dataclass
class ProbeResult:
    alive: bool = True
    ready: bool = True
    latency_ms: float = 0.0
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


class LivenessCheckable(Protocol):
    def check_liveness(self) -> ProbeResult:
        ...


class ReadinessCheckable(Protocol):
    def check_readiness(self) -> ProbeResult:
        ...


class LivenessProbe:
    """Probes a component's liveness (is it alive and responding?)."""

    def __init__(self, check_callable: Callable[[], ProbeResult] | None = None) -> None:
        self._check = check_callable

    def probe(self, target: Any = None) -> ProbeResult:
        start = time.time()
        try:
            if self._check is not None:
                result = self._check()
            elif target is not None:
                if hasattr(target, "check_liveness"):
                    result = target.check_liveness()
                else:
                    result = ProbeResult(alive=True)
            else:
                result = ProbeResult(alive=True)
            elapsed = (time.time() - start) * 1000
            result.latency_ms = elapsed
            return result
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return ProbeResult(
                alive=False, ready=False, latency_ms=elapsed, error=str(e)
            )


class ReadinessProbe:
    """Probes a component's readiness (is it ready to accept work?)."""

    def __init__(self, check_callable: Callable[[], ProbeResult] | None = None) -> None:
        self._check = check_callable

    def probe(self, target: Any = None) -> ProbeResult:
        start = time.time()
        try:
            if self._check is not None:
                result = self._check()
            elif target is not None:
                if hasattr(target, "check_readiness"):
                    result = target.check_readiness()
                else:
                    result = ProbeResult(alive=True, ready=True)
            else:
                result = ProbeResult(alive=True, ready=True)
            elapsed = (time.time() - start) * 1000
            result.latency_ms = elapsed
            return result
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return ProbeResult(
                alive=False, ready=False, latency_ms=elapsed, error=str(e)
            )


class ProbeRegistry:
    """Manages liveness and readiness probes for registered components."""

    def __init__(self) -> None:
        self._liveness: dict[str, LivenessProbe] = {}
        self._readiness: dict[str, ReadinessProbe] = {}
        self._lock = Lock()

    def register(
        self,
        component_id: str,
        liveness_probe: LivenessProbe | None = None,
        readiness_probe: ReadinessProbe | None = None,
    ) -> None:
        with self._lock:
            if liveness_probe is not None:
                self._liveness[component_id] = liveness_probe
            if readiness_probe is not None:
                self._readiness[component_id] = readiness_probe

    def unregister(self, component_id: str) -> bool:
        with self._lock:
            removed_liveness = self._liveness.pop(component_id, None)
            removed_readiness = self._readiness.pop(component_id, None)
            return removed_liveness is not None or removed_readiness is not None

    def probe_liveness(self, component_id: str) -> ProbeResult:
        probe = self._liveness.get(component_id)
        if probe is None:
            return ProbeResult(alive=True)
        return probe.probe()

    def probe_readiness(self, component_id: str) -> ProbeResult:
        probe = self._readiness.get(component_id)
        if probe is None:
            return ProbeResult(alive=True, ready=True)
        return probe.probe()

    def get_component_ids(self) -> list[str]:
        with self._lock:
            return list(set(self._liveness.keys()) | set(self._readiness.keys()))

    def clear(self) -> None:
        with self._lock:
            self._liveness.clear()
            self._readiness.clear()
