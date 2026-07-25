from __future__ import annotations

import os
import time

from dotenv import load_dotenv

from .base import (
    AIProvider,
    AIResponse,
    ProviderNotConfiguredError,
    validate_str,
    validate_timeout,
)


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

    capabilities: frozenset = frozenset()

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
        self._base_url = validate_str(
            self._resolve_host(base_url),
            "base_url",
            owner=self.__class__.__name__,
        )
        self._model = validate_str(
            self._resolve_model(model),
            "model",
            owner=self.__class__.__name__,
        )
        self._timeout = validate_timeout(timeout, owner=self.__class__.__name__)

    def generate(self, prompt: str, *, model: str | None = None) -> AIResponse:
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

        start = time.monotonic()

        from ollama import chat  # type: ignore[import-not-found]

        response = chat(
            model=effective_model,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - start) * 1000

        return AIResponse(
            response["message"]["content"],
            provider=self.provider_name,
            model=effective_model,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_host(cls, provided: str | None) -> str:
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