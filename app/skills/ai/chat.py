from app.skills.base import Skill
from app.skills.result import SkillResult


class ChatSkill(Skill):

    name = "Chat Skill"
    intent = "chat"
    version = "1.0.0"
    description = "Reasoning AI"

    def run(self, request):

        return SkillResult.ok(
            "Reasoning Brain will be connected later."
        )