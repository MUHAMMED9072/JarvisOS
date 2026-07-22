from __future__ import annotations

from app.cortex.handlers import BaseHandler


class AIHandler(BaseHandler):
    """Thin wrapper around AIRouter for LLM interactions."""

    DEFAULT_PROVIDER = "deepseek"

    def chat(self, prompt: str, *, provider: str | None = None) -> str:
        router = self.registry.get("ai_router")
        return router.ask(provider or self.DEFAULT_PROVIDER, prompt)

    def plan(self, task: str) -> str:
        router = self.registry.get("ai_router")
        prompt = f"Create a step-by-step plan for: {task}"
        return router.ask(self.DEFAULT_PROVIDER, prompt)

    def summarize(self, text: str) -> str:
        router = self.registry.get("ai_router")
        prompt = f"Summarize the following:\n\n{text}"
        return router.ask(self.DEFAULT_PROVIDER, prompt)
