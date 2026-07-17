SKILL_TEMPLATE = '''from app.skills.base import Skill
from app.skills.result import SkillResult


class {class_name}(Skill):
    name = "{skill_name}"
    intent = "{intent}"
    version = "1.0.0"
    description = "{description}"

    def run(self, request) -> SkillResult:
        return SkillResult.ok(message={body})
'''