# app/ai/router.py
from __future__ import annotations

import importlib
import inspect
import pkgutil

from app.core.logger import JarvisLogger

from .providers.base import AIProvider, AIResponse


_IGNORED_MODULES = frozenset({"base", "__init__"})


class AIRouter:

    def __init__(self):

        self.providers: dict[str, AIProvider] = self._discover_providers()

    def ask(self, provider: str, prompt: str) -> AIResponse:

        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}")
        return self.providers[provider].generate(prompt)

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
