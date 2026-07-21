# app/ai/providers/ollama.py
from __future__ import annotations

from ollama import chat


class OllamaProvider:

    provider_name: str = "ollama"

    def generate(self, prompt: str, model: str = "qwen2.5-coder") -> str:

        r = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return r["message"]["content"]
    