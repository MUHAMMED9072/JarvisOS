from typing import Protocol

class AIProvider(Protocol):
    def generate(self, prompt: str) -> str:
        """
        Generate a text response from the AI provider given a text prompt.
        """
        ...
