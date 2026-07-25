from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.skills.base import Skill
from app.skills.loader import SkillLoader
from app.skills.manager import SkillManager


@dataclass
class SkillInfo:
    name: str
    intent: str
    description: str
    version: str
    author: str
    enabled: bool = True


@dataclass
class SkillsStats:
    total: int = 0
    enabled: int = 0
    disabled: int = 0


class SkillsController:
    """Orchestrates the Skills Manager page."""

    def __init__(self, registry) -> None:
        self.registry = registry
        self._loader = SkillLoader()
        self._disabled: set[str] = set()

    # ------------------------------------------------------------------
    # Manager access
    # ------------------------------------------------------------------

    @property
    def _manager(self) -> SkillManager:
        return self.registry.get("skill_manager")

    # ------------------------------------------------------------------
    # List / search
    # ------------------------------------------------------------------

    def get_all_skills(self) -> list[SkillInfo]:
        return [
            self._to_info(s)
            for s in self._manager.all_skills()
        ]

    def search_skills(self, query: str) -> list[SkillInfo]:
        if not query.strip():
            return self.get_all_skills()
        q = query.lower()
        results: list[SkillInfo] = []
        for s in self._manager.all_skills():
            info = self._to_info(s)
            if (
                q in info.name.lower()
                or q in info.intent.lower()
                or q in info.description.lower()
            ):
                results.append(info)
        return results

    def get_skill_by_intent(self, intent: str) -> SkillInfo | None:
        skill = self._manager.get(intent)
        if skill is self._manager.fallback:
            return None
        return self._to_info(skill)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_statistics(self) -> SkillsStats:
        all_skills = list(self._manager.all_skills())
        total = len(all_skills)
        enabled = sum(1 for s in all_skills if s.intent not in self._disabled)
        disabled = total - enabled
        return SkillsStats(total=total, enabled=enabled, disabled=disabled)

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_all(self) -> list[str]:
        self._manager.skills.clear()
        self._loader.load(self._manager, self.registry)
        self._disabled.clear()
        return [s.intent for s in self._manager.all_skills()]

    # ------------------------------------------------------------------
    # Enable / Disable
    # ------------------------------------------------------------------

    def toggle_skill(self, intent: str) -> bool:
        if intent in self._disabled:
            self._disabled.remove(intent)
            return True
        self._disabled.add(intent)
        return False

    def is_enabled(self, intent: str) -> bool:
        return intent not in self._disabled

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _to_info(self, skill: Skill) -> SkillInfo:
        return SkillInfo(
            name=skill.name,
            intent=skill.intent,
            description=skill.description,
            version=skill.version,
            author=skill.author,
            enabled=skill.intent not in self._disabled,
        )
