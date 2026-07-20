# app/skills/manager.py
from app.core.logger import JarvisLogger
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

    def unregister(self, intent: str) -> bool:
        """
        Remove a registered skill by intent.

        Args:
            intent: Intent name of the skill to remove.

        Returns:
            ``True`` if a skill was removed, ``False`` if no skill was
            registered under ``intent`` (or removal failed).
        """

        JarvisLogger.info(f"Uninstall started for intent='{intent}'")

        if not intent:
            JarvisLogger.error(
                f"Uninstall failed: empty intent supplied to SkillManager"
            )
            return False

        if intent not in self.skills:
            JarvisLogger.error(
                f"Uninstall failed: intent='{intent}' not found in SkillManager"
            )
            return False

        try:
            removed = self.skills.pop(intent)
        except Exception as exc:
            JarvisLogger.error(
                f"Uninstall failed: pop('{intent}') raised "
                f"{type(exc).__name__}: {exc}"
            )
            return False

        if removed is None:
            JarvisLogger.error(
                f"Uninstall failed: intent='{intent}' resolved to None"
            )
            return False

        JarvisLogger.info(
            f"Uninstall succeeded for intent='{intent}' "
            f"(skill='{removed.__class__.__name__}')"
        )
        return True
