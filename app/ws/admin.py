from __future__ import annotations

import asyncio
import fnmatch
import json
import time
import uuid
from typing import Any

from app.core.logger import JarvisLogger
from app.ws.manager import WebSocketConnectionManager
from app.ws.schemas import ServerMessage, WSMessageType


class AdminManager:
    """Remote administration over WebSocket connections.

    Provides server introspection, plugin/skill/memory/voice/monitor
    management, runtime configuration queries, lifecycle control,
    and WebSocket observability (metrics, health, diagnostics,
    maintenance, runtime config).
    """

    def __init__(
        self,
        ws_manager: WebSocketConnectionManager,
        registry: Any,
        *,
        kernel: Any = None,
        system_monitor: Any = None,
        ws_metrics: Any = None,
        ws_health: Any = None,
        ws_diagnostics: Any = None,
        ws_maintenance: Any = None,
        ws_runtime_config: Any = None,
    ) -> None:
        self._ws = ws_manager
        self._registry = registry
        self._kernel = kernel
        self._monitor = system_monitor
        self._ws_metrics = ws_metrics
        self._ws_health = ws_health
        self._ws_diagnostics = ws_diagnostics
        self._ws_maintenance = ws_maintenance
        self._ws_runtime_config = ws_runtime_config

    # ------------------------------------------------------------------
    # Incoming message routing
    # ------------------------------------------------------------------

    async def try_handle_message(
        self,
        client_id: str,
        raw: str,
    ) -> bool:
        try:
            data = json.loads(raw)
            msg_type = data.get("type")
        except json.JSONDecodeError:
            return False

        payload: dict = data.get("payload") or {}

        handler = self._handlers().get(msg_type)
        if handler is None:
            return False

        await handler(client_id, payload)
        return True

    def _handlers(self) -> dict[str, Any]:
        return {
            "admin.ping": self._handle_ping,
            "admin.status": self._handle_status,
            "admin.info": self._handle_info,
            "admin.shutdown": self._handle_shutdown,
            "admin.restart": self._handle_restart,
            "admin.clients": self._handle_clients,
            "admin.plugins": self._handle_plugins,
            "admin.skills": self._handle_skills,
            "admin.memory": self._handle_memory,
            "admin.voice": self._handle_voice,
            "admin.monitor": self._handle_monitor,
            "admin.config": self._handle_config,
            # P12-10 WS Observability
            "admin.ws.metrics": self._handle_ws_metrics,
            "admin.ws.health": self._handle_ws_health,
            "admin.ws.diagnostics": self._handle_ws_diagnostics,
            "admin.ws.reset_metrics": self._handle_ws_reset_metrics,
            "admin.ws.maintenance": self._handle_ws_maintenance,
            "admin.ws.runtime_config": self._handle_ws_runtime_config,
        }

    # ------------------------------------------------------------------
    # Permission check
    # ------------------------------------------------------------------

    async def _check_permission(
        self,
        client_id: str,
        permission: str,
    ) -> bool:
        info = self._ws.get_connection(client_id)
        if info is None:
            return False
        metadata = info.metadata or {}
        if not isinstance(metadata, dict):
            return True
        session_id = metadata.get("session_id")
        if not session_id:
            return True
        roles = metadata.get("roles", [])
        if "admin" in roles:
            return True
        permissions = metadata.get("permissions", set())
        if isinstance(permissions, list):
            permissions = set(permissions)
        if permission in permissions:
            return True
        for perm_pattern in permissions:
            if fnmatch.fnmatch(permission, perm_pattern):
                return True
        return False

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_ping(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        await self._respond(client_id, payload, "admin.pong", {"message": "pong"})

    async def _handle_status(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.status"):
            await self._err(client_id, payload, "permission denied")
            return

        loop = asyncio.get_running_loop()

        def _collect() -> dict[str, Any]:
            data: dict[str, Any] = {
                "connected_clients": 0,
                "plugins": 0,
                "skills": 0,
                "memory_entries": 0,
                "voice_running": False,
                "active_conversations": 0,
                "monitor_running": False,
            }

            pm = self._registry.get_optional("plugin_manager")
            if pm:
                data["plugins"] = len(pm.list_plugins())

            sm = self._registry.get_optional("skill_manager")
            if sm and hasattr(sm, "skills"):
                data["skills"] = len(sm.skills)

            mem = self._registry.get_optional("memory")
            if mem:
                recent = mem.get_recent(limit=0)
                data["memory_entries"] = len(recent) if recent else 0

            vm = self._registry.get_optional("voice_manager")
            if vm:
                data["voice_running"] = vm.is_running()

            ai_mgr = self._registry.get_optional("ai_manager")
            if ai_mgr:
                cm = getattr(ai_mgr, "conversation_manager", None)
                if cm and hasattr(cm, "conversations"):
                    data["active_conversations"] = len(cm.conversations)

            if self._monitor:
                data["monitor_running"] = self._monitor.running

            return data

        info = await loop.run_in_executor(None, _collect)
        ws_count = await self._ws.get_active_count()
        info["connected_clients"] = ws_count

        await self._respond(client_id, payload, "admin.status", info)

    async def _handle_info(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.info"):
            await self._err(client_id, payload, "permission denied")
            return

        from app.core.config import Config

        data = {
            "app_name": Config.APP_NAME,
            "version": Config.VERSION,
            "python_version": __import__("sys").version,
            "platform": __import__("sys").platform,
        }
        await self._respond(client_id, payload, "admin.info", data)

    async def _handle_shutdown(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.shutdown"):
            await self._err(client_id, payload, "permission denied")
            return

        await self._respond(
            client_id, payload, "admin.shutdown",
            {"message": "shutdown initiated"},
        )

        if self._kernel is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._kernel.shutdown)

        loop = asyncio.get_running_loop()
        loop.call_soon(loop.stop)

    async def _handle_restart(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.restart"):
            await self._err(client_id, payload, "permission denied")
            return

        if self._kernel is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._kernel.shutdown)

        await self._respond(
            client_id, payload, "admin.restart",
            {"message": "restart signal sent"},
        )

    async def _handle_clients(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.clients"):
            await self._err(client_id, payload, "permission denied")
            return

        ids = await self._ws.get_connected_ids()
        clients = []
        for cid in ids:
            info = self._ws.get_connection(cid)
            clients.append({
                "client_id": cid,
                "connected_at": info.connected_at if info else 0,
                "rooms": list(info.rooms) if info else [],
                "subscriptions": list(info.subscriptions) if info else [],
            })

        await self._respond(
            client_id, payload, "admin.clients",
            {"count": len(clients), "clients": clients},
        )

    async def _handle_plugins(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.plugins"):
            await self._err(client_id, payload, "permission denied")
            return

        action = payload.get("action", "list")
        pm = self._registry.get_optional("plugin_manager")
        loop = asyncio.get_running_loop()

        if action == "list":
            if pm is None:
                await self._respond(client_id, payload, "admin.plugins", {"plugins": []})
                return
            names = await loop.run_in_executor(None, pm.list_plugins)
            plugins = []
            for name in names:
                manifest = pm.get_manifest(name)
                plugin_obj = pm.get_plugin(name)
                enabled = not getattr(plugin_obj, "_disabled", False) if plugin_obj else False
                plugins.append({
                    "name": name,
                    "version": manifest.version if manifest else "",
                    "description": manifest.description if manifest else "",
                    "author": manifest.author if manifest else "",
                    "enabled": enabled,
                })
            await self._respond(client_id, payload, "admin.plugins", {"plugins": plugins})

        elif action == "get":
            name = payload.get("name", "")
            if not name or pm is None:
                await self._err(client_id, payload, "plugin name required")
                return
            manifest = pm.get_manifest(name)
            plugin_obj = pm.get_plugin(name)
            enabled = not getattr(plugin_obj, "_disabled", False) if plugin_obj else False
            await self._respond(client_id, payload, "admin.plugins", {
                "name": name,
                "version": manifest.version if manifest else "",
                "description": manifest.description if manifest else "",
                "author": manifest.author if manifest else "",
                "enabled": enabled,
            })

        elif action == "enable":
            name = payload.get("name", "")
            if not name or pm is None:
                await self._err(client_id, payload, "plugin name required")
                return
            await loop.run_in_executor(None, pm.enable, name)
            await self._respond(client_id, payload, "admin.plugins", {
                "action": "enable", "name": name, "success": True,
            })

        elif action == "disable":
            name = payload.get("name", "")
            if not name or pm is None:
                await self._err(client_id, payload, "plugin name required")
                return
            await loop.run_in_executor(None, pm.disable, name)
            await self._respond(client_id, payload, "admin.plugins", {
                "action": "disable", "name": name, "success": True,
            })

        else:
            await self._err(client_id, payload, f"unknown plugin action: {action}")

    async def _handle_skills(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.skills"):
            await self._err(client_id, payload, "permission denied")
            return

        sm = self._registry.get_optional("skill_manager")
        if sm is None:
            await self._respond(client_id, payload, "admin.skills", {"skills": []})
            return

        skills = []
        for skill in sm.all_skills():
            skills.append({
                "name": getattr(skill, "name", ""),
                "intent": getattr(skill, "intent", ""),
                "version": getattr(skill, "version", ""),
                "description": getattr(skill, "description", ""),
                "author": getattr(skill, "author", ""),
            })

        await self._respond(
            client_id, payload, "admin.skills",
            {"count": len(skills), "skills": skills},
        )

    async def _handle_memory(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.memory"):
            await self._err(client_id, payload, "permission denied")
            return

        action = payload.get("action", "stats")
        mem = self._registry.get_optional("memory")
        loop = asyncio.get_running_loop()

        if action == "stats":
            if mem is None:
                await self._respond(client_id, payload, "admin.memory", {"entries": 0})
                return
            recent = await loop.run_in_executor(None, mem.get_recent, 0)
            session_msgs = await loop.run_in_executor(None, mem.get_session_messages)
            await self._respond(client_id, payload, "admin.memory", {
                "entries": len(recent) if recent else 0,
                "session_messages": len(session_msgs) if session_msgs else 0,
            })

        elif action == "prune":
            ttl_days = payload.get("ttl_days", 30)
            if mem is None:
                await self._respond(client_id, payload, "admin.memory", {"removed": 0})
                return
            removed = await loop.run_in_executor(None, mem.prune_all, ttl_days)
            await self._respond(client_id, payload, "admin.memory", {
                "action": "prune", "ttl_days": ttl_days, "removed": removed,
            })

        elif action == "clear":
            if mem is None:
                await self._respond(client_id, payload, "admin.memory", {"success": True})
                return
            await loop.run_in_executor(None, mem.clear)
            await self._respond(client_id, payload, "admin.memory", {
                "action": "clear", "success": True,
            })

        else:
            await self._err(client_id, payload, f"unknown memory action: {action}")

    async def _handle_voice(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.voice"):
            await self._err(client_id, payload, "permission denied")
            return

        action = payload.get("action", "status")
        vm = self._registry.get_optional("voice_manager")
        loop = asyncio.get_running_loop()

        if action == "status":
            running = vm.is_running() if vm else False
            await self._respond(client_id, payload, "admin.voice", {"running": running})

        elif action == "start":
            if vm is None:
                await self._err(client_id, payload, "voice manager not available")
                return
            await loop.run_in_executor(None, vm.start)
            await self._respond(client_id, payload, "admin.voice", {
                "action": "start", "success": True,
            })

        elif action == "stop":
            if vm is None:
                await self._err(client_id, payload, "voice manager not available")
                return
            await loop.run_in_executor(None, vm.stop)
            await self._respond(client_id, payload, "admin.voice", {
                "action": "stop", "success": True,
            })

        else:
            await self._err(client_id, payload, f"unknown voice action: {action}")

    async def _handle_monitor(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.monitor"):
            await self._err(client_id, payload, "permission denied")
            return

        action = payload.get("action", "snapshot")
        mon = self._monitor

        if action in ("snapshot", "status"):
            if mon is None:
                await self._err(client_id, payload, "monitor not available")
                return
            try:
                snap = await mon.snapshot()
                interval = await mon.get_interval()
                running = mon.running
                thresholds = await mon.get_thresholds()
                await self._respond(client_id, payload, "admin.monitor", {
                    "running": running,
                    "interval_seconds": interval,
                    "thresholds": thresholds,
                    "snapshot": snap,
                })
            except Exception as exc:
                await self._err(client_id, payload, str(exc))

        elif action == "set_interval":
            interval = payload.get("interval", 5.0)
            if mon is None:
                await self._err(client_id, payload, "monitor not available")
                return
            await mon.set_interval(interval)
            await self._respond(client_id, payload, "admin.monitor", {
                "action": "set_interval", "interval": interval, "success": True,
            })

        elif action == "start":
            if mon is None:
                await self._err(client_id, payload, "monitor not available")
                return
            mon.start()
            await self._respond(client_id, payload, "admin.monitor", {
                "action": "start", "success": True,
            })

        elif action == "stop":
            if mon is None:
                await self._err(client_id, payload, "monitor not available")
                return
            await mon.stop()
            await self._respond(client_id, payload, "admin.monitor", {
                "action": "stop", "success": True,
            })

        else:
            await self._err(client_id, payload, f"unknown monitor action: {action}")

    async def _handle_config(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.config"):
            await self._err(client_id, payload, "permission denied")
            return

        from app.core.config import Config

        keys = payload.get("keys", None)
        loop = asyncio.get_running_loop()

        def _collect() -> dict[str, Any]:
            return {
                "app_name": Config.APP_NAME,
                "version": Config.VERSION,
                "data_dir": str(Config.DATA_DIR),
                "log_dir": str(Config.LOG_DIR),
                "log_level": Config.LOG_LEVEL,
                "memory_dir": str(Config.MEMORY_DIR),
                "cache_dir": str(Config.CACHE_DIR),
                "plugin_dir": str(Config.PLUGIN_DIR),
                "file_dir": str(Config.FILE_DIR),
                "max_file_size": Config.MAX_FILE_SIZE,
                "chunk_size": Config.CHUNK_SIZE,
                "default_brain": Config.DEFAULT_BRAIN,
                "reasoning_brain": Config.REASONING_BRAIN,
                "coding_brain": Config.CODING_BRAIN,
                "wake_word": Config.WAKE_WORD,
                "default_language": Config.DEFAULT_LANGUAGE,
                "ai_enabled": Config.AI is not None,
                "voice_enabled": Config.VOICE.enabled if Config.VOICE else False,
                "applications": dict(Config.APPLICATIONS),
            }

        all_config = await loop.run_in_executor(None, _collect)

        if keys:
            if isinstance(keys, str):
                keys = [keys]
            filtered = {k: all_config[k] for k in keys if k in all_config}
            await self._respond(client_id, payload, "admin.config", filtered)
        else:
            await self._respond(client_id, payload, "admin.config", all_config)

    # ------------------------------------------------------------------
    # P12-10: WebSocket Observability
    # ------------------------------------------------------------------

    async def _handle_ws_metrics(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if self._ws_metrics is None:
            await self._err(client_id, payload, "metrics service not available")
            return
        try:
            snap = await self._ws_metrics.snapshot()
            await self._respond(client_id, payload, "admin.ws.metrics", snap)
        except Exception as exc:
            await self._err(client_id, payload, str(exc))

    async def _handle_ws_health(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if self._ws_health is None:
            await self._err(client_id, payload, "health monitor not available")
            return
        try:
            report = await self._ws_health.evaluate()
            await self._respond(client_id, payload, "admin.ws.health", report)
        except Exception as exc:
            await self._err(client_id, payload, str(exc))

    async def _handle_ws_diagnostics(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if self._ws_diagnostics is None:
            await self._err(client_id, payload, "diagnostics not available")
            return
        try:
            report = await self._ws_diagnostics.generate()
            await self._respond(client_id, payload, "admin.ws.diagnostics", report)
        except Exception as exc:
            await self._err(client_id, payload, str(exc))

    async def _handle_ws_reset_metrics(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.ws.reset_metrics"):
            await self._err(client_id, payload, "permission denied")
            return
        if self._ws_metrics is None:
            await self._err(client_id, payload, "metrics service not available")
            return
        try:
            await self._ws_metrics.reset()
            await self._respond(client_id, payload, "admin.ws.reset_metrics", {"success": True})
        except Exception as exc:
            await self._err(client_id, payload, str(exc))

    async def _handle_ws_maintenance(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.ws.maintenance"):
            await self._err(client_id, payload, "permission denied")
            return
        if self._ws_maintenance is None:
            await self._err(client_id, payload, "maintenance service not available")
            return
        try:
            action = payload.get("action", "run_all")
            operations = {
                "clear_retry_queues": self._ws_maintenance.clear_retry_queues,
                "clear_offline_queues": self._ws_maintenance.clear_offline_queues,
                "clear_inactive_sessions": self._ws_maintenance.clear_inactive_sessions,
                "prune_expired_tokens": self._ws_maintenance.prune_expired_tokens,
                "prune_expired_acks": self._ws_maintenance.prune_expired_acks,
                "reset_metrics": self._ws_maintenance.reset_metrics,
                "run_all": self._ws_maintenance.run_all,
            }
            handler = operations.get(action)
            if handler is None:
                await self._err(client_id, payload, f"unknown maintenance action: {action}")
                return
            client_filter = payload.get("client_id")
            if action in ("clear_retry_queues", "clear_offline_queues") and client_filter:
                result = await handler(client_id=client_filter)
            else:
                result = await handler()
            result["action"] = action
            await self._respond(client_id, payload, "admin.ws.maintenance", result)
        except Exception as exc:
            await self._err(client_id, payload, str(exc))

    async def _handle_ws_runtime_config(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not await self._check_permission(client_id, "admin.ws.runtime_config"):
            await self._err(client_id, payload, "permission denied")
            return
        if self._ws_runtime_config is None:
            await self._err(client_id, payload, "runtime config not available")
            return
        try:
            action = payload.get("action", "get")
            if action == "get":
                key = payload.get("key")
                if key:
                    result = {"key": key, "value": self._ws_runtime_config.get(key)}
                else:
                    result = {"config": self._ws_runtime_config.get_all()}
            elif action == "set":
                key = payload.get("key")
                value = payload.get("value")
                if not key:
                    await self._err(client_id, payload, "key is required for set")
                    return
                ok = self._ws_runtime_config.set(key, value)
                result = {"key": key, "set": ok}
            elif action == "reset":
                key = payload.get("key")
                self._ws_runtime_config.reset(key=key)
                result = {"reset": True}
            else:
                await self._err(client_id, payload, f"unknown action: {action}")
                return
            result["action"] = action
            await self._respond(client_id, payload, "admin.ws.runtime_config", result)
        except Exception as exc:
            await self._err(client_id, payload, str(exc))

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    async def _respond(
        self,
        client_id: str,
        request_payload: dict[str, Any],
        response_type: str,
        data: dict[str, Any],
    ) -> None:
        if not await self._ws.is_connected(client_id):
            return

        payload = {
            "request_id": request_payload.get("request_id", ""),
            "correlation_id": request_payload.get("correlation_id", ""),
            "success": True,
            "duration_ms": 0,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        }
        payload.update(data)

        await self._ws.send(
            client_id,
            ServerMessage(type=_ws_type(response_type), payload=payload),
        )

    async def _err(
        self,
        client_id: str,
        request_payload: dict[str, Any],
        error: str,
    ) -> None:
        if not await self._ws.is_connected(client_id):
            return

        payload = {
            "request_id": request_payload.get("request_id", ""),
            "correlation_id": request_payload.get("correlation_id", ""),
            "success": False,
            "duration_ms": 0,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "error": error,
        }

        await self._ws.send(
            client_id,
            ServerMessage(type=WSMessageType.ADMIN_ERROR, payload=payload),
        )


def _ws_type(response_type: str) -> WSMessageType:
    mapping: dict[str, WSMessageType] = {
        "admin.pong": WSMessageType.ADMIN_PONG,
        "admin.status": WSMessageType.ADMIN_STATUS_RESPONSE,
        "admin.info": WSMessageType.ADMIN_INFO_RESPONSE,
        "admin.shutdown": WSMessageType.ADMIN_SHUTDOWN_RESPONSE,
        "admin.restart": WSMessageType.ADMIN_RESTART_RESPONSE,
        "admin.clients": WSMessageType.ADMIN_CLIENTS_RESPONSE,
        "admin.plugins": WSMessageType.ADMIN_PLUGINS_RESPONSE,
        "admin.skills": WSMessageType.ADMIN_SKILLS_RESPONSE,
        "admin.memory": WSMessageType.ADMIN_MEMORY_RESPONSE,
        "admin.voice": WSMessageType.ADMIN_VOICE_RESPONSE,
        "admin.monitor": WSMessageType.ADMIN_MONITOR_RESPONSE,
        "admin.config": WSMessageType.ADMIN_CONFIG_RESPONSE,
        "admin.ws.metrics": WSMessageType.ADMIN_WS_METRICS_RESPONSE,
        "admin.ws.health": WSMessageType.ADMIN_WS_HEALTH_RESPONSE,
        "admin.ws.diagnostics": WSMessageType.ADMIN_WS_DIAGNOSTICS_RESPONSE,
        "admin.ws.reset_metrics": WSMessageType.ADMIN_WS_RESET_METRICS_RESPONSE,
        "admin.ws.maintenance": WSMessageType.ADMIN_WS_MAINTENANCE_RESPONSE,
        "admin.ws.runtime_config": WSMessageType.ADMIN_WS_RUNTIME_CONFIG_RESPONSE,
    }
    return mapping.get(response_type, WSMessageType.ADMIN_ERROR)
