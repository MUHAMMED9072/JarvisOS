from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request, UploadFile

from app.api.dependencies import get_service, require_service
from app.api.errors import BadRequestError, ServiceUnavailableError
from app.api.schemas import (
    VoiceListenActionResponse,
    VoiceProcessRequest,
    VoiceProcessResponse,
    VoiceProviderInfo,
    VoiceProviderListResponse,
    VoiceStatusResponse,
    VoiceTranscribeResponse,
)
from app.core.registry import ServiceRegistry
from app.voice.config import VoiceConfig
from app.voice.integration import VoiceCortexIntegration
from app.voice.manager import VoiceManager

router = APIRouter(prefix="/api/v1/voice", tags=["Voice"])

VOICE_MGR = Depends(require_service("voice_manager"))
VOICE_INTEGRATION = Depends(require_service("voice_integration"))


def _get_voice_config(request: Request) -> VoiceConfig:
    registry: ServiceRegistry | None = getattr(request.app.state, "registry", None)
    if registry is not None:
        cfg = registry.get_optional("voice_config")
        if isinstance(cfg, VoiceConfig):
            return cfg
    return VoiceConfig()


# ------------------------------------------------------------------
# Transcribe audio file to text
# ------------------------------------------------------------------


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_audio(
    request: Request,
    file: UploadFile,
) -> VoiceTranscribeResponse:
    if not file.filename:
        raise BadRequestError("No audio file provided")

    from app.voice.recognizer import SpeechRecognizer

    config = _get_voice_config(request)
    recognizer = SpeechRecognizer(config)

    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from app.voice.providers.whisper_provider import WhisperProvider

        whisper = WhisperProvider(
            model_name=config.whisper_model,
            device=config.whisper_device,
            compute_type=config.whisper_compute_type,
        )
        recognizer.set_whisper(whisper)
        text = recognizer.transcribe_file(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not text:
        raise BadRequestError("Transcription failed or returned empty text")

    return VoiceTranscribeResponse(
        text=text,
        confidence=0.0,
        language=config.language,
        duration_ms=0.0,
    )


# ------------------------------------------------------------------
# Process text through the voice pipeline
# ------------------------------------------------------------------


@router.post("/process", response_model=VoiceProcessResponse)
async def process_speech(
    body: VoiceProcessRequest,
    integration: VoiceCortexIntegration = VOICE_INTEGRATION,
) -> VoiceProcessResponse:
    result = integration.process_speech(
        text=body.text,
        confidence=body.confidence,
        session_id=body.session_id,
        source="api",
        session_metadata=body.session_metadata,
    )
    return VoiceProcessResponse(
        success=result.success,
        response=result.response,
        provider=result.provider,
        model=result.model,
        conversation_id=result.conversation_id,
        routing_strategy=result.routing_strategy,
        metadata=dict(result.metadata),
    )


# ------------------------------------------------------------------
# Start background listening
# ------------------------------------------------------------------


@router.post("/listen/start", response_model=VoiceListenActionResponse)
async def listen_start(
    vm: VoiceManager = VOICE_MGR,
) -> VoiceListenActionResponse:
    vm.start()
    return VoiceListenActionResponse(
        status="ok",
        message="Voice listening started",
    )


# ------------------------------------------------------------------
# Stop background listening
# ------------------------------------------------------------------


@router.post("/listen/stop", response_model=VoiceListenActionResponse)
async def listen_stop(
    vm: VoiceManager = VOICE_MGR,
) -> VoiceListenActionResponse:
    vm.stop()
    return VoiceListenActionResponse(
        status="ok",
        message="Voice listening stopped",
    )


# ------------------------------------------------------------------
# Voice subsystem status
# ------------------------------------------------------------------


@router.get("/status", response_model=VoiceStatusResponse)
async def voice_status(
    request: Request,
    vm: VoiceManager = VOICE_MGR,
) -> VoiceStatusResponse:
    config = _get_voice_config(request)
    return VoiceStatusResponse(
        running=vm.is_running(),
        enabled=config.enabled,
        speaker_enabled=config.speaker_enabled,
        wake_word_enabled=config.wake_word_enabled,
        vad_enabled=config.vad_enabled,
        whisper_model=config.whisper_model,
        language=config.language,
        sample_rate=config.sample_rate,
        record_seconds=config.record_seconds,
    )


# ------------------------------------------------------------------
# List voice providers
# ------------------------------------------------------------------


@router.get("/providers", response_model=VoiceProviderListResponse)
async def voice_providers(
    request: Request,
) -> VoiceProviderListResponse:
    config = _get_voice_config(request)
    providers: list[VoiceProviderInfo] = [
        VoiceProviderInfo(
            name="whisper",
            type="stt",
            available=True,
            description="Whisper speech-to-text provider",
            config={
                "model": config.whisper_model,
                "device": config.whisper_device,
                "compute_type": config.whisper_compute_type,
                "language": config.language,
            },
        ),
        VoiceProviderInfo(
            name="speaker",
            type="tts",
            available=config.speaker_enabled,
            description="Text-to-speech speaker (stub)",
            config={
                "enabled": config.speaker_enabled,
            },
        ),
        VoiceProviderInfo(
            name="listener",
            type="capture",
            available=True,
            description="Microphone audio capture",
            config={
                "sample_rate": config.sample_rate,
                "channels": config.channels,
                "record_seconds": config.record_seconds,
                "vad_enabled": config.vad_enabled,
                "wake_word_enabled": config.wake_word_enabled,
            },
        ),
    ]
    return VoiceProviderListResponse(providers=providers)
