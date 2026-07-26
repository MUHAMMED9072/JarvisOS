from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntFlag, auto
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Generator, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..conversation import ConversationMessage
    from ..structured import StructuredSchema, StructuredResult
    from ..tools import ToolCall, ToolDefinition


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------
#
# All provider-raised errors derive from ``AIProviderError`` so that
# callers can catch every provider failure with a single clause and
# still distinguish the kind of failure via the subclasses:
#
#   * ``ProviderNotConfiguredError``    - required configuration is
#       missing or invalid (e.g. no API key, bad URL, bad model).
#   * ``ProviderNotImplementedError``   - the provider's real backend
#       integration is not yet wired (stubs raise this after config
#       validation passes).
#   * ``ProviderTimeoutError``          - the provider's SDK raised a
#       timeout or the call exceeded ``timeout`` seconds.
#   * ``ProviderRateLimitError``        - the provider returned a
#       rate-limit response (e.g. HTTP 429).
#   * ``ProviderConnectionError``       - network connectivity failure
#       (DNS, refused connection, TLS error).
#   * ``ProviderAPIAuthorizationError`` - authentication or
#       authorization failure (invalid key, expired token).
#   * ``ProviderUnexpectedError``       - any other provider-side
#       failure that doesn't fit the categories above.
#
# Per ``AI_SYSTEM.md`` §"Rules for Implementing a Real Provider",
# providers must raise a *specific* exception type rather than letting
# SDK exceptions propagate unannotated, so the router / caller can
# react to each kind of failure separately.
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
    * ``base_url`` / ``model`` / ``timeout`` / ``max_retries``
      fails type or value validation.
    """


class ProviderNotImplementedError(AIProviderError):
    """
    Raised when a provider's real backend integration is not yet wired.

    During the stub phase every cloud provider's ``generate()``
    raises this exception once configuration has been validated, so
    callers can distinguish "not configured" from "feature pending".
    """


class ProviderTimeoutError(AIProviderError):
    """Raised when a provider call exceeds its configured timeout."""


class ProviderRateLimitError(AIProviderError):
    """Raised when a provider signals that the caller has exceeded its rate limit."""


class ProviderConnectionError(AIProviderError):
    """Raised when a network connectivity failure prevents reaching the provider."""


class ProviderAPIAuthorizationError(AIProviderError):
    """Raised when the provider rejects the current credentials."""


class ProviderUnexpectedError(AIProviderError):
    """Raised for any provider-side failure that doesn't fit the categories above."""


class AllProvidersFailedError(AIProviderError):
    """Raised when every provider in a routing chain has failed."""

    def __init__(
        self,
        failures: dict[str, Exception] | None = None,
        message: str = "All providers failed",
    ) -> None:
        self.failures = failures or {}
        super().__init__(message)


# ---------------------------------------------------------------------------
# Capability flags
# ---------------------------------------------------------------------------


class ProviderCapability(IntFlag):
    """Capability flags that describe what a provider supports."""

    STREAMING = auto()
    FUNCTION_CALLING = auto()
    EMBEDDINGS = auto()
    IMAGE_INPUT = auto()
    JSON_OUTPUT = auto()
    CONVERSATION = auto()
    SYSTEM_PROMPT = auto()
    REASONING = auto()
    TEXT_GENERATION = auto()


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """Structured metadata about a provider instance."""

    name: str
    model: str
    base_url: str
    capabilities: frozenset[ProviderCapability] = frozenset()
    timeout: float = 30.0


class AIResponse(str):
    """
    A string response enriched with provider metadata.

    ``AIResponse`` is a subclass of ``str``, so every existing caller that
    treats the return value as a string continues to work without changes.
    New callers can access the richer metadata attributes when needed:

        response = provider.generate("Hello")
        print(response)            # works: ``AIResponse`` IS-A ``str``
        print(response.provider)   # new: ``"openai"``
        print(response.model)      # new: ``"gpt-4o-mini"``
        print(response.latency_ms) # new: float
    """

    __slots__ = ("provider", "model", "latency_ms", "metadata")

    def __new__(
        cls,
        content: str,
        *,
        provider: str,
        model: str,
        latency_ms: float,
        metadata: dict | None = None,
    ) -> AIResponse:
        instance = super().__new__(cls, content)
        instance.provider = provider
        instance.model = model
        instance.latency_ms = latency_ms
        instance.metadata = metadata or {}
        return instance


# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------


def validate_str(value: object, field: str, owner: str = "") -> str:
    """Validate that *value* is a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        cls_name = owner or "Provider"
        raise ProviderNotConfiguredError(
            f"{cls_name}: {field} must be a non-empty string"
        )
    return value


def validate_optional_str(value: object, field: str, owner: str = "") -> str | None:
    """Validate that *value* is either ``None`` or a non-empty string."""
    if value is None:
        return None
    return validate_str(value, field, owner)


def validate_timeout(value: object, owner: str = "") -> float:
    """Validate that *value* is a positive number (rejects bool, which is an ``int`` subclass)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        cls_name = owner or "Provider"
        raise ProviderNotConfiguredError(
            f"{cls_name}: timeout must be a positive number, "
            f"got {type(value).__name__}"
        )
    if value <= 0:
        cls_name = owner or "Provider"
        raise ProviderNotConfiguredError(
            f"{cls_name}: timeout must be > 0, got {value!r}"
        )
    return float(value)


def validate_api_key(value: object, field: str, owner: str = "") -> str:
    """Validate that *value* is a non-empty string suitable for an API key."""
    if value is None:
        raise ProviderNotConfiguredError(
            f"{owner or 'Provider'}: {field} is required"
        )
    return validate_str(value, field, owner)


# ---------------------------------------------------------------------------
# Standardized exception mapping
# ---------------------------------------------------------------------------


