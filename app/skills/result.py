from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:

    success: bool

    message: str = ""

    data: dict[str, Any] = field(default_factory=dict)

    execution_time: float = 0

    skill: str = ""

    @classmethod
    def ok(cls, message="", data=None):

        return cls(
            success=True,
            message=message,
            data=data or {}
        )

    @classmethod
    def fail(cls, message="", data=None):

        return cls(
            success=False,
            message=message,
            data=data or {}
        )