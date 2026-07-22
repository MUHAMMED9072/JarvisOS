# app/ai/providers/ollama.py
"""
Ollama provider - local LLM runtime.

This is the only provider with a real, working SDK integration today.
The ``ollama`` Python package is imported lazily inside ``generate()``
rather than at module load time, so that importing the module never
fails on machines that do not have the ``ollama`` package installed
(e.g. CI, or systems that only use the cloud providers).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from .base import AIProvider, ProviderNotConfiguredError


load_dotenv()


class OllamaProvider(AIProvider):
    """
    Provider for a locally running Ollama daemon.

    The provider_name ``"ollama"`` is the registration key used by
    ``AIRouter``; do not change it without updating every call site
    that dispatches by name.

    The class declares the ``AIProvider`` protocol explicitly so that
    ``isinstance(provider, AIProvider)`` returns ``True`` (the
    runtime-checkable protocol would otherwise be satisfied only by
    duck typing on the ``generate`` method).
    """

    provider_name: str = "ollama"

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "qwen2.5-coder"
    DEFAULT_TIMEOUT = 30.0
    ENV_HOST_VAR = "OLLAMA_HOST"
    ENV_MODEL_VAR = "OLLAMA_MODEL"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Construct the Ollama provider.

        All arguments are keyword-only and optional.  Missing values
        fall back to environment variables (``OLLAMA_HOST``,
        ``OLLAMA_MODEL``) and finally to the class-level defaults.

        No network call is performed here - the daemon is contacted
        only when ``generate()`` is invoked.
        """
        self._base_url = self._validate_str(
            self._resolve_host(base_url),
            "base_url",
        )
        self._model = self._validate_str(
            self._resolve_model(model),
            "model",
        )
        self._timeout = self._validate_timeout(timeout)

    def generate(self, prompt: str, *, model: str | None = None) -> str:
        """
        Generate a text response for the supplied prompt.

        ``model`` is accepted as an optional override to preserve
        the historical call shape used by the Evolution Engine
        (``OllamaProvider().generate(prompt, model=...)``); when
        omitted, the constructor's model is used.

        The ``ollama`` Python package is imported lazily so that
        simply importing this module never requires the SDK to be
        installed.
        """
        if not isinstance(prompt, str):
            raise TypeError(
                f"prompt must be str, got {type(prompt).__name__}"
            )

        effective_model = model if isinstance(model, str) and model else self._model

        # Lazy SDK import - keeps the module importable on machines
        # where the ``ollama`` package is not installed.
        from ollama import chat  # type: ignore[import-not-found]

        response = chat(
            model=effective_model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_host(cls, provided: str | None) -> str:
        """Return the explicit value if given, else the env var,
        else the default.  An explicit empty string is *not*
        coerced to the default - it is preserved so the validator
        can reject it."""
        if provided is not None:
            return provided
        env_value = os.getenv(cls.ENV_HOST_VAR)
        if env_value is not None:
            return env_value
        return cls.DEFAULT_BASE_URL

    @classmethod
    def _resolve_model(cls, provided: str | None) -> str:
        if provided is not None:
            return provided
        env_value = os.getenv(cls.ENV_MODEL_VAR)
        if env_value is not None:
            return env_value
        return cls.DEFAULT_MODEL

    @staticmethod
    def _validate_str(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ProviderNotConfiguredError(
                f"OllamaProvider: {field} must be a non-empty string"
            )
        return value

    @staticmethod
    def _validate_timeout(value: object) -> float:
        # Reject bool explicitly (``bool`` is a subclass of ``int``).
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProviderNotConfiguredError(
                f"OllamaProvider: timeout must be a positive number, "
                f"got {type(value).__name__}"
            )
        if value <= 0:
            raise ProviderNotConfiguredError(
                f"OllamaProvider: timeout must be > 0, got {value!r}"
            )
        return float(value)
