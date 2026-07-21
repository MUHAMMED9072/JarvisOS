from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AIProvider(Protocol):
    """
    Production contract that every AI provider must satisfy.

    AIRouter depends only on this protocol.

    Every provider must implement:

        generate(prompt: str) -> str

    Additional provider-specific features (streaming, embeddings,
    function calling, health checks, etc.) are optional and should
    not be required by this base contract.
    """

    def generate(self, prompt: str) -> str:
        """
        Generate a text response for the supplied prompt.
        """
        ...