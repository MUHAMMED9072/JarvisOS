# app/skills/loader.py
import importlib
import inspect
import pkgutil

import app.skills

from app.core.logger import JarvisLogger
from app.skills.base import Skill


class SkillLoader:

    def load(self, manager, registry=None):

        package = app.skills

        for _, module_name, _ in pkgutil.walk_packages(
            package.__path__,
            package.__name__ + "."
        ):

            # Ignore framework modules
            if module_name.endswith((
                ".base",
                ".manager",
                ".loader",
                ".result",
            )):
                continue

            module = importlib.import_module(module_name)

            for _, obj in inspect.getmembers(module, inspect.isclass):

                if (
                    issubclass(obj, Skill)
                    and obj is not Skill
                ):

                    skill = obj()

                    # Inject shared services
                    if registry is not None:
                        skill.setup(registry)

                    manager.register(skill)

    def reload(self, intent: str, manager, registry=None) -> list[str]:
        """
        Hot-reload a single previously registered skill by its intent.

        Re-imports the module backing the skill, discovers its concrete
        ``Skill`` subclasses, instantiates them, and re-registers each
        instance with the ``SkillManager``. The previous instance for the
        same intent is replaced. Dependency injection via
        ``setup(registry)`` is preserved.

        Args:
            intent: Intent of the skill to reload.
            manager: ``SkillManager`` instance holding the current skill.
            registry: Optional service registry forwarded to ``setup``.

        Returns:
            List of intents successfully re-registered.
        """

        JarvisLogger.info(f"Reload started for intent='{intent}'")

        existing = manager.get(intent)

        # If the manager returned the fallback, this intent is unknown.
        if existing is manager.fallback:
            JarvisLogger.error(
                f"Reload failed: intent='{intent}' not found in SkillManager"
            )
            return []

        module = inspect.getmodule(existing)

        if module is None:
            JarvisLogger.error(
                f"Reload failed: cannot resolve module for intent='{intent}'"
            )
            return []

        module_name = module.__name__

        try:
            reloaded = importlib.reload(module)
        except Exception as exc:
            JarvisLogger.error(
                f"Reload failed: importlib.reload('{module_name}') raised "
                f"{type(exc).__name__}: {exc}"
            )
            return []

        # Drop the previous instances for this module's intents so a reload
        # yields a clean replacement rather than duplicate registration.
        # Direct dict mutation is required: SkillManager exposes no public
        # unregister/remove API, so a reload cannot otherwise evict the
        # stale instance before the new one is registered.
        previous_intents: list[str] = [
            registered_intent
            for registered_intent, registered_skill in list(manager.skills.items())
            if inspect.getmodule(registered_skill) is module
        ]

        for registered_intent in previous_intents:
            manager.skills.pop(registered_intent, None)

        reloaded_intents: list[str] = []

        for _, obj in inspect.getmembers(reloaded, inspect.isclass):
            if not issubclass(obj, Skill) or obj is Skill:
                continue

            try:
                skill = obj()
            except Exception as exc:
                JarvisLogger.error(
                    f"Reload failed: cannot instantiate '{obj.__name__}' "
                    f"from module '{module_name}': {type(exc).__name__}: {exc}"
                )
                continue

            if registry is not None:
                try:
                    skill.setup(registry)
                except Exception as exc:
                    JarvisLogger.error(
                        f"Reload failed: setup('{obj.__name__}') raised "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue

            try:
                manager.register(skill)
            except Exception as exc:
                JarvisLogger.error(
                    f"Reload failed: register('{obj.__name__}') raised "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            reloaded_intents.append(skill.intent)

        if reloaded_intents:
            JarvisLogger.info(
                f"Reload succeeded for intent='{intent}': "
                f"intents={reloaded_intents}"
            )
        else:
            JarvisLogger.error(
                f"Reload failed: no Skill subclasses were re-registered from "
                f"module='{module_name}' for intent='{intent}'"
            )

        return reloaded_intents
