from __future__ import annotations

from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------
#
# All provider-raised errors derive from ``AIProviderError`` so that
# callers (e.g. ``CodeGenerator``, ``AIManager``, future skills) can
# catch every provider failure with a single ``except AIProviderError``
# clause and still distinguish the *kind* of failure via the subclasses:
#
#   * ``ProviderNotConfiguredError``  - required configuration missing
#                                       or invalid (e.g. no API key).
#   * ``ProviderNotImplementedError`` - the provider's real backend
#                                       integration is not yet wired
#                                       (this P2-13 phase).
#
# Per ``AI_SYSTEM.md`` §"Rules for Implementing a Real Provider",
# providers must raise a *specific* exception type rather than letting
# SDK exceptions propagate unannotated, so the router / caller can
# react to "no API key" vs. "network error" vs. "rate limited" vs.
# "not yet implemented" separately.
# ---------------------------------------------------------------------------


class AIProviderError(Exception):
    """
    Base class for every error raised by an ``AIProvider`` implementation.

    Catching ``AIProviderError`` covers the entire provider failure
    surface.  Subclasses are caught individually when a caller needs
    to distinguish the underlying cause.
    """


class ProviderNotConfiguredError(AIProviderError):
    """
    Raised when a provider is missing or given invalid configuration.

    Typical triggers:

    * The required environment variable (e.g. ``OPENAI_API_KEY``) is
      not set and no override was supplied to the constructor.
    * An explicit ``api_key`` argument is empty or not a string.
    * ``base_url`` / ``model`` / ``timeout`` fails type validation.
    """


class ProviderNotImplementedError(AIProviderError):
    """
    Raised when a provider's real backend integration is not yet wired.

    During the P2-13 stub phase every cloud provider's ``generate()``
    raises this exception once configuration has been validated.  When
    the real SDK calls are added in a later roadmap item, only the
    body of ``generate()`` changes - the exception class itself
    stays in place for callers that need to detect "not yet ready".
    """


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


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

    Every concrete provider is also expected to declare a class
    attribute ``provider_name`` (a non-empty ``str``).  It is not
    part of this ``Protocol`` because adding a non-method member
    to a ``Protocol`` makes ``issubclass()`` raise ``TypeError``;
    ``AIRouter`` enforces it via ``getattr(cls, "provider_name",
    None)`` at registration time.
    """

    def generate(self, prompt: str) -> str:
        """
        Generate a text response for the supplied prompt.
        """
        ...
