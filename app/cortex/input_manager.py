from __future__ import annotations

from .models import CortexRequest


class InputManager:
    """
    Entry point for every request entering JARVIS.
    """

    def receive(self, text: str, source: str = "voice") -> CortexRequest:

        return CortexRequest(
            text=text.strip(),
            source=source,
        )