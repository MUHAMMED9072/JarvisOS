from __future__ import annotations

from .providers.base import AIResponse
from .router import AIRouter


class AIManager:
    def __init__(self):
        self.router = AIRouter()

    def ask(self, provider, prompt) -> AIResponse:
        return self.router.ask(provider, prompt)