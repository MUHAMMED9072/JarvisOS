# app/generator/installer.py

import importlib
import inspect

from app.skills.base import Skill
from app.core.logger import get_logger

logger = get_logger(__name__)


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
            logger.exception("Failed to import skill module '%s': %s", module_name, exc)
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

                logger.info(
                    "Registered skill '%s' (intent='%s')",
                    obj.__name__,
                    skill.intent,
                )

            except Exception:
                logger.exception(
                    "Failed to install skill '%s' from module '%s'",
                    obj.__name__,
                    module_name,
                )

        return registered_intents