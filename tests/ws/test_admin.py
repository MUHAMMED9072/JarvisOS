"""Tests for Remote Administration over WebSockets (P12-07)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.registry import ServiceRegistry
from app.ws.admin import AdminManager
from app.ws.manager import WebSocketConnectionManager
from app.ws.schemas import ServerMessage, WSMessageType


# ==========================================================================
# Helpers
# ==========================================================================


def _make_msg(msg_type: str, **payload: Any) -> str:
    return json.dumps({"type": msg_type, "payload": payload})


def _get_sent_type(ws_mock: AsyncMock, index: int = 0) -> str:
    call_args = ws_mock.send.call_args_list[index]
    msg: ServerMessage = call_args[0][1]
    return msg.type.value


def _get_sent_payload(ws_mock: AsyncMock, index: int = 0) -> dict:
    call_args = ws_mock.send.call_args_list[index]
    msg: ServerMessage = call_args[0][1]
    return msg.payload


def _make_registry(**overrides: Any) -> MagicMock:
    """Create a mock registry with standard services."""
    registry = MagicMock(spec=ServiceRegistry)

    services: dict[str, Any] = {
        "plugin_manager": MagicMock(),
        "skill_manager": MagicMock(),
        "memory": MagicMock(),
        "voice_manager": MagicMock(),
        "ai_manager": MagicMock(),
        "kernel": MagicMock(),
    }
    services.update(overrides)

    def get_side_effect(name: str) -> Any:
        if name in services:
            return services[name]
        raise KeyError(f"Service {name!r} not found")

    registry.get = MagicMock(side_effect=get_side_effect)
    registry.get_optional = MagicMock(side_effect=lambda name: services.get(name))
    return registry


def _make_ws() -> AsyncMock:
    ws = AsyncMock(spec=WebSocketConnectionManager)
    ws.is_connected = AsyncMock(return_value=True)
    ws.send = AsyncMock(return_value=True)
    ws.get_connection = MagicMock()
    ws.get_connected_ids = AsyncMock(return_value=["client-1"])
    ws.get_active_count = AsyncMock(return_value=1)
    return ws


def _request_id() -> str:
    return "req-001"


def _correlation_id() -> str:
    return "corr-001"


def _base_payload(**kw: Any) -> dict:
    p = {
        "request_id": _request_id(),
        "correlation_id": _correlation_id(),
        "timestamp": "2026-07-27T08:00:00",
    }
    p.update(kw)
    return p


async def _make_env(**kwargs: Any) -> tuple[AdminManager, AsyncMock]:
    ws = _make_ws()
    registry = kwargs.pop("registry", None) or _make_registry()

    ws.is_connected = AsyncMock(return_value=True)
    ws.send = AsyncMock(return_value=True)
    ws.get_connection = MagicMock(
        return_value=MagicMock(
            metadata={},
            rooms=set(),
            subscriptions=set(),
            connected_at=1000.0,
        ),
    )
    ws.get_connected_ids = AsyncMock(return_value=["client-1", "client-2"])
    ws.get_active_count = AsyncMock(return_value=2)

    monitor = kwargs.pop("monitor", MagicMock())
    if monitor:
        monitor.running = True
        monitor.snapshot = AsyncMock(return_value={"cpu": {"percent": 25.0}})
        monitor.get_interval = AsyncMock(return_value=5.0)
        monitor.get_thresholds = AsyncMock(return_value={"cpu_percent": 90.0})
        monitor.set_interval = AsyncMock()
        monitor.start = MagicMock()
        monitor.stop = AsyncMock()

    mgr = AdminManager(
        ws_manager=ws,
        registry=registry,
        kernel=kwargs.pop("kernel", MagicMock()),
        system_monitor=monitor,
    )
    return mgr, ws


# ==========================================================================
# Tests
# ==========================================================================


class TestPing:
    """admin.ping → admin.pong."""

    @pytest.mark.asyncio
    async def test_ping_responds_with_pong(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.ping", **_base_payload()),
        )
        assert handled is True
        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_PONG.value
        payload = _get_sent_payload(ws, 0)
        assert payload.get("message") == "pong"
        assert payload.get("request_id") == _request_id()
        assert payload.get("correlation_id") == _correlation_id()
        assert payload.get("success") is True


class TestStatus:
    """admin.status → admin.status with server info."""

    @pytest.mark.asyncio
    async def test_status_returns_data(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.status", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)

        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_STATUS_RESPONSE.value
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True
        assert "connected_clients" in payload


class TestInfo:
    """admin.info → admin.info with server details."""

    @pytest.mark.asyncio
    async def test_info_returns_server_info(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.info", **_base_payload()),
        )
        assert handled is True
        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_INFO_RESPONSE.value
        payload = _get_sent_payload(ws, 0)
        assert payload.get("app_name") == "JARVIS OS"
        assert "version" in payload
        assert "python_version" in payload


class TestShutdown:
    """admin.shutdown → admin.shutdown response."""

    @pytest.mark.asyncio
    async def test_shutdown_responds(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.shutdown", **_base_payload()),
        )
        assert handled is True
        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_SHUTDOWN_RESPONSE.value
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True
        assert "shutdown" in payload.get("message", "")


class TestRestart:
    """admin.restart → admin.restart response."""

    @pytest.mark.asyncio
    async def test_restart_responds(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.restart", **_base_payload()),
        )
        assert handled is True
        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_RESTART_RESPONSE.value
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True


class TestClients:
    """admin.clients → admin.clients with connected clients."""

    @pytest.mark.asyncio
    async def test_clients_returns_client_list(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.clients", **_base_payload()),
        )
        assert handled is True
        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_CLIENTS_RESPONSE.value
        payload = _get_sent_payload(ws, 0)
        assert payload.get("count", 0) >= 1
        assert "clients" in payload


class TestPlugins:
    """Plugin administration."""

    @pytest.mark.asyncio
    async def test_list_plugins(self) -> None:
        registry = _make_registry()
        pm = registry.get_optional("plugin_manager")
        pm.list_plugins = MagicMock(return_value=["plugin_a", "plugin_b"])
        pm.get_manifest = MagicMock(
            side_effect=lambda n: MagicMock(
                version="1.0", description="desc", author="author",
            ),
        )
        pm.get_plugin = MagicMock(return_value=MagicMock(_disabled=False))

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.plugins", action="list", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True
        assert "plugins" in payload
        assert len(payload["plugins"]) == 2

    @pytest.mark.asyncio
    async def test_get_plugin(self) -> None:
        registry = _make_registry()
        pm = registry.get_optional("plugin_manager")
        pm.get_manifest = MagicMock(
            return_value=MagicMock(version="2.0", description="Test plugin", author="Tester"),
        )
        pm.get_plugin = MagicMock(return_value=MagicMock(_disabled=False))

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.plugins", action="get", name="test_plugin", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        payload = _get_sent_payload(ws, 0)
        assert payload.get("name") == "test_plugin"

    @pytest.mark.asyncio
    async def test_enable_plugin(self) -> None:
        registry = _make_registry()
        pm = registry.get_optional("plugin_manager")
        pm.enable = MagicMock()

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.plugins", action="enable", name="my_plugin", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        assert pm.enable.called

    @pytest.mark.asyncio
    async def test_disable_plugin(self) -> None:
        registry = _make_registry()
        pm = registry.get_optional("plugin_manager")
        pm.disable = MagicMock()

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.plugins", action="disable", name="my_plugin", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        assert pm.disable.called

    @pytest.mark.asyncio
    async def test_unknown_plugin_action(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.plugins", action="unknown", **_base_payload()),
        )
        assert handled is True
        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_ERROR.value


class TestSkills:
    """Skill administration."""

    @pytest.mark.asyncio
    async def test_list_skills(self) -> None:
        registry = _make_registry()
        sm = registry.get_optional("skill_manager")

        skill_a = MagicMock(name="skill_a", intent="intent_a", version="1.0", description="desc_a", author="auth_a")
        skill_b = MagicMock(name="skill_b", intent="intent_b", version="2.0", description="desc_b", author="auth_b")
        sm.all_skills = MagicMock(return_value=[skill_a, skill_b])

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.skills", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True
        assert payload.get("count") == 2
        assert len(payload.get("skills", [])) == 2


class TestMemory:
    """Memory administration."""

    @pytest.mark.asyncio
    async def test_memory_stats(self) -> None:
        registry = _make_registry()
        mem = registry.get_optional("memory")
        mem.get_recent = MagicMock(return_value=[{"role": "user"}, {"role": "assistant"}])
        mem.get_session_messages = MagicMock(return_value=[{"role": "user"}])

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.memory", action="stats", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True
        assert payload.get("entries") == 2
        assert payload.get("session_messages") == 1

    @pytest.mark.asyncio
    async def test_memory_prune(self) -> None:
        registry = _make_registry()
        mem = registry.get_optional("memory")
        mem.prune_all = MagicMock(return_value=5)

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.memory", action="prune", ttl_days=30, **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        payload = _get_sent_payload(ws, 0)
        assert payload.get("action") == "prune"
        assert payload.get("removed") == 5

    @pytest.mark.asyncio
    async def test_memory_clear(self) -> None:
        registry = _make_registry()
        mem = registry.get_optional("memory")
        mem.clear = MagicMock()

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.memory", action="clear", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        assert mem.clear.called
        payload = _get_sent_payload(ws, 0)
        assert payload.get("action") == "clear"

    @pytest.mark.asyncio
    async def test_unknown_memory_action(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.memory", action="unknown", **_base_payload()),
        )
        assert handled is True
        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_ERROR.value


class TestVoice:
    """Voice administration."""

    @pytest.mark.asyncio
    async def test_voice_status(self) -> None:
        registry = _make_registry()
        vm = registry.get_optional("voice_manager")
        vm.is_running = MagicMock(return_value=True)

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.voice", action="status", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        payload = _get_sent_payload(ws, 0)
        assert payload.get("running") is True

    @pytest.mark.asyncio
    async def test_voice_start(self) -> None:
        registry = _make_registry()
        vm = registry.get_optional("voice_manager")
        vm.start = MagicMock()

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.voice", action="start", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        assert vm.start.called

    @pytest.mark.asyncio
    async def test_voice_stop(self) -> None:
        registry = _make_registry()
        vm = registry.get_optional("voice_manager")
        vm.stop = MagicMock()

        mgr, ws = await _make_env(monitor=None, registry=registry)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.voice", action="stop", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.1)
        assert vm.stop.called

    @pytest.mark.asyncio
    async def test_unknown_voice_action(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.voice", action="unknown", **_base_payload()),
        )
        assert handled is True
        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_ERROR.value


class TestMonitor:
    """Monitor administration."""

    @pytest.mark.asyncio
    async def test_monitor_snapshot(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.monitor", action="snapshot", **_base_payload()),
        )
        assert handled is True
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True
        assert "snapshot" in payload
        assert payload.get("running") is True

    @pytest.mark.asyncio
    async def test_monitor_set_interval(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.monitor", action="set_interval", interval=10.0, **_base_payload()),
        )
        assert handled is True
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True

    @pytest.mark.asyncio
    async def test_monitor_start(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.monitor", action="start", **_base_payload()),
        )
        assert handled is True
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True

    @pytest.mark.asyncio
    async def test_monitor_stop(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.monitor", action="stop", **_base_payload()),
        )
        assert handled is True
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True

    @pytest.mark.asyncio
    async def test_unknown_monitor_action(self) -> None:
        mgr, ws = await _make_env()
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.monitor", action="unknown", **_base_payload()),
        )
        assert handled is True
        assert _get_sent_type(ws, 0) == WSMessageType.ADMIN_ERROR.value


class TestConfig:
    """Runtime configuration query."""

    @pytest.mark.asyncio
    async def test_config_all_keys(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.config", **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.05)
        payload = _get_sent_payload(ws, 0)
        assert payload.get("success") is True
        assert "app_name" in payload
        assert "version" in payload
        assert "max_file_size" in payload

    @pytest.mark.asyncio
    async def test_config_filtered_keys(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.config", keys=["version", "app_name"], **_base_payload()),
        )
        assert handled is True
        await asyncio.sleep(0.05)
        payload = _get_sent_payload(ws, 0)
        assert "version" in payload
        assert "app_name" in payload
        assert "max_file_size" not in payload


class TestMetadata:
    """Request/response metadata preservation."""

    @pytest.mark.asyncio
    async def test_request_id_preserved(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.ping", request_id="my-req-42", correlation_id="my-corr-99"),
        )
        assert handled is True
        payload = _get_sent_payload(ws, 0)
        assert payload.get("request_id") == "my-req-42"
        assert payload.get("correlation_id") == "my-corr-99"
        assert payload.get("success") is True


class TestError:
    """Error handling."""

    @pytest.mark.asyncio
    async def test_unknown_admin_type(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.nonexistent", **_base_payload()),
        )
        assert handled is False
        assert ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_non_admin_type_ignored(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"

        handled = await mgr.try_handle_message(cid, _make_msg("ping"))
        assert handled is False

        handled = await mgr.try_handle_message(cid, _make_msg("subscribe", event="test"))
        assert handled is False

        handled = await mgr.try_handle_message(cid, _make_msg("command.execute"))
        assert handled is False

        handled = await mgr.try_handle_message(cid, _make_msg("file.upload.start"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_invalid_json(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"

        handled = await mgr.try_handle_message(cid, "not json{{{")
        assert handled is False

    @pytest.mark.asyncio
    async def test_send_result_when_disconnected(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid = "admin-1"
        ws.is_connected = AsyncMock(return_value=False)

        handled = await mgr.try_handle_message(
            cid, _make_msg("admin.ping", **_base_payload()),
        )
        assert handled is True
        assert ws.send.call_count == 0


class TestMultipleClients:
    """Concurrent administrators."""

    @pytest.mark.asyncio
    async def test_multiple_admins(self) -> None:
        mgr, ws = await _make_env(monitor=None)
        cid1 = "admin-1"
        cid2 = "admin-2"

        handled1 = await mgr.try_handle_message(
            cid1, _make_msg("admin.ping", **_base_payload()),
        )
        handled2 = await mgr.try_handle_message(
            cid2, _make_msg("admin.ping", **_base_payload()),
        )
        assert handled1 and handled2
        assert ws.send.call_count == 2
