# app/generator/installer.py

import importlib
import inspect

from app.core.logger import JarvisLogger
from app.skills.base import Skill


class SkillInstaller:
    """
    Dynamically installs a single skill module into a SkillManager.

    Workflow:
      1. Import the module.
      2. Discover concrete Skill subclasses.
      3. Instantiate each subclass.
      4. Inject shared services via skill.setup(registry).
      5. Register the skill with the manager.
    """

    def install(self, module_name: str, manager, registry=None) -> list[str]:
        """
        Load a skill module, register all valid Skill subclasses,
        and return the list of successfully registered intents.

        Args:
            module_name: Fully-qualified module path.
            manager: SkillManager instance.
            registry: Optional ServiceRegistry for dependency injection.

        Returns:
            List of registered intent names.
        """

        try:
            module = importlib.import_module(module_name)
        except (ModuleNotFoundError, ImportError) as exc:
            JarvisLogger.error(
                f"Failed to import skill module '{module_name}': {exc}"
            )
            return []

        registered_intents: list[str] = []

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, Skill) or obj is Skill:
                continue

            try:
                skill = obj()

                if registry is not None:
                    skill.setup(registry)

                manager.register(skill)
                registered_intents.append(skill.intent)

                JarvisLogger.info(
                    f"Registered skill '{obj.__name__}' (intent='{skill.intent}')"
                )

            except Exception as exc:
                JarvisLogger.error(
                    f"Failed to install skill '{obj.__name__}' "
                    f"from module '{module_name}': {exc}"
                )

        return registered_intents