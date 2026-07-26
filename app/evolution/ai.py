from __future__ import annotations

from app.ai.providers.base import AIResponse, ProviderCapability


class EvolutionAI:
    """AIManager wrapper for Evolution Engine AI interactions.

    All AI requests flow through:
        Evolution Engine -> EvolutionAI -> AIManager/AIRouter -> Provider

    Uses capability-based routing instead of hardcoded provider names.
    Preserves metadata through AIResponse.
    """

    def __init__(self, registry):
        self._ai = registry.get("ai_manager")
        self._router = registry.get("ai_router")

    def _ask(self, prompt: str) -> AIResponse:
        caps = frozenset({ProviderCapability.TEXT_GENERATION})
        return self._router.ask_routed(prompt, required_capabilities=caps)

    def plan(self, objective: str) -> AIResponse:
        """Create an evolution plan via capability-routed text generation."""
        return self._ask(objective)

    def generate(self, prompt: str) -> AIResponse:
        """Generate code via capability-routed text generation."""
        return self._ask(prompt)

    def autofix(self, prompt: str) -> AIResponse:
        """Auto-fix a patch via capability-routed text generation."""
        return self._ask(prompt)
