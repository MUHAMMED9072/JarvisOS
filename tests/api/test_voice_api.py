"""Tests for the Voice REST API (P11-05)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas import (
    VoiceListenActionResponse,
    VoiceProcessResponse,
    VoiceProviderListResponse,
    VoiceStatusResponse,
    VoiceTranscribeResponse,
)
from app.api.server import create_app
from app.core.registry import ServiceRegistry
from app.voice.config import VoiceConfig


# ==========================================================================
# Helpers
# ==========================================================================


def _make_app(
    registry: ServiceRegistry | None = None,
    voice_manager=None,
    voice_integration=None,
    voice_config: VoiceConfig | None = None,
) -> FastAPI:
    if registry is None:
        registry = ServiceRegistry()
    if voice_manager is not None:
        registry.register("voice_manager", voice_manager)
    if voice_integration is not None:
        registry.register("voice_integration", voice_integration)
    if voice_config is not None:
        registry.register("voice_config", voice_config)
    registry.register("dispatcher", MagicMock())
    registry.register("memory", MagicMock())
    registry.register("event_bus", MagicMock())
    registry.register("cortex", MagicMock())
    return create_app(registry)


def _make_client(
    registry: ServiceRegistry | None = None,
    voice_manager=None,
    voice_integration=None,
    voice_config: VoiceConfig | None = None,
) -> TestClient:
    app = _make_app(registry, voice_manager, voice_integration, voice_config)
    return TestClient(app)


# ==========================================================================
# Route registration
# ==========================================================================


class TestVoiceRouteRegistration:
    """Voice routes appear in OpenAPI schema."""

    def test_voice_routes_in_openapi(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/voice/transcribe" in paths
        assert "/api/v1/voice/process" in paths
        assert "/api/v1/voice/listen/start" in paths
        assert "/api/v1/voice/listen/stop" in paths
        assert "/api/v1/voice/status" in paths
        assert "/api/v1/voice/providers" in paths


# ==========================================================================
# Transcription
# ==========================================================================


class TestTranscribe:
    """POST /api/v1/voice/transcribe"""

    @patch("app.voice.recognizer.SpeechRecognizer")
    @patch("app.voice.providers.whisper_provider.WhisperProvider")
    def test_transcribe_success(self, mock_whisper_cls, mock_recognizer_cls):
        mock_recognizer = MagicMock()
        mock_recognizer.transcribe_file.return_value = "hello world"
        mock_recognizer_cls.return_value = mock_recognizer
        mock_whisper_cls.return_value = MagicMock()

        vi = MagicMock()
        vm = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post(
            "/api/v1/voice/transcribe",
            files={"file": ("test.wav", b"fake audio data")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "hello world"
        assert "confidence" in data
        assert "language" in data

    @patch("app.voice.recognizer.SpeechRecognizer")
    @patch("app.voice.providers.whisper_provider.WhisperProvider")
    def test_transcribe_empty_result(self, mock_whisper_cls, mock_recognizer_cls):
        mock_recognizer = MagicMock()
        mock_recognizer.transcribe_file.return_value = ""
        mock_recognizer_cls.return_value = mock_recognizer
        mock_whisper_cls.return_value = MagicMock()

        vi = MagicMock()
        vm = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post(
            "/api/v1/voice/transcribe",
            files={"file": ("test.wav", b"silence")},
        )
        assert resp.status_code == 400

    def test_transcribe_no_file_returns_422(self):
        vi = MagicMock()
        vm = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post("/api/v1/voice/transcribe")
        assert resp.status_code == 422

    def test_transcribe_empty_filename_returns_422(self):
        vi = MagicMock()
        vm = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post(
            "/api/v1/voice/transcribe",
            files={"file": ("", b"data")},
        )
        assert resp.status_code == 422

    @patch("app.voice.recognizer.SpeechRecognizer")
    @patch("app.voice.providers.whisper_provider.WhisperProvider")
    def test_transcribe_uses_custom_config(self, mock_whisper_cls, mock_recognizer_cls):
        mock_recognizer = MagicMock()
        mock_recognizer.transcribe_file.return_value = "transcribed"
        mock_recognizer_cls.return_value = mock_recognizer
        mock_whisper_cls.return_value = MagicMock()

        config = VoiceConfig(language="fr", whisper_model="large")
        vi = MagicMock()
        vm = MagicMock()
        client = _make_client(
            voice_manager=vm, voice_integration=vi, voice_config=config,
        )
        resp = client.post(
            "/api/v1/voice/transcribe",
            files={"file": ("test.wav", b"audio data")},
        )
        assert resp.status_code == 200
        assert resp.json()["language"] == "fr"


# ==========================================================================
# Processing
# ==========================================================================


class TestProcess:
    """POST /api/v1/voice/process"""

    def test_process_success(self):
        integration = MagicMock()
        result = MagicMock()
        result.success = True
        result.response = "processed response"
        result.provider = "test_provider"
        result.model = "test_model"
        result.conversation_id = "conv_123"
        result.routing_strategy = "smart"
        result.metadata = {"source": "api", "confidence": 0.95}
        integration.process_speech.return_value = result

        vm = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=integration)
        resp = client.post(
            "/api/v1/voice/process",
            json={
                "text": "hello",
                "confidence": 0.95,
                "session_id": "sess_1",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["response"] == "processed response"
        assert data["provider"] == "test_provider"
        assert data["conversation_id"] == "conv_123"
        assert data["metadata"]["confidence"] == 0.95

    def test_process_failure(self):
        integration = MagicMock()
        result = MagicMock()
        result.success = False
        result.response = "Processing failed"
        result.provider = ""
        result.model = ""
        result.conversation_id = ""
        result.routing_strategy = ""
        result.metadata = {"error": "pipeline_failure"}
        integration.process_speech.return_value = result

        vm = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=integration)
        resp = client.post(
            "/api/v1/voice/process",
            json={"text": "hello"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["metadata"]["error"] == "pipeline_failure"

    def test_process_empty_text(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post(
            "/api/v1/voice/process",
            json={"text": ""},
        )
        assert resp.status_code == 422

    def test_process_missing_text(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post("/api/v1/voice/process", json={})
        assert resp.status_code == 422

    def test_process_invalid_confidence(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post(
            "/api/v1/voice/process",
            json={"text": "hi", "confidence": 2.5},
        )
        assert resp.status_code == 422

    def test_process_with_session_metadata(self):
        integration = MagicMock()
        result = MagicMock()
        result.success = True
        result.response = "ok"
        result.provider = ""
        result.model = ""
        result.conversation_id = ""
        result.routing_strategy = ""
        result.metadata = {"custom": "value"}
        integration.process_speech.return_value = result

        vm = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=integration)
        resp = client.post(
            "/api/v1/voice/process",
            json={
                "text": "hello",
                "session_metadata": {"custom_key": "custom_val"},
            },
        )
        assert resp.status_code == 200
        integration.process_speech.assert_called_once()
        kwargs = integration.process_speech.call_args[1]
        assert kwargs["session_metadata"] == {"custom_key": "custom_val"}
        assert kwargs["source"] == "api"


# ==========================================================================
# Listen start/stop
# ==========================================================================


class TestListenStart:
    """POST /api/v1/voice/listen/start"""

    def test_start_success(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post("/api/v1/voice/listen/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "started" in data["message"]
        vm.start.assert_called_once()

    def test_start_idempotent(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post("/api/v1/voice/listen/start")
        assert resp.status_code == 200


class TestListenStop:
    """POST /api/v1/voice/listen/stop"""

    def test_stop_success(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post("/api/v1/voice/listen/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "stopped" in data["message"]
        vm.stop.assert_called_once()

    def test_stop_idempotent(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post("/api/v1/voice/listen/stop")
        assert resp.status_code == 200


# ==========================================================================
# Status
# ==========================================================================


class TestStatus:
    """GET /api/v1/voice/status"""

    def test_status_running(self):
        vm = MagicMock()
        vm.is_running.return_value = True
        vi = MagicMock()
        config = VoiceConfig(
            enabled=True,
            speaker_enabled=True,
            wake_word_enabled=True,
            vad_enabled=True,
            whisper_model="large",
            language="fr",
            sample_rate=44100,
            record_seconds=10,
        )
        client = _make_client(
            voice_manager=vm, voice_integration=vi, voice_config=config,
        )
        resp = client.get("/api/v1/voice/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["enabled"] is True
        assert data["speaker_enabled"] is True
        assert data["wake_word_enabled"] is True
        assert data["vad_enabled"] is True
        assert data["whisper_model"] == "large"
        assert data["language"] == "fr"
        assert data["sample_rate"] == 44100
        assert data["record_seconds"] == 10

    def test_status_stopped(self):
        vm = MagicMock()
        vm.is_running.return_value = False
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.get("/api/v1/voice/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is False
        assert data["enabled"] is False

    def test_status_all_defaults(self):
        vm = MagicMock()
        vm.is_running.return_value = False
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.get("/api/v1/voice/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["whisper_model"] == "base"
        assert data["sample_rate"] == 16000
        assert data["record_seconds"] == 5

    def test_response_shape(self):
        vm = MagicMock()
        vm.is_running.return_value = False
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.get("/api/v1/voice/status")
        data = resp.json()
        for field in (
            "running", "enabled", "speaker_enabled",
            "wake_word_enabled", "vad_enabled", "whisper_model",
            "language", "sample_rate", "record_seconds",
        ):
            assert field in data, f"Missing field: {field}"


# ==========================================================================
# Providers
# ==========================================================================


class TestProviders:
    """GET /api/v1/voice/providers"""

    def test_providers_list(self):
        vm = MagicMock()
        vi = MagicMock()
        config = VoiceConfig(
            whisper_model="large",
            speaker_enabled=True,
            vad_enabled=True,
            wake_word_enabled=True,
        )
        client = _make_client(
            voice_manager=vm, voice_integration=vi, voice_config=config,
        )
        resp = client.get("/api/v1/voice/providers")
        assert resp.status_code == 200
        data = resp.json()
        names = [p["name"] for p in data["providers"]]
        assert "whisper" in names
        assert "speaker" in names
        assert "listener" in names

    def test_provider_details(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.get("/api/v1/voice/providers")
        assert resp.status_code == 200
        data = resp.json()
        for p in data["providers"]:
            assert "name" in p
            assert "type" in p
            assert "available" in p
            assert "description" in p
            assert "config" in p

    def test_speaker_unavailable_when_disabled(self):
        vm = MagicMock()
        vi = MagicMock()
        config = VoiceConfig(speaker_enabled=False)
        client = _make_client(
            voice_manager=vm, voice_integration=vi, voice_config=config,
        )
        resp = client.get("/api/v1/voice/providers")
        data = resp.json()
        speaker = next(p for p in data["providers"] if p["name"] == "speaker")
        assert speaker["available"] is False


# ==========================================================================
# Error handling
# ==========================================================================


class TestVoiceErrorHandling:
    """Proper error status codes for voice endpoints."""

    def test_service_unavailable_no_voice_manager(self):
        registry = ServiceRegistry()
        registry.register("dispatcher", MagicMock())
        registry.register("memory", MagicMock())
        registry.register("event_bus", MagicMock())
        registry.register("cortex", MagicMock())
        client = TestClient(create_app(registry))
        resp = client.get("/api/v1/voice/status")
        assert resp.status_code == 503

    def test_service_unavailable_no_integration(self):
        vm = MagicMock()
        registry = ServiceRegistry()
        registry.register("voice_manager", vm)
        registry.register("dispatcher", MagicMock())
        registry.register("memory", MagicMock())
        registry.register("event_bus", MagicMock())
        registry.register("cortex", MagicMock())
        client = TestClient(create_app(registry))
        resp = client.post(
            "/api/v1/voice/process",
            json={"text": "hello"},
        )
        assert resp.status_code == 503

    def test_validation_error_on_missing_text(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post("/api/v1/voice/process", json={})
        assert resp.status_code == 422


# ==========================================================================
# Response model shapes
# ==========================================================================


class TestVoiceResponseShapes:
    """Verify response payloads match expected Pydantic models."""

    @patch("app.voice.recognizer.SpeechRecognizer")
    @patch("app.voice.providers.whisper_provider.WhisperProvider")
    def test_transcribe_response_shape(self, mock_whisper_cls, mock_recognizer_cls):
        mock_recognizer = MagicMock()
        mock_recognizer.transcribe_file.return_value = "hello"
        mock_recognizer_cls.return_value = mock_recognizer
        mock_whisper_cls.return_value = MagicMock()

        vi = MagicMock()
        vm = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post(
            "/api/v1/voice/transcribe",
            files={"file": ("test.wav", b"data")},
        )
        data = resp.json()
        for field in ("text", "confidence", "language", "duration_ms"):
            assert field in data, f"Missing field: {field}"

    def test_process_response_shape(self):
        integration = MagicMock()
        result = MagicMock()
        result.success = True
        result.response = "ok"
        result.provider = ""
        result.model = ""
        result.conversation_id = ""
        result.routing_strategy = ""
        result.metadata = {}
        integration.process_speech.return_value = result

        vm = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=integration)
        resp = client.post(
            "/api/v1/voice/process",
            json={"text": "hello"},
        )
        data = resp.json()
        for field in (
            "success", "response", "provider", "model",
            "conversation_id", "routing_strategy", "metadata",
        ):
            assert field in data, f"Missing field: {field}"

    def test_listen_action_response_shape(self):
        vm = MagicMock()
        vi = MagicMock()
        client = _make_client(voice_manager=vm, voice_integration=vi)
        resp = client.post("/api/v1/voice/listen/start")
        data = resp.json()
        for field in ("status", "message"):
            assert field in data, f"Missing field: {field}"
