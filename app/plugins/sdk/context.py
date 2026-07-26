from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from app.core.logger import JarvisLogger


class PluginConfig:
    def __init__(self, plugin_name: str) -> None:
        self._plugin_name = plugin_name
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class PluginContext:
    def __init__(self, registry: Any, plugin_name: str = "") -> None:
        self._registry = registry
        self._plugin_name = plugin_name
        self._config = PluginConfig(plugin_name)
        self._logger = JarvisLogger
        self._manager: Any = None
        self._registered_services: list[str] = []
        self._subscriptions: list[tuple[str, Callable[..., Any]]] = []
        self._skill_intents: list[str] = []

    def _set_manager(self, manager: Any) -> None:
        self._manager = manager

    def register_service(self, name: str, service: Any) -> None:
        """Register a plugin-private service (namespaced)."""
        full_name = f"plugin.{self._plugin_name}.{name}"
        if self._registry is not None:
            try:
                self._registry.register(full_name, service)
            except (ValueError, Exception):
                return
        self._track_services([full_name])

    def export_service(self, name: str, service: Any) -> None:
        """Export a shared service to the global registry."""
        if self._registry is not None:
            try:
                self._registry.register(name, service)
            except (ValueError, Exception):
                return
        self._track_services([name])

    def list_services(self) -> list[str]:
        if self._registry is not None and hasattr(self._registry, 'list_services'):
            return self._registry.list_services()
        return list(self._registered_services)

    def _track_services(self, names: list[str]) -> None:
        self._registered_services.extend(names)
        if self._manager is not None:
            mgr_method = getattr(self._manager, 'register_plugin_service', None)
            if mgr_method:
                for n in names:
                    mgr_method(self._plugin_name, n)

    def subscribe(self, event: str, callback: Callable[..., Any]) -> None:
        bus = self._event_bus_ref()
        if bus is not None:
            bus.subscribe(event, callback)
        self._subscriptions.append((event, callback))

    def publish(self, event: str, *args: Any, **kwargs: Any) -> None:
        bus = self._event_bus_ref()
        if bus is not None:
            bus.publish(event, *args, **kwargs)

    def unsubscribe(self, event: str, callback: Callable[..., Any]) -> None:
        bus = self._event_bus_ref()
        if bus is not None:
            bus.unsubscribe(event, callback)
        self._subscriptions = [
            (e, c) for e, c in self._subscriptions
            if not (e == event and c is callback)
        ]

    def _cleanup_subscriptions(self) -> None:
        bus = self._event_bus_ref()
        if bus is not None:
            for event, callback in self._subscriptions:
                try:
                    bus.unsubscribe(event, callback)
                except Exception:
                    pass
        self._subscriptions.clear()

    def _event_bus_ref(self) -> Any:
        if self._registry is None:
            return None
        try:
            return self._registry.get("event_bus")
        except (KeyError, Exception):
            return None

    @property
    def registry(self) -> Any:
        return self._registry

    @property
    def config(self) -> PluginConfig:
        return self._config

    @property
    def event_bus(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get("event_bus")

    @property
    def ai_manager(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional("ai_manager")

    @property
    def memory(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional("memory")

    @property
    def cortex(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional("cortex")

    @property
    def dispatcher(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional("dispatcher")

    @property
    def skill_manager(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional("skill_manager")

    # ------------------------------------------------------------------
    # Additional service properties
    # ------------------------------------------------------------------

    @property
    def template_registry(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional("template_registry")

    @property
    def tool_registry(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional("tool_registry")

    @property
    def memory_aware_ai(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional("memory_aware_ai")

    @property
    def ai_diagnostics(self) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional("ai_diagnostics")

    def get_service(self, name: str) -> Any:
        if self._registry is None:
            return None
        return self._registry.get_optional(name)

    # ------------------------------------------------------------------
    # AI Chat
    # ------------------------------------------------------------------

    def ai_ask(
        self,
        prompt: str = "",
        *,
        provider: str | None = None,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        tools: Any = None,
        schema: Any = None,
        required_capabilities: Any = None,
    ) -> Any:
        ai = self.ai_manager
        if ai is None:
            return None
        try:
            return ai.ask(
                provider, prompt,
                prompt_template=prompt_template,
                template_variables=template_variables,
                conversation_id=conversation_id,
                required_capabilities=required_capabilities,
                tools=tools,
                schema=schema,
            )
        except Exception:
            self.log_error("AI ask failed")
            return None

    def ai_ask_stream(
        self,
        provider: str,
        prompt: str = "",
        *,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
    ) -> Any:
        ai = self.ai_manager
        if ai is None:
            return None
        try:
            return ai.ask_stream(
                provider, prompt,
                prompt_template=prompt_template,
                template_variables=template_variables,
                conversation_id=conversation_id,
            )
        except Exception:
            self.log_error("AI streaming failed")
            return None

    # ------------------------------------------------------------------
    # Conversation Management
    # ------------------------------------------------------------------

    def create_conversation(
        self,
        *,
        provider: str = "",
        model: str = "",
        system_prompt: str = "",
        max_messages: int | None = None,
        metadata: dict | None = None,
    ) -> Any:
        ai = self.ai_manager
        if ai is None:
            return None
        return ai.create_conversation(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            max_messages=max_messages,
            metadata=metadata,
        )

    def get_conversation(self, conversation_id: str) -> Any:
        ai = self.ai_manager
        if ai is None:
            return None
        return ai.conversation_manager.get(conversation_id)

    def delete_conversation(self, conversation_id: str) -> bool:
        ai = self.ai_manager
        if ai is None:
            return False
        return ai.conversation_manager.delete(conversation_id)

    # ------------------------------------------------------------------
    # Planning & Reasoning
    # ------------------------------------------------------------------

    def ai_plan(
        self,
        objective: str,
        *,
        provider: str | None = None,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        planning_prompt: str | None = None,
        required_capabilities: Any = None,
    ) -> Any:
        ai = self.ai_manager
        if ai is None:
            return None
        try:
            return ai.plan(
                objective,
                provider=provider,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
                planning_prompt=planning_prompt,
                required_capabilities=required_capabilities,
            )
        except Exception:
            self.log_error("AI planning failed")
            return None

    def ai_reason(
        self,
        objective: str,
        *,
        provider: str | None = None,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        reasoning_prompt: str | None = None,
        required_capabilities: Any = None,
    ) -> Any:
        ai = self.ai_manager
        if ai is None:
            return None
        try:
            return ai.reason(
                objective,
                provider=provider,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
                reasoning_prompt=reasoning_prompt,
                required_capabilities=required_capabilities,
            )
        except Exception:
            self.log_error("AI reasoning failed")
            return None

    # ------------------------------------------------------------------
    # Structured Output
    # ------------------------------------------------------------------

    def create_structured_schema(
        self,
        name: str,
        schema: dict,
        metadata: dict | None = None,
    ) -> Any:
        svc = self._registry.get_optional("structured_service") if self._registry else None
        if svc is None:
            return None
        try:
            return svc.create_schema(name, schema, metadata=metadata)
        except Exception:
            self.log_error("Failed to create structured schema")
            return None

    def parse_structured(self, text: str, schema: Any) -> Any:
        svc = self._registry.get_optional("structured_service") if self._registry else None
        if svc is None:
            return None
        try:
            return svc.parse(text, schema)
        except Exception:
            self.log_error("Failed to parse structured output")
            return None

    # ------------------------------------------------------------------
    # Tool Registration
    # ------------------------------------------------------------------

    def register_tool(self, tool: Any) -> None:
        registry = self.tool_registry
        if registry is None:
            return
        try:
            registry.register(tool)
        except Exception:
            self.log_error("Failed to register tool")

    def unregister_tool(self, name: str) -> bool:
        registry = self.tool_registry
        if registry is None:
            return False
        return registry.unregister(name)

    def list_tools(self) -> list:
        registry = self.tool_registry
        if registry is None:
            return []
        return registry.list()

    # ------------------------------------------------------------------
    # Prompt Templates
    # ------------------------------------------------------------------

    def register_template(self, template: Any) -> None:
        registry = self.template_registry
        if registry is None:
            return
        try:
            registry.register(template)
        except Exception:
            self.log_error("Failed to register template")

    def unregister_template(self, name: str) -> bool:
        registry = self.template_registry
        if registry is None:
            return False
        return registry.unregister(name)

    def get_template(self, name: str) -> Any:
        registry = self.template_registry
        if registry is None:
            return None
        return registry.get(name)

    # ------------------------------------------------------------------
    # Skill Registration
    # ------------------------------------------------------------------

    def register_skill(self, skill: Any) -> None:
        mgr = self.skill_manager
        if mgr is None:
            self.log_error("SkillManager not available")
            return
        try:
            if not getattr(skill, 'intent', None):
                self.log_error(f"Skill {type(skill).__name__} has no intent")
                return
            if hasattr(skill, 'setup') and self._registry is not None:
                skill.setup(self._registry)
            mgr.register(skill)
            self._skill_intents.append(skill.intent)
            self.log_info(f"Skill registered: {skill.intent}")
        except Exception:
            self.log_error(f"Failed to register skill {getattr(skill, 'name', '')}")

    def unregister_skill(self, intent: str) -> bool:
        mgr = self.skill_manager
        if mgr is None:
            return False
        try:
            result = mgr.unregister(intent)
            if result:
                self._skill_intents = [
                    i for i in self._skill_intents if i != intent
                ]
            return result
        except Exception:
            self.log_error(f"Failed to unregister skill {intent}")
            return False

    def _cleanup_skills(self) -> None:
        mgr = self.skill_manager
        if mgr is not None:
            for intent in list(self._skill_intents):
                try:
                    mgr.unregister(intent)
                except Exception:
                    pass
        self._skill_intents.clear()

    def log_info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(f"[Plugin] {message}", *args, **kwargs)

    def log_error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(f"[Plugin] {message}", *args, **kwargs)

    def log_warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(f"[Plugin] {message}", *args, **kwargs)

    def log_debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(f"[Plugin] {message}", *args, **kwargs)
