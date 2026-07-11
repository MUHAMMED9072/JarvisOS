from abc import ABC, abstractmethod
from time import perf_counter

from app.skills.result import SkillResult


class Skill(ABC):

    name = "Unnamed Skill"
    intent = ""
    version = "1.0.0"
    description = ""
    author = "JarvisOS"

    def __init__(self):

        # Injected by SkillLoader
        self.memory = None
        self.event_bus = None
        self.logger = None
        self.skill_manager = None

    def setup(self, registry):
        """
        Inject shared services from the Kernel.
        """

        self.memory = registry.get("memory")
        self.event_bus = registry.get("event_bus")
        self.skill_manager = registry.get("skill_manager")

    def execute(self, request):

        start = perf_counter()

        try:

            result = self.run(request)

            if not isinstance(result, SkillResult):
                raise TypeError(
                    f"{self.__class__.__name__}.run() must return SkillResult"
                )

        except Exception as e:

            result = SkillResult.fail(
                message=str(e)
            )

        result.skill = self.name
        result.execution_time = round(
            perf_counter() - start,
            4
        )

        return result

    @abstractmethod
    def run(self, request):
        pass