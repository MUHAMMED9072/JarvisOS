# app/ai/providers/base.py
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AIProvider(Protocol):
    """
    Contract that every AI provider must satisfy.

    The router only relies on a single operation: ``generate(prompt)``.
    The return type is intentionally a plain ``str`` because that is the
    exact return shape of every concrete provider in
    ``app/ai/providers/``.
    """

    def generate(self, prompt: str) -> str:
        ...
