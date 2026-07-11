from app.skills.base import Skill
from app.skills.result import SkillResult


class FallbackSkill(Skill):

    name = "Fallback Skill"
    intent = "unknown"
    version = "1.0.0"
    description = "Fallback for unsupported commands"

    def run(self, request):

        return SkillResult.fail(
            "Sorry, I don't know how to handle that request yet."
        )