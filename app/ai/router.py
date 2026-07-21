# app/ai/router.py
from __future__ import annotations

from .providers.ollama import OllamaProvider
from .providers.openai import OpenAIProvider
from .providers.claude import ClaudeProvider
from .providers.gemini import GeminiProvider
from .providers.deepseek import DeepSeekProvider
from .providers.base import AIProvider


class AIRouter:

    def __init__(self):

        self.providers: dict[str, AIProvider] = {
            "ollama": OllamaProvider(),
            "openai": OpenAIProvider(),
            "claude": ClaudeProvider(),
            "gemini": GeminiProvider(),
            "deepseek": DeepSeekProvider(),
        }

    def ask(self, provider: str, prompt: str) -> str:

        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}")
        return self.providers[provider].generate(prompt)
