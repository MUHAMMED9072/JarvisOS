from .providers.ollama import OllamaProvider
from .providers.openai import OpenAIProvider
from .providers.claude import ClaudeProvider
from .providers.gemini import GeminiProvider
from .providers.deepseek import DeepSeekProvider

class AIRouter:
    def __init__(self):
        self.providers = {
            "ollama": OllamaProvider(),
            "openai": OpenAIProvider(),
            "claude": ClaudeProvider(),
            "gemini": GeminiProvider(),
            "deepseek": DeepSeekProvider(),
        }

    def ask(self, provider, prompt):
        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}")
        return self.providers[provider].generate(prompt)
