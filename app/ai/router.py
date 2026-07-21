# app/ai/router.py
from __future__ import annotations

import importlib
import inspect
import pkgutil

from app.core.logger import JarvisLogger

from .providers.base import AIProvider


_IGNORED_MODULES = frozenset({"base", "__init__"})


class AIRouter:

    def __init__(self):

        self.providers: dict[str, AIProvider] = self._discover_providers()

    def ask(self, provider: str, prompt: str) -> str:

        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}")
        return self.providers[provider].generate(prompt)

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