def map_exception(exc: Exception, provider_name: str) -> AIProviderError:
    """
    Map a provider SDK exception to the appropriate ``AIProviderError``
    subclass so that callers can react to specific failure modes.

    If *exc* is already an ``AIProviderError``, it is returned as-is.
    Otherwise a best-effort category is chosen based on the exception
    type name and message content, then wrapped in
    ``ProviderUnexpectedError``.
    """
    if isinstance(exc, AIProviderError):
        return exc

    exc_name = type(exc).__name__
    exc_msg = str(exc).lower()

    if "timeout" in exc_name.lower() or "deadline" in exc_name.lower() or "timeout" in exc_msg or "deadline" in exc_msg:
        return ProviderTimeoutError(f"{provider_name}: {exc}")
    if "ratelimit" in exc_name.lower() or "429" in exc_msg or "rate limit" in exc_msg:
        return ProviderRateLimitError(f"{provider_name}: {exc}")
    if "connection" in exc_name.lower() or "connection" in exc_msg or "network" in exc_msg:
        return ProviderConnectionError(f"{provider_name}: {exc}")
    if "auth" in exc_name.lower() or "401" in exc_msg or "403" in exc_msg:
        return ProviderAPIAuthorizationError(f"{provider_name}: {exc}")

    return ProviderUnexpectedError(f"{provider_name}: {exc}")


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 0.5,
    retryable: tuple[type[Exception], ...] = (
        ProviderTimeoutError,
        ProviderConnectionError,
    ),
):
    """
    Decorator that retries a provider call on transient failures.

    Retries only for exceptions in *retryable* (defaults to timeout and
    connection errors).  Non-retryable exceptions (e.g. configuration or
    authorization errors) propagate immediately.

    Backoff doubles with each attempt: ``base_delay * 2 ** attempt``.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> AIResponse:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if not isinstance(exc, retryable) or attempt >= max_retries:
                        raise
                    last_exc = exc
                    if args:
                        tracker = getattr(args[0], '_retry_tracker', None)
                        if tracker is not None:
                            tracker(attempt + 1, max_retries, type(exc).__name__)
                    delay = base_delay * (2**attempt)
                    time.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Shared SDK call wrapper
# ---------------------------------------------------------------------------


def _call_sdk(
    sdk_call: Callable[[], Any],
    provider_name: str,
    model: str,
    response_handler: Callable[[Any], tuple[str, dict]],
) -> AIResponse:
    """
    Execute a provider SDK call, time it, map exceptions, and build an
    ``AIResponse`` in a single step.

    Parameters
    ----------
    sdk_call
        A zero-argument callable that executes the actual SDK request and
        returns the raw response object.
    provider_name
        Used as ``AIResponse.provider`` and in exception messages.
    model
        Used as ``AIResponse.model``.
    response_handler
        Receives the raw SDK response and returns ``(content, metadata)``
        where *content* is the response text and *metadata* is a dict with
        usage information (token counts, etc.).

    Returns
    -------
    AIResponse
        A fully populated response.
    """
    start = time.monotonic()
    try:
        response = sdk_call()
    except Exception as exc:
        raise map_exception(exc, provider_name)
    latency_ms = (time.monotonic() - start) * 1000
    content, metadata = response_handler(response)
    return AIResponse(
        content,
        provider=provider_name,
        model=model,
        latency_ms=latency_ms,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Streaming types
# ---------------------------------------------------------------------------


@dataclass
class AIStreamChunk:
    """A single chunk yielded during streaming generation."""
    content: str = ""
    finish_reason: str | None = None
    usage: dict | None = None


class AIStreamResponse:
    """Iterable streaming response that accumulates chunks and can
    produce a final assembled ``AIResponse``.

    Usage::

        stream = provider.generate_stream("Hello")
        for chunk in stream:
            print(chunk.content, end="")
        result = stream.final_response()
    """

    def __init__(
        self,
        provider: str,
        model: str,
        generator: Generator[AIStreamChunk, None, None],
    ) -> None:
        self._provider = provider
        self._model = model
        self._generator = generator
        self._full_text: list[str] = []
        self._finish_reason: str | None = None
        self._usage: dict = {}
        self._start_time = time.monotonic()
        self._cancelled = False

    def __iter__(self) -> AIStreamResponse:
        return self

    def __next__(self) -> AIStreamChunk:
        if self._cancelled:
            raise StopIteration
        try:
            chunk = next(self._generator)
            self._full_text.append(chunk.content)
            if chunk.finish_reason:
                self._finish_reason = chunk.finish_reason
            if chunk.usage:
                self._usage = chunk.usage
            return chunk
        except StopIteration:
            raise

    def cancel(self) -> None:
        """Gracefully cancel the stream and release resources."""
        self._cancelled = True
        self._generator.close()

    def final_response(self) -> AIResponse:
        """Assemble the final ``AIResponse`` after the stream completes."""
        metadata: dict = {}
        if self._finish_reason:
            metadata["finish_reason"] = self._finish_reason
        if self._usage:
            metadata.update(self._usage)
        return AIResponse(
            "".join(self._full_text),
            provider=self._provider,
            model=self._model,
            latency_ms=(time.monotonic() - self._start_time) * 1000,
            metadata=metadata,
        )


def _stream_sdk(
    sdk_call: Callable[[], Any],
    provider_name: str,
    chunk_handler: Callable[[Any], AIStreamChunk | None],
) -> Generator[AIStreamChunk, None, None]:
    """Execute a streaming SDK call and yield ``AIStreamChunk`` items.

    Parameters
    ----------
    sdk_call
        A zero-argument callable that initiates the streaming API call
        and returns an iterable of raw SDK response chunks.
    provider_name
        Used in exception messages.
    chunk_handler
        Receives each raw SDK chunk and returns an ``AIStreamChunk``
        (or ``None`` to skip the chunk).

    Yields
    ------
    AIStreamChunk
        One per content delta from the SDK stream.
    """
    try:
        stream = sdk_call()
    except Exception as exc:
        raise map_exception(exc, provider_name)
    try:
        for raw_chunk in stream:
            chunk = chunk_handler(raw_chunk)
            if chunk is not None:
                yield chunk
    except Exception as exc:
        raise map_exception(exc, provider_name)


# ---------------------------------------------------------------------------
# Shared provider base class
# ---------------------------------------------------------------------------


class _ProviderBase:
    """
    Shared base that provides default ``provider_info()`` and metadata
    attributes for all concrete AI providers.

    Subclasses must define:
        ``provider_name`` (``str``) — registration key for ``AIRouter``.
        ``capabilities`` (``frozenset`` of ``ProviderCapability``).
        ``_model`` (``str``) — the default / configured model name.
        ``_base_url`` (``str``) — the API endpoint.
        ``_timeout`` (``float``) — request timeout in seconds.
    """

    provider_name: str = ""
    capabilities: frozenset = frozenset()
    _model: str = ""
    _base_url: str = ""
    _timeout: float = 30.0

    def provider_info(self) -> ProviderMetadata:
        """Return structured metadata about this provider instance."""
        return ProviderMetadata(
            name=self.provider_name,
            model=self._model,
            base_url=self._base_url,
            capabilities=self.capabilities,
            timeout=self._timeout,
        )

    def check_availability(self) -> bool:
        """Return True if this provider appears configured and usable.

        Subclasses that require API keys or other credentials may
        override this to perform the appropriate check.  The default
        implementation returns ``True``.
        """
        try:
            if hasattr(self, "_resolve_api_key"):
                self._resolve_api_key()  # type: ignore[attr-defined]
                return True
            return True
        except AIProviderError:
            return False

    def format_messages(
        self,
        messages: list[ConversationMessage],
    ) -> list[dict]:
        """Translate conversation messages into SDK-native format.

        Override in subclasses to return the exact structure expected
        by the respective SDK.  The default implementation returns
        ``{"role": ..., "content": ...}`` dicts suitable for
        OpenAI-compatible chat completion APIs.
        """
        result: list[dict] = []
        for m in messages:
            entry: dict = {"role": m.role, "content": m.content}
            if m.metadata:
                entry["metadata"] = m.metadata
            result.append(entry)
        return result

    def format_tools(
        self, tools: list[ToolDefinition],
    ) -> list[dict]:
        """Translate internal ``ToolDefinition`` objects into the
        SDK-native tool format expected by this provider.

        Subclasses that support tool calling **must** override this
        method.  The default implementation raises
        ``NotImplementedError``.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement format_tools"
        )

    def parse_tool_calls(self, raw_response: Any) -> list[ToolCall]:
        """Extract ``ToolCall`` objects from an SDK response.

        Subclasses that support tool calling **must** override this
        method.  The default implementation returns an empty list.
        """
        return []

    def format_structured_schema(
        self, schema: StructuredSchema,
    ) -> dict | None:
        """Translate *schema* into SDK-specific structured output config.

        Subclasses that support structured output **may** override this
        method.  The default implementation returns ``None`` (no
        special SDK configuration).
        """
        return None

    def parse_structured_response(
        self, raw_text: str, schema: StructuredSchema,
    ) -> StructuredResult:
        """Parse and validate *raw_text* against *schema*.

        Override in subclasses that need custom parsing logic
        (e.g. extracting JSON from a code fence).  The default
        implementation delegates to :func:`parse_structured_output`.
        """
        from ..structured import parse_structured_output
        return parse_structured_output(raw_text, schema)


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AIProvider(Protocol):
    """
    Production contract that every AI provider must satisfy.

    ``AIRouter`` depends on this protocol.

    Every provider must implement:

        generate(prompt: str) -> str

    Each provider is also expected to declare a class attribute
    ``provider_name`` (a non-empty ``str``).  It is not part of
    this ``Protocol`` because adding a non-method member to a
    ``Protocol`` makes ``issubclass()`` raise ``TypeError`` in
    Python 3.14+; ``AIRouter`` enforces it via
    ``getattr(cls, "provider_name", None)`` at registration time.

    Additional optional features (documented best practices):

    * ``capabilities`` — a ``frozenset`` of ``ProviderCapability``
      flags.  Check with:
      ``getattr(provider, "capabilities", frozenset())``.

    * ``provider_info()`` — returns a ``ProviderMetadata``
      dataclass.  Check with:
      ``getattr(provider, "provider_info", None)``.
    """

    def generate(
        self,
        prompt: str,
        tools: list[ToolDefinition] | None = None,
        schema: StructuredSchema | None = None,
    ) -> str:
        """Generate a text (or tool-assisted) response for the supplied
        prompt.

        If *tools* is provided and the provider supports tool calling,
        the provider may request tool invocations.  Tool calls are
        returned in the ``AIResponse.metadata["tool_calls"]`` list.

        If *schema* is provided and the provider supports structured
        output, the response is parsed and validated against the
        schema.  The ``StructuredResult`` is placed in
        ``AIResponse.metadata["structured"]``.

        Providers that do not support these features silently ignore
        the corresponding parameters.
        """
        ...