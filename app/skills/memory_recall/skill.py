from app.skills.base import Skill
from app.skills.result import SkillResult


class MemoryRecallSkill(Skill):

    name = "Memory Recall"
    intent = "memory_recall"
    version = "1.0.0"
    description = "Recalls information from JARVIS memory."

    def run(self, request):

        app = self.memory.get_last_application()

        if app:

            return SkillResult.ok(
                message=f"The last application you opened was {app}."
            )

        return SkillResult.fail(
            message="I couldn't find any application in memory."
        )