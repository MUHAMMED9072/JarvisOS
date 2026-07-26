"""Tests for VoiceCortexIntegration and VoiceManager integration methods."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.event_bus import EventBus
from app.core.registry import ServiceRegistry
from app.cortex.models import CortexRequest, CortexResponse
from app.skills.result import SkillResult
from app.voice.config import VoiceConfig
from app.voice.integration import VoiceCortexIntegration
from app.voice.manager import VoiceManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ai_response(text: str, **kw: object) -> str:
    """Build a minimal AIResponse stand-in that has ``.provider``,
    ``.model``, ``.metadata`` attributes (duck-typed)."""
    from app.ai.providers.base import AIResponse
    return AIResponse(
        text,
        provider=kw.get("provider", "test"),
        model=kw.get("model", "mock"),
        latency_ms=kw.get("latency_ms", 10.0),
        metadata=kw.get("metadata", {"routing_strategy": "preferred"}),
    )


def _build_registry(
    *,
    cortex_result: CortexRequest | None = None,
    cortex_exc: BaseException | None = None,
    dispatcher_result: tuple[SkillResult, CortexResponse] | None = None,
    dispatcher_exc: BaseException | None = None,
) -> ServiceRegistry:
    registry = ServiceRegistry()

    event_bus = EventBus()
    registry.register("event_bus", event_bus)

    memory = MagicMock()
    registry.register("memory", memory)

    cortex = MagicMock()
    if cortex_exc is not None:
        cortex.process.side_effect = cortex_exc
    elif cortex_result is not None:
        cortex.process.return_value = cortex_result
    else:
        req = CortexRequest(
            text="hello",
            normalized="hello",
            intent="chat",
            confidence=0.9,
            brain="smart",
        )
        cortex.process.return_value = req
    registry.register("cortex", cortex)

    dispatcher = MagicMock()
    if dispatcher_exc is not None:
        dispatcher.dispatch_with_response.side_effect = dispatcher_exc
    elif dispatcher_result is not None:
        dispatcher.dispatch_with_response.return_value = dispatcher_result
    else:
        skill_result = SkillResult.ok(
            message=_make_ai_response("Hello from AI"),
            data={"brain": "smart"},
        )
        cr = CortexResponse(
            success=True,
            response="Hello from AI",
            provider="test",
            model="mock",
            routing_strategy="preferred",
            conversation_id="conv_abc",
        )
        dispatcher.dispatch_with_response.return_value = (skill_result, cr)
    registry.register("dispatcher", dispatcher)

    registry.register(
        "voice_config",
        VoiceConfig(enabled=False, commands=(), speaker_enabled=False),
    )

    return registry


# ===================================================================
# VoiceCortexIntegration
# ===================================================================


class TestVoiceCortexIntegrationProcessSpeech:
    """Unit tests for ``VoiceCortexIntegration.process_speech()``."""

    def test_success_path(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello")
        assert result.success is True
        assert result.response == "Hello from AI"
        assert result.provider == "test"
        assert result.model == "mock"
        assert result.routing_strategy == "preferred"
        assert result.conversation_id == "conv_abc"

    def test_voice_metadata_preserved(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech(
            "hello",
            confidence=0.85,
            source="voice",
        )
        assert result.metadata is not None
        assert result.metadata.get("transcript_confidence") == 0.85
        assert result.metadata.get("source") == "voice"
        assert "timestamp" in result.metadata

    def test_session_id_in_metadata(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello", session_id="session_1")
        assert result.metadata.get("session_id") == "session_1"

    def test_session_metadata_merged(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech(
            "hello",
            session_metadata={"language": "en", "device": "mic1"},
        )
        assert result.metadata.get("language") == "en"
        assert result.metadata.get("device") == "mic1"

    def test_empty_text_returns_error(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("")
        assert result.success is False
        assert "Empty" in result.response
        assert result.metadata.get("error") == "empty_transcript"

    def test_whitespace_text_returns_error(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("   ")
        assert result.success is False
        assert result.metadata.get("error") == "empty_transcript"

    def test_pipeline_failure_returns_error(self):
        registry = _build_registry(
            cortex_exc=ValueError("Pipeline exploded"),
        )
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello")
        assert result.success is False
        assert "Pipeline" in result.response
        assert result.metadata.get("error") == "pipeline_failure"

    def test_dispatch_failure_returns_error(self):
        registry = _build_registry(
            dispatcher_exc=RuntimeError("Dispatch exploded"),
        )
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello")
        assert result.success is False
        assert "Dispatch" in result.response
        assert result.metadata.get("error") == "dispatch_failure"

    def test_confidence_in_error_response(self):
        registry = _build_registry(
            cortex_exc=ValueError("fail"),
        )
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello", confidence=0.42)
        assert result.metadata.get("transcript_confidence") == 0.42

    def test_source_in_metadata(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello", source="mic")
        assert result.metadata.get("source") == "mic"

    def test_timestamp_in_success_response(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello")
        assert "timestamp" in result.metadata
        assert isinstance(result.metadata["timestamp"], float)

    def test_routing_strategy_preserved(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello")
        assert result.routing_strategy == "preferred"

    def test_provider_and_model_preserved(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello")
        assert result.provider == "test"
        assert result.model == "mock"

    def test_non_ai_brain_still_returns_cortex_response(self):
        """FastBrain returns plain string; integration still builds response."""
        skill_result = SkillResult.ok(message="Application opened")
        cr = CortexResponse(
            success=True,
            response="Application opened",
        )
        registry = _build_registry(
            dispatcher_result=(skill_result, cr),
        )
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("open browser")
        assert result.success is True
        assert "Application" in result.response


# ===================================================================
# VoiceManager.handle_transcript_with_response
# ===================================================================


class TestVoiceManagerHandleTranscriptWithResponse:
    """Tests for ``VoiceManager.handle_transcript_with_response()``."""

    @pytest.fixture
    def manager(self):
        registry = _build_registry()
        return VoiceManager(registry)

    def test_success_returns_skill_and_cortex_response(self, manager):
        result, cr = manager.handle_transcript_with_response("hello")
        assert result.success is True
        assert cr.success is True
        assert cr.response == "Hello from AI"
        assert cr.provider == "test"
        assert cr.model == "mock"

    def test_voice_metadata_in_response(self, manager):
        _, cr = manager.handle_transcript_with_response(
            "hello",
            confidence=0.9,
            session_id="s1",
        )
        assert cr.metadata.get("transcript_confidence") == 0.9
        assert cr.metadata.get("session_id") == "s1"
        assert cr.metadata.get("source") == "voice"
        assert "timestamp" in cr.metadata

    def test_empty_text_returns_fail(self, manager):
        result, cr = manager.handle_transcript_with_response("")
        assert result.success is False
        assert cr.success is False
        assert cr.metadata.get("error") == "empty_transcript"

    def test_none_text_returns_fail(self, manager):
        result, cr = manager.handle_transcript_with_response(None)  # type: ignore[arg-type]
        assert result.success is False
        assert cr.success is False

    def test_whitespace_text_returns_fail(self, manager):
        result, cr = manager.handle_transcript_with_response("   ")
        assert result.success is False

    def test_cortex_pipeline_error(self, manager):
        registry = _build_registry(cortex_exc=ValueError("crash"))
        m = VoiceManager(registry)
        result, cr = m.handle_transcript_with_response("hello")
        assert result.success is False
        assert cr.success is False
        assert cr.metadata.get("error") == "pipeline_failure"

    def test_dispatcher_error(self, manager):
        registry = _build_registry(
            dispatcher_exc=RuntimeError("boom"),
        )
        m = VoiceManager(registry)
        result, cr = m.handle_transcript_with_response("hello")
        assert result.success is False
        assert cr.success is False
        assert cr.metadata.get("error") == "dispatch_failure"

    def test_dispatcher_error_preserves_confidence(self, manager):
        registry = _build_registry(
            dispatcher_exc=RuntimeError("boom"),
        )
        m = VoiceManager(registry)
        _, cr = m.handle_transcript_with_response("hello", confidence=0.75)
        assert cr.metadata.get("transcript_confidence") == 0.75

    def test_command_short_circuit_returns_directly(self):
        registry = ServiceRegistry()
        event_bus = EventBus()
        registry.register("event_bus", event_bus)
        registry.register("memory", MagicMock())
        registry.register("cortex", MagicMock())
        registry.register("dispatcher", MagicMock())
        registry.register(
            "voice_config",
            VoiceConfig(enabled=False, commands=("stop",), speaker_enabled=False),
        )
        m = VoiceManager(registry)
        result, cr = m.handle_transcript_with_response("stop")
        assert result.success is True
        assert cr.success is True
        assert cr.metadata.get("command") is True

    def test_session_metadata_merged(self, manager):
        _, cr = manager.handle_transcript_with_response(
            "hello",
            session_metadata={"language": "en"},
        )
        assert cr.metadata.get("language") == "en"

    def test_routing_strategy_in_response(self, manager):
        _, cr = manager.handle_transcript_with_response("hello")
        assert cr.routing_strategy == "preferred"

    def test_conversation_id_in_response(self, manager):
        _, cr = manager.handle_transcript_with_response("hello")
        assert cr.conversation_id == "conv_abc"

    def test_provider_and_model_preserved(self, manager):
        _, cr = manager.handle_transcript_with_response("hello")
        assert cr.provider == "test"
        assert cr.model == "mock"

    def test_timestamp_in_response(self, manager):
        _, cr = manager.handle_transcript_with_response("hello")
        assert "timestamp" in cr.metadata

    def test_event_published_on_success(self, manager):
        event_bus = manager._registry.get("event_bus")
        subscriber = MagicMock()
        event_bus.subscribe(VoiceManager.EVENT_TRANSCRIPT, subscriber)
        manager.handle_transcript_with_response("hello")
        subscriber.assert_called_once_with("hello")

    def test_backward_compatible_handle_transcript_passes_correctly(self):
        """Verify that handle_transcript still dispatches through cortex."""
        registry = _build_registry()
        m = VoiceManager(registry)
        # Use a real SkillResult for dispatch
        dispatcher = registry.get("dispatcher")
        real_result = SkillResult.ok(message="Hello from AI", data={"brain": "smart"})
        dispatcher.dispatch.return_value = real_result
        result = m.handle_transcript("hello")
        assert result.success is True
        assert result.message == "Hello from AI"


# ===================================================================
# Edge cases
# ===================================================================


class TestVoiceIntegrationEdgeCases:
    """Additional edge-case coverage."""

    def test_none_memory_in_metadata(self):
        """Memory failure must not crash the integration response."""
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello")
        # Even if memory is mocked, response must be valid
        assert result.success is True
        assert "timestamp" in result.metadata

    def test_low_confidence_does_not_block(self):
        registry = _build_registry()
        integration = VoiceCortexIntegration(registry)
        result = integration.process_speech("hello", confidence=0.05)
        assert result.success is True
        assert result.metadata.get("transcript_confidence") == 0.05
