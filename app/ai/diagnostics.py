from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestStats:
    total: int = 0
    success: int = 0
    failure: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0


class ProviderStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_latency_ms = 0.0
        self.min_latency_ms = 0.0
        self.max_latency_ms = 0.0
        self.retry_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "total_latency_ms": self.total_latency_ms,
                "min_latency_ms": self.min_latency_ms,
                "max_latency_ms": self.max_latency_ms,
                "retry_count": self.retry_count,
                "total_prompt_tokens": self.total_prompt_tokens,
                "total_completion_tokens": self.total_completion_tokens,
            }

    def reset(self) -> None:
        with self._lock:
            self.total_requests = 0
            self.successful_requests = 0
            self.failed_requests = 0
            self.total_latency_ms = 0.0
            self.min_latency_ms = 0.0
            self.max_latency_ms = 0.0
            self.retry_count = 0
            self.total_prompt_tokens = 0
            self.total_completion_tokens = 0


class _ThreadSafeCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total = 0
        self.success = 0
        self.failure = 0
        self.total_latency_ms = 0.0
        self.min_latency_ms = 0.0
        self.max_latency_ms = 0.0

    def record(self, success: bool, latency_ms: float = 0.0) -> None:
        with self._lock:
            self.total += 1
            if success:
                self.success += 1
            else:
                self.failure += 1
            if latency_ms > 0:
                self.total_latency_ms += latency_ms
                if self.min_latency_ms == 0.0 or latency_ms < self.min_latency_ms:
                    self.min_latency_ms = latency_ms
                if latency_ms > self.max_latency_ms:
                    self.max_latency_ms = latency_ms

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total": self.total,
                "success": self.success,
                "failure": self.failure,
                "total_latency_ms": self.total_latency_ms,
                "min_latency_ms": self.min_latency_ms,
                "max_latency_ms": self.max_latency_ms,
            }

    def reset(self) -> None:
        with self._lock:
            self.total = 0
            self.success = 0
            self.failure = 0
            self.total_latency_ms = 0.0
            self.min_latency_ms = 0.0
            self.max_latency_ms = 0.0


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._providers: dict[str, ProviderStats] = {}
        self._start_time = time.monotonic()

        self.requests = _ThreadSafeCounter()
        self.routing = _ThreadSafeCounter()
        self.streaming = _ThreadSafeCounter()
        self.planning = _ThreadSafeCounter()
        self.reasoning = _ThreadSafeCounter()
        self.tools = _ThreadSafeCounter()
        self.conversations = _ThreadSafeCounter()
        self.memory = _ThreadSafeCounter()
        self.errors = _ThreadSafeCounter()
        self.retries = _ThreadSafeCounter()

    def for_provider(self, name: str) -> ProviderStats:
        with self._lock:
            if name not in self._providers:
                self._providers[name] = ProviderStats()
            return self._providers[name]

    def record_provider_request(
        self,
        provider: str,
        success: bool,
        latency_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        with self._lock:
            ps = self._providers.get(provider)
            if ps is None:
                ps = ProviderStats()
                self._providers[provider] = ps
            with ps._lock:
                ps.total_requests += 1
                if success:
                    ps.successful_requests += 1
                else:
                    ps.failed_requests += 1
                if latency_ms > 0:
                    ps.total_latency_ms += latency_ms
                    if ps.min_latency_ms == 0.0 or latency_ms < ps.min_latency_ms:
                        ps.min_latency_ms = latency_ms
                    if latency_ms > ps.max_latency_ms:
                        ps.max_latency_ms = latency_ms
                ps.total_prompt_tokens += prompt_tokens
                ps.total_completion_tokens += completion_tokens

    def record_provider_retry(self, provider: str, attempt: int) -> None:
        with self._lock:
            ps = self._providers.get(provider)
            if ps is None:
                ps = ProviderStats()
                self._providers[provider] = ps
            with ps._lock:
                ps.retry_count += 1

    def record_retry(self, attempt: int, max_retries: int, error_type: str) -> None:
        self.retries.record(True)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            providers = {
                name: ps.snapshot()
                for name, ps in self._providers.items()
            }
            return {
                "requests": self.requests.snapshot(),
                "routing": self.routing.snapshot(),
                "streaming": self.streaming.snapshot(),
                "planning": self.planning.snapshot(),
                "reasoning": self.reasoning.snapshot(),
                "tools": self.tools.snapshot(),
                "conversations": self.conversations.snapshot(),
                "memory": self.memory.snapshot(),
                "errors": self.errors.snapshot(),
                "retries": self.retries.snapshot(),
                "providers": providers,
                "uptime_seconds": time.monotonic() - self._start_time,
                "timestamp": time.time(),
            }

    def reset(self) -> None:
        with self._lock:
            self.requests.reset()
            self.routing.reset()
            self.streaming.reset()
            self.planning.reset()
            self.reasoning.reset()
            self.tools.reset()
            self.conversations.reset()
            self.memory.reset()
            self.errors.reset()
            self.retries.reset()
            self._providers.clear()
            self._start_time = time.monotonic()


class AIDiagnosticsService:
    def __init__(self, metrics_collector: MetricsCollector | None = None) -> None:
        self._metrics = metrics_collector or MetricsCollector()

    @property
    def metrics(self) -> MetricsCollector:
        return self._metrics

    def snapshot(self, router: Any = None) -> dict[str, Any]:
        from app.core.config import Config

        ms = self._metrics.snapshot()
        health = self._check_health(router) if router else {}

        result: dict[str, Any] = {
            "uptime_seconds": ms["uptime_seconds"],
            "timestamp": ms["timestamp"],
            "requests": ms["requests"],
            "routing": ms["routing"],
            "streaming": ms["streaming"],
            "planning": ms["planning"],
            "reasoning": ms["reasoning"],
            "tools": ms["tools"],
            "conversations": ms["conversations"],
            "memory": ms["memory"],
            "errors": ms["errors"],
            "retries": ms["retries"],
            "providers": ms["providers"],
            "health": health,
            "features": {
                "streaming": Config.AI.features.streaming,
                "function_calling": Config.AI.features.function_calling,
                "embeddings": Config.AI.features.embeddings,
                "image_input": Config.AI.features.image_input,
                "json_output": Config.AI.features.json_output,
                "conversation": Config.AI.features.conversation,
                "system_prompt": Config.AI.features.system_prompt,
                "reasoning": Config.AI.features.reasoning,
                "planning": Config.AI.features.planning,
                "memory_integration": Config.AI.features.memory_integration,
                "event_publishing": Config.AI.features.event_publishing,
            },
        }
        return result

    def _check_health(self, router: Any) -> dict[str, dict[str, Any]]:
        health: dict[str, dict[str, Any]] = {}
        for name in router.providers:
            status = router.provider_status(name)
            health[name] = {
                "available": status.name == "AVAILABLE",
                "status": status.name,
            }
        return health

    def reset(self) -> None:
        self._metrics.reset()
