```python
import importlib
import inspect
import pkgutil

import app.skills

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

            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                continue

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
```