from __future__ import annotations

from typing import Any


class WebSocketRuntimeConfig:
    """Runtime-updatable configuration for the WebSocket subsystem.

    Changes immediately affect running services where safe to do so.
    """

    _DEFAULTS: dict[str, Any] = {
        "heartbeat_interval": 30.0,
        "heartbeat_timeout": 10.0,
        "max_retries": 3,
        "retry_interval": 5.0,
        "ack_timeout": 30.0,
        "offline_queue_maxsize": 100,
        "offline_queue_overflow": "drop_oldest",
        "reconnect_token_expiry": 300.0,
        "max_event_queue_size": 100,
        "compression_enabled": False,
        "compression_min_size": 4096,
        "rate_limit_max_messages": 120,
        "rate_limit_window": 60,
        "session_expiry": 3600.0,
    }

    def __init__(self, ws_manager: Any, config: Any = None) -> None:
        self._ws = ws_manager
        self._config = config
        self._overrides: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        if self._config is not None:
            attr_map = {
                "heartbeat_interval": "WS_HEARTBEAT_INTERVAL",
                "heartbeat_timeout": "WS_HEARTBEAT_TIMEOUT",
                "max_retries": "WS_MAX_RETRIES",
                "retry_interval": "WS_RETRY_INTERVAL",
                "ack_timeout": "WS_ACK_TIMEOUT",
                "offline_queue_maxsize": "WS_OFFLINE_QUEUE_MAXSIZE",
                "offline_queue_overflow": "WS_OFFLINE_QUEUE_OVERFLOW",
                "reconnect_token_expiry": "WS_RECONNECT_TOKEN_EXPIRY",
                "max_event_queue_size": "WS_MAX_EVENT_QUEUE_SIZE",
                "compression_enabled": "WS_COMPRESSION_ENABLED",
                "compression_min_size": "WS_COMPRESSION_MIN_SIZE",
                "rate_limit_max_messages": "WS_MAX_MESSAGES_PER_MINUTE",
                "rate_limit_window": None,
                "session_expiry": "WS_SESSION_EXPIRY",
            }
            attr = attr_map.get(key)
            if attr and hasattr(self._config, attr):
                return getattr(self._config, attr)
        return self._DEFAULTS.get(key)

    def set(self, key: str, value: Any) -> bool:
        if key not in self._DEFAULTS:
            return False

        self._overrides[key] = value

        ws = self._ws
        if key == "heartbeat_interval" and hasattr(ws, "_heartbeat_interval"):
            ws._heartbeat_interval = float(value)
        elif key == "heartbeat_timeout" and hasattr(ws, "_heartbeat_timeout"):
            ws._heartbeat_timeout = float(value)

        return True

    def get_all(self) -> dict[str, Any]:
        result = {}
        for key in self._DEFAULTS:
            result[key] = self.get(key)
        return result

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._overrides.clear()
        else:
            self._overrides.pop(key, None)
