from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class VoiceConfig:
    """Centralised configuration for the voice subsystem.

    All defaults are chosen so the subsystem is *off* in headless or
    test environments. Flip ``enabled`` to True on a real machine.
    """

    # Master switch
    enabled: bool = False

    # Capture
    sample_rate: int = 16000
    channels: int = 1
    record_seconds: int = 5
    dtype: str = "float32"

    # Whisper
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    language: str = "en"

    # Wake word (stub by default)
    wake_word_enabled: bool = False
    wake_word: str = "jarvis"
    wake_word_energy_threshold: float = 0.02

    # Voice activity detection
    vad_enabled: bool = False
    vad_energy_threshold: float = 0.01
    vad_frame_duration_ms: int = 30
    vad_silence_ms: int = 700
    vad_max_seconds: int = 15

    # Session control commands (empty by default)
    commands: tuple[str, ...] = ()

    # Output (TTS is a stub for now)
    speaker_enabled: bool = False

    # Background loop
    loop_pause_seconds: float = 0.5
