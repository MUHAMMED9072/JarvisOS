# app/ai/providers/gemini.py
"""
Google Gemini provider stub.

Real SDK integration (the ``google-generativeai`` Python package) is
intentionally deferred - this module imports no third-party SDK and
makes no network calls.  The public API (constructor signature,
``provider_name``, ``generate(prompt) -> str``) is shaped to match
the production ``AIProvider`` contract so the real implementation
can be dropped in later by replacing only the body of
``generate()``.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from .base import (
    AIProvider,
    ProviderNotConfiguredError,
    ProviderNotImplementedError,
)


load_dotenv()


class GeminiProvider(AIProvider):
    """
    Stub for the Google Gemini API backend.

    ``provider_name`` is the registration key used by ``AIRouter``;
    do not change it without updating every call site that dispatches
    by name.
    """

    provider_name: str = "gemini"

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
    DEFAULT_MODEL = "gemini-2.0-flash-exp"
    DEFAULT_TIMEOUT = 30.0
    ENV_API_KEY_VAR = "GEMINI_API_KEY"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Construct the Gemini provider.

        ``api_key`` may be supplied explicitly for testing; when
        omitted, it is read lazily from ``GEMINI_API_KEY`` the first
        time ``generate()`` is called.  This lazy resolution is what
        lets ``AIRouter`` instantiate the provider with no arguments
        even when the key has not been configured.

        ``base_url``, ``model`` and ``timeout`` are validated eagerly
        and raise ``ProviderNotConfiguredError`` on bad input.
        """
        self._api_key: str | None = self._validate_optional_str(
            api_key, "api_key"
        )
        self._base_url = self._validate_str(
            base_url if base_url is not None else self.DEFAULT_BASE_URL,
            "base_url",
        )
        self._model = self._validate_str(
            model if model is not None else self.DEFAULT_MODEL,
            "model",
        )
        self._timeout = self._validate_timeout(timeout)

    def generate(self, prompt: str) -> str:
        """
        Generate a text response for the supplied prompt.

        The real implementation will call the Gemini generateContent
        endpoint at ``self._base_url`` with ``self._model`` and a
        30-second (configurable) timeout.  Until the SDK is wired in
        this stub raises ``ProviderNotImplementedError`` after
        configuration has been validated.
        """
        if not isinstance(prompt, str):
            raise TypeError(
                f"prompt must be str, got {type(prompt).__name__}"
            )
        self._resolve_api_key()
        raise ProviderNotImplementedError(
            f"{type(self).__name__}.generate() is not yet implemented; "
            f"real Google Gemini SDK integration pending. "
            f"Configured model: {self._model}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_api_key(self) -> str:
        """Return the API key, loading from env on first use."""
        if self._api_key:
            return self._api_key
        env_key = os.getenv(self.ENV_API_KEY_VAR)
        if isinstance(env_key, str) and env_key.strip():
            self._api_key = env_key
            return env_key
        raise ProviderNotConfiguredError(
            f"{type(self).__name__}: {self.ENV_API_KEY_VAR} is not set "
            f"in the environment and no api_key= was supplied"
        )

    @staticmethod
    def _validate_str(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ProviderNotConfiguredError(
                f"GeminiProvider: {field} must be a non-empty string"
            )
        return value

    @staticmethod
    def _validate_optional_str(value: object, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ProviderNotConfiguredError(
                f"GeminiProvider: {field} must be a non-empty string "
                f"when provided"
            )
        return value

    @staticmethod
    def _validate_timeout(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProviderNotConfiguredError(
                f"GeminiProvider: timeout must be a positive number, "
                f"got {type(value).__name__}"
            )
        if value <= 0:
            raise ProviderNotConfiguredError(
                f"GeminiProvider: timeout must be > 0, got {value!r}"
            )
        return float(value)
