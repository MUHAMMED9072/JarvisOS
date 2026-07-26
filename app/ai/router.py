from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import TYPE_CHECKING, Generator

from app.core.config import Config
from app.core.logger import JarvisLogger

if TYPE_CHECKING:
    from .structured import StructuredSchema
    from .tools import ToolDefinition

from .providers.base import (
    AIProvider,
    AIProviderError,
    AIResponse,
    AIStreamChunk,
    AIStreamResponse,
    AllProvidersFailedError,
    ProviderCapability,
)
from .routing import ProviderStatus, RoutingConfig, RoutingStrategy


_IGNORED_MODULES = frozenset({"base", "__init__"})


class AIRouter:

    _metrics = None  # class-level default for instances that bypass __init__

    def __init__(
        self,
        routing_config: RoutingConfig | None = None,
        metrics_collector=None,
    ):

        self.providers: dict[str, AIProvider] = self._discover_providers()
        self.routing_config: RoutingConfig = (
            routing_config if routing_config is not None
            else Config.AI.build_routing_config()
        )
        self._metrics = metrics_collector
        if self._metrics:
            self._wire_retry_tracker()

    def _wire_retry_tracker(self) -> None:
        """Inject retry tracking callback into every registered provider."""
        if self._metrics is None:
            return
        for provider in self.providers.values():
            try:
                provider._retry_tracker = self._metrics.record_retry  # type: ignore[attr-defined]
            except Exception:
                pass

    def ask(self, provider: str, prompt: str, tools: list[ToolDefinition] | None = None, schema: StructuredSchema | None = None) -> AIResponse:

        if provider not in self.providers:
            if self._metrics:
                self._metrics.record_provider_request(provider, False)
            raise ValueError(f"Unknown provider: {provider}")
        p = self.providers[provider]
        try:
            if tools is not None and schema is not None:
                result = p.generate(prompt, tools=tools, schema=schema)
            elif tools is not None:
                result = p.generate(prompt, tools=tools)
            elif schema is not None:
                result = p.generate(prompt, schema=schema)
            else:
                result = p.generate(prompt)
        except Exception:
            if self._metrics:
                self._metrics.record_provider_request(provider, False)
            raise
        if self._metrics:
            prompt_tokens = 0
            completion_tokens = 0
            if hasattr(result, 'metadata'):
                meta = result.metadata if isinstance(result.metadata, dict) else {}
                prompt_tokens = meta.get('prompt_tokens', 0) or 0
                completion_tokens = meta.get('completion_tokens', 0) or 0
            self._metrics.record_provider_request(
                provider, True, result.latency_ms if hasattr(result, 'latency_ms') else 0,
                prompt_tokens, completion_tokens,
            )
        return result

    def ask_stream(self, provider: str, prompt: str) -> AIStreamResponse:
        """Stream a response from *provider*.

        If the provider supports native streaming (``generate_stream``)
        the stream is used directly.  Otherwise the synchronous
        ``generate`` result is wrapped in a single-chunk stream.
        """
        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}")
        p = self.providers[provider]
        stream_gen = getattr(p, "generate_stream", None)
        if stream_gen is not None:
            model = getattr(p, "_model", "")
            return AIStreamResponse(provider, model, stream_gen(prompt))
        return self._sync_response_as_stream(provider, p, p.generate(prompt))

    def ask_routed_stream(
        self,
        prompt: str,
        required_capabilities: frozenset[ProviderCapability] | None = None,
    ) -> AIStreamResponse:
        """Stream a response using the configured routing strategy.

        Follows the same routing policies as ``ask_routed`` but uses
        streaming dispatch.
        """
        order = self._resolve_provider_order()
        if not order:
            raise ValueError(
                "No providers are configured for routing"
        )

        failures: dict[str, Exception] = {}

        for name in order:
            if name not in self.providers:
                failures[name] = ValueError(
                    f"Provider {name!r} is not registered"
                )
                continue

            status = self._check_provider_status(name)
            if status is not ProviderStatus.AVAILABLE:
                continue

            if not self.supports_all(name, required_capabilities):
                failures[name] = AIProviderError(
                    f"Provider {name!r} does not support required "
                    f"capabilities"
                )
                continue

            p = self.providers[name]
            stream_gen = getattr(p, "generate_stream", None)
            model = getattr(p, "_model", "")

            try:
                if stream_gen is not None:
                    return AIStreamResponse(name, model, stream_gen(prompt))
                return self._sync_response_as_stream(
                    name, p, p.generate(prompt)
                )
            except AIProviderError as exc:
                failures[name] = exc
                continue

        raise AllProvidersFailedError(failures)

    @staticmethod
    def _sync_response_as_stream(
        provider_name: str, provider: AIProvider, result: str | AIResponse,
    ) -> AIStreamResponse:
        """Wrap a synchronous ``generate`` result as a single-chunk stream."""
        metadata = result.metadata if isinstance(result, AIResponse) else {}
        model = getattr(provider, "_model", "")

        def _gen() -> Generator[AIStreamChunk, None, None]:  # noqa: F811
            yield AIStreamChunk(
                content=str(result),
                finish_reason="stop",
                usage=metadata if metadata else None,
            )

        return AIStreamResponse(provider_name, model, _gen())

    def ask_routed(
        self,
        prompt: str,
        required_capabilities: frozenset[ProviderCapability] | None = None,
        tools: list[ToolDefinition] | None = None,
        schema: StructuredSchema | None = None,
    ) -> AIResponse:
        """Dispatch *prompt* using the configured routing strategy.

        Attempts providers in the order determined by
        ``routing_config.strategy``, skipping unavailable/disabled
        providers and providers that do not satisfy
        *required_capabilities* (when specified).  If a provider fails,
        the next available compatible provider is tried automatically.

        Returns the first successful ``AIResponse``.

        Raises
        ------
        AllProvidersFailedError
            When every provider in the routing chain has failed.
        ValueError
            When no providers are configured at all.
        """
        order = self._resolve_provider_order()
        if not order:
            if self._metrics:
                self._metrics.routing.record(False)
            raise ValueError(
                "No providers are configured for routing"
            )

        failures: dict[str, Exception] = {}
        provider_tried = False

        for name in order:
            if name not in self.providers:
                failures[name] = ValueError(
                    f"Provider {name!r} is not registered"
                )
                continue

            status = self._check_provider_status(name)
            if status is not ProviderStatus.AVAILABLE:
                continue

            if not self.supports_all(name, required_capabilities):
                failures[name] = AIProviderError(
                    f"Provider {name!r} does not support required "
                    f"capabilities"
                )
                continue

            if tools and not self.supports_capability(name, ProviderCapability.FUNCTION_CALLING):
                failures[name] = AIProviderError(
                    f"Provider {name!r} does not support tool calling"
                )
                continue

            if schema and not self.supports_capability(name, ProviderCapability.JSON_OUTPUT):
                failures[name] = AIProviderError(
                    f"Provider {name!r} does not support structured output"
                )
                continue

            provider_tried = True
            if self._metrics:
                self._metrics.routing.record(True)

            try:
                result = self.ask(name, prompt, tools=tools, schema=schema)
                if required_capabilities:
                    result.metadata.setdefault("capabilities", set(required_capabilities))
                    result.metadata.setdefault("routing_strategy", self.routing_config.strategy.name)
                    result.metadata.setdefault("fallback_history", list(failures.keys()))
                if self._metrics and failures:
                    for failed_name in failures:
                        self._metrics.record_provider_retry(failed_name, 1)
                return result
            except AIProviderError as exc:
                if self._metrics:
                    self._metrics.record_provider_retry(name, 1)
                failures[name] = exc
                continue

        if self._metrics and provider_tried:
            self._metrics.routing.record(False)

        raise AllProvidersFailedError(failures)

    def register(self, provider: AIProvider) -> None:

        if not isinstance(provider, AIProvider):
            JarvisLogger.error(
                f"Provider registration failed: object of type "
                f"'{type(provider).__name__}' does not implement AIProvider"
            )
            raise TypeError(
                f"Object of type '{type(provider).__name__}' does not "
                f"implement AIProvider"
            )

        name = getattr(provider, "provider_name", None)
        if not isinstance(name, str) or not name:
            JarvisLogger.error(
                f"Provider registration failed: provider of type "
                f"'{type(provider).__name__}' has no valid 'provider_name'"
            )
            raise ValueError(
                f"Provider of type '{type(provider).__name__}' has no "
                f"valid 'provider_name'"
            )

        if name in self.providers:
            JarvisLogger.error(
                f"Provider registration failed: a provider named "
                f"'{name}' is already registered"
            )
            raise ValueError(
                f"Provider '{name}' is already registered"
            )

        self.providers[name] = provider
        JarvisLogger.info(
            f"Provider registration succeeded: '{name}' "
            f"({type(provider).__name__})"
        )

    def unregister(self, name: str) -> bool:

        if not isinstance(name, str) or not name:
            JarvisLogger.error(
                f"Provider unregistration failed: invalid name supplied"
            )
            return False

        if name not in self.providers:
            JarvisLogger.error(
                f"Provider unregistration failed: provider '{name}' is "
                f"not registered"
            )
            return False

        try:
            removed = self.providers.pop(name)
        except Exception as exc:
            JarvisLogger.error(
                f"Provider unregistration failed: removing '{name}' raised "
                f"{type(exc).__name__}: {exc}"
            )
            return False

        JarvisLogger.info(
            f"Provider unregistration succeeded: '{name}' "
            f"({type(removed).__name__})"
        )
        return True

    def reload(self, name: str) -> bool:

        if not isinstance(name, str) or not name:
            JarvisLogger.error(
                f"Provider reload failed: invalid name supplied"
            )
            return False

        if name not in self.providers:
            JarvisLogger.error(
                f"Provider reload failed: provider '{name}' is not registered"
            )
            return False

        old_provider = self.providers[name]

        module = inspect.getmodule(old_provider)
        if module is None:
            JarvisLogger.error(
                f"Provider reload failed: cannot resolve module for "
                f"provider '{name}'"
            )
            return False

        module_name = module.__name__

        try:
            reloaded = importlib.reload(module)
        except Exception as exc:
            JarvisLogger.error(
                f"Provider reload failed: importlib.reload('{module_name}') "
                f"raised {type(exc).__name__}: {exc}"
            )
            return False

        new_instance: AIProvider | None = None

        for _, obj in inspect.getmembers(reloaded, inspect.isclass):
            if not isinstance(obj, type):
                continue
            if obj.__module__ != module_name:
                continue
            if not issubclass(obj, AIProvider):
                continue
            if obj is AIProvider:
                continue

            candidate_name = getattr(obj, "provider_name", None)
            if candidate_name != name:
                continue

            try:
                candidate = obj()
            except Exception as exc:
                JarvisLogger.error(
                    f"Provider reload failed: instantiating "
                    f"'{obj.__name__}' from module '{module_name}' raised "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            if not isinstance(candidate, AIProvider):
                continue

            new_instance = candidate
            break

        if new_instance is None:
            JarvisLogger.error(
                f"Provider reload failed: no concrete AIProvider matching "
                f"name '{name}' was found in module '{module_name}' after "
                f"reload"
            )
            return False

        if not self.unregister(name):
            JarvisLogger.error(
                f"Provider reload failed: could not unregister existing "
                f"provider '{name}' before re-registration"
            )
            return False

        try:
            self.register(new_instance)
        except Exception as exc:
            # Roll back to the original provider.
            self.providers[name] = old_provider

            JarvisLogger.error(
                f"Provider reload failed: re-registering provider '{name}' "
                f"raised {type(exc).__name__}: {exc}. "
                f"Original provider has been restored."
            )
            return False

        JarvisLogger.info(
            f"Provider reload succeeded: '{name}' replaced "
            f"({type(old_provider).__name__} -> {type(new_instance).__name__})"
        )
        return True

    # ------------------------------------------------------------------
    # Routing helpers
    # ------------------------------------------------------------------

    def provider_status(self, name: str) -> ProviderStatus:
        """Return the current ``ProviderStatus`` for *name*."""
        if name not in self.providers:
            return ProviderStatus.UNAVAILABLE

        config = self.routing_config
        if name in config.disabled_providers:
            return ProviderStatus.DISABLED

        provider = self.providers[name]
        check = getattr(provider, "check_availability", None)
        if check is not None and not check():
            return ProviderStatus.NO_CREDENTIALS

        return ProviderStatus.AVAILABLE

    @property
    def available_providers(self) -> list[str]:
        """Return names of every registered provider that is currently available."""
        return [
            name
            for name in self.providers
            if self.provider_status(name) is ProviderStatus.AVAILABLE
        ]

    def _check_provider_status(self, name: str) -> ProviderStatus:
        """Internal availability check that also considers
        ``enabled_providers`` from config."""
        config = self.routing_config
        if (
            config.enabled_providers is not None
            and name not in config.enabled_providers
        ):
            return ProviderStatus.DISABLED
        return self.provider_status(name)

    # ------------------------------------------------------------------
    # Capability queries
    # ------------------------------------------------------------------

    def provider_capabilities(
        self, name: str,
    ) -> frozenset[ProviderCapability]:
        """Return the capabilities declared by *name*.

        Returns an empty frozenset when the provider does not declare
        any capabilities or is not registered.
        """
        provider = self.providers.get(name)
        if provider is None:
            return frozenset()
        caps = getattr(provider, "capabilities", None)
        if not isinstance(caps, frozenset):
            return frozenset()
        return caps

    def providers_with_capability(
        self, capability: ProviderCapability,
    ) -> list[str]:
        """Return every registered provider that supports *capability*."""
        return [
            name
            for name in self.providers
            if capability in self.provider_capabilities(name)
        ]

    def supports_capability(
        self, name: str, capability: ProviderCapability | None,
    ) -> bool:
        """Return True when *name* supports *capability*.

        Returns True when *capability* is None (no requirement).
        """
        if capability is None:
            return True
        return capability in self.provider_capabilities(name)

    def supports_all(
        self,
        name: str,
        capabilities: frozenset[ProviderCapability] | None,
    ) -> bool:
        """Return True when *name* supports all *capabilities*.

        Returns True when *capabilities* is None or empty (no
        requirement).
        """
        if not capabilities:
            return True
        provider_caps = self.provider_capabilities(name)
        return capabilities.issubset(provider_caps)

    def _resolve_provider_order(self) -> list[str]:
        """Return the ordered list of providers to try for routing."""
        config = self.routing_config
        base_order = list(config.providers)

        if config.strategy is RoutingStrategy.PREFERRED:
            return base_order
        if config.strategy is RoutingStrategy.FAILOVER:
            return base_order
        if config.strategy is RoutingStrategy.OFFLINE_FIRST:
            offline = config.offline_provider
            rest = [p for p in base_order if p != offline]
            return [offline] + rest if offline in base_order else rest
        if config.strategy is RoutingStrategy.ONLINE_FIRST:
            offline = config.offline_provider
            rest = [p for p in base_order if p != offline]
            return rest + [offline] if offline in base_order else rest
        return base_order

    @staticmethod
    def _discover_providers() -> dict[str, AIProvider]:

        from . import providers as providers_package

        discovered: dict[str, AIProvider] = {}

        for module_info in pkgutil.iter_modules(providers_package.__path__):

            module_name = module_info.name

            if module_name in _IGNORED_MODULES:
                continue

            full_name = f"{providers_package.__name__}.{module_name}"

            try:
                module = importlib.import_module(full_name)
            except Exception as exc:
                JarvisLogger.error(
                    f"Provider discovery failed: importlib.import_module("
                    f"'{full_name}') raised {type(exc).__name__}: {exc}"
                )
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):

                if not isinstance(obj, type):
                    continue
                if obj.__module__ != full_name:
                    continue
                if not issubclass(obj, AIProvider):
                    continue
                if obj is AIProvider:
                    continue

                name = getattr(obj, "provider_name", None)
                if not isinstance(name, str) or not name:
                    continue

                if name in discovered:
                    JarvisLogger.error(
                        f"Duplicate AI provider '{name}' found in module "
                        f"'{full_name}'. Skipping."
                    )
                    continue

                try:
                    instance = obj()
                except Exception as exc:
                    JarvisLogger.error(
                        f"Provider discovery failed: instantiating "
                        f"'{obj.__name__}' from module '{full_name}' raised "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue

                if isinstance(instance, AIProvider):
                    discovered[name] = instance

        return discovered
