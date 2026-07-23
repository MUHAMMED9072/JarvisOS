"""Session-control command router.

Empty by default. The router exists so that short session-control
phrases (e.g. "stop listening", "cancel", "mute") can be intercepted
*before* they reach Cortex. It is **not** a parser of natural
language; it only matches a configurable list of literal phrases.

Routing is intentionally minimal:

* ``is_command(text)`` — is this a session-control phrase?
* ``handle(text)`` — if yes, return a :class:`SkillResult` describing
  what to do. The orchestrator (``VoiceManager``) is the only
  consumer.

There is no intent detection, no entity extraction, no LLM call.
"""

from __future__ import annotations

from typing import Optional

from app.skills.result import SkillResult
from app.voice.config import VoiceConfig


class CommandRouter:
    """Optional pre-cortex short-circuit for session control."""

    def __init__(self, config: VoiceConfig | None = None) -> None:
        self._config = config or VoiceConfig()

    @property
    def commands(self) -> tuple[str, ...]:
        return self._config.commands

    def is_command(self, text: str) -> bool:
        """True if ``text`` is one of the configured session commands."""
        if not text or not self._config.commands:
            return False

        normalized = text.strip().lower()
        return normalized in {cmd.lower() for cmd in self._config.commands}

    def handle(self, text: str) -> Optional[SkillResult]:
        """Return a :class:`SkillResult` for the matched command, or None.

        The default implementation is a passthrough that simply
        acknowledges the command. Extend by mapping phrases to
        custom handlers in a subclass.
        """
        if not self.is_command(text):
            return None

        # The default behaviour is to acknowledge without forwarding
        # to cortex. Concrete actions (mute, stop, etc.) are out of
        # scope for P3-22.
        return SkillResult.ok(
            message=f"Command acknowledged: {text.strip()}",
            data={"command": text.strip().lower()},
        )
