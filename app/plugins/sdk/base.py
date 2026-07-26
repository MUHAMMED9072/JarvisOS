from __future__ import annotations

from abc import ABC
from collections.abc import Callable
from typing import Any

from app.plugins.sdk.context import PluginContext
from app.plugins.sdk.models import PluginManifest


class Plugin(ABC):
    name: str = ""
    version: str = "1.0.0"
    manifest: PluginManifest | None = None

    def __init__(self) -> None:
        self.context: PluginContext | None = None
        self._enabled: bool = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _inject(self, context: PluginContext) -> None:
        self.context = context

    def on_load(self) -> None:
        pass

    def on_enable(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    def on_uninstall(self) -> None:
        pass

    def log_info(self, message: str, *args: Any, **kwargs: Any) -> None:
        if self.context:
            self.context.log_info(message, *args, **kwargs)

    def log_error(self, message: str, *args: Any, **kwargs: Any) -> None:
        if self.context:
            self.context.log_error(message, *args, **kwargs)

    def log_warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        if self.context:
            self.context.log_warning(message, *args, **kwargs)

    def log_debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        if self.context:
            self.context.log_debug(message, *args, **kwargs)

    def register_service(self, name: str, service: Any) -> None:
        if self.context:
            self.context.register_service(name, service)

    def export_service(self, name: str, service: Any) -> None:
        if self.context:
            self.context.export_service(name, service)

    def subscribe(self, event: str, callback: Callable[..., Any]) -> None:
        if self.context:
            self.context.subscribe(event, callback)

    def publish(self, event: str, *args: Any, **kwargs: Any) -> None:
        if self.context:
            self.context.publish(event, *args, **kwargs)

    def unsubscribe(self, event: str, callback: Callable[..., Any]) -> None:
        if self.context:
            self.context.unsubscribe(event, callback)

    # ------------------------------------------------------------------
    # AI convenience methods
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
        if self.context:
            return self.context.ai_ask(
                prompt, provider=provider,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
                tools=tools, schema=schema,
                required_capabilities=required_capabilities,
            )
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
        if self.context:
            return self.context.ai_ask_stream(
                provider, prompt,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )
        return None

    def create_conversation(
        self,
        *,
        provider: str = "",
        model: str = "",
        system_prompt: str = "",
        max_messages: int | None = None,
        metadata: dict | None = None,
    ) -> Any:
        if self.context:
            return self.context.create_conversation(
                provider=provider, model=model,
                system_prompt=system_prompt,
                max_messages=max_messages,
                metadata=metadata,
            )
        return None

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
        if self.context:
            return self.context.ai_plan(
                objective, provider=provider,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
                planning_prompt=planning_prompt,
                required_capabilities=required_capabilities,
            )
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
        if self.context:
            return self.context.ai_reason(
                objective, provider=provider,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
                reasoning_prompt=reasoning_prompt,
                required_capabilities=required_capabilities,
            )
        return None

    def register_tool(self, tool: Any) -> None:
        if self.context:
            self.context.register_tool(tool)

    def register_template(self, template: Any) -> None:
        if self.context:
            self.context.register_template(template)

    # ------------------------------------------------------------------
    # Skill convenience methods
    # ------------------------------------------------------------------

    def register_skill(self, skill: Any) -> None:
        if self.context:
            self.context.register_skill(skill)

    def unregister_skill(self, intent: str) -> bool:
        if self.context:
            return self.context.unregister_skill(intent)
        return False
