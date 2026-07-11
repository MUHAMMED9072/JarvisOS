from app.skills.unknown.fallback import FallbackSkill


class SkillManager:

    def __init__(self):

        self.skills = {}
        self.fallback = FallbackSkill()

    def register(self, skill):

        intent = skill.intent

        if not intent:
            raise ValueError(
                f"{skill.__class__.__name__} has no intent."
            )

        self.skills[intent] = skill

    def get(self, intent):

        return self.skills.get(
            intent,
            self.fallback
        )

    def all_skills(self):

        return self.skills.values()