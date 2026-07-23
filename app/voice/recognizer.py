"""Speech-to-text facade.

Combines :class:`VoiceListener` and :class:`WhisperProvider` into one
callable surface. Optional VAD-driven capture is supported; the fixed
``record()`` path is preserved as a fallback.
"""

from __future__ import annotations

from typing import Optional

from app.core.logger import JarvisLogger
from app.voice.config import VoiceConfig
from app.voice.listener import VoiceListener
from app.voice.providers.whisper_provider import WhisperProvider
from app.voice.vad import VoiceActivityDetector


class SpeechRecognizer:
    """One-stop shop for "mic → text".

    Construction is lazy with respect to the Whisper model: it is only
    loaded the first time ``listen_and_transcribe()`` (or
    ``transcribe_file()``) is called, so importing this module in
    tests does not trigger a model download.
    """

    def __init__(
        self,
        config: VoiceConfig | None = None,
        listener: VoiceListener | None = None,
        whisper: WhisperProvider | None = None,
        vad: VoiceActivityDetector | None = None,
    ) -> None:
        self._config = config or VoiceConfig()
        self._listener = listener or VoiceListener(self._config, vad)
        self._whisper = whisper  # lazy
        self._vad = vad or VoiceActivityDetector(self._config)
        self._logger = JarvisLogger

    # ------------------------------------------------------------------
    # Whisper lazy loader
    # ------------------------------------------------------------------

    def _ensure_whisper(self) -> WhisperProvider:
        if self._whisper is None:
            self._whisper = WhisperProvider(
                model_name=self._config.whisper_model,
                device=self._config.whisper_device,
                compute_type=self._config.whisper_compute_type,
            )
        return self._whisper

    def set_whisper(self, whisper: WhisperProvider) -> None:
        """Inject a pre-built WhisperProvider (useful for tests)."""
        self._whisper = whisper

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe_file(self, audio_path: str) -> str:
        """Transcribe a WAV file. Returns an empty string on failure."""
        try:
            whisper = self._ensure_whisper()
            return whisper.transcribe(audio_path).strip()
        except Exception as exc:  # noqa: BLE001 — surface to caller via empty string
            self._logger.error("Transcription failed: %s", exc)
            return ""

    def listen_and_transcribe(self) -> Optional[str]:
        """Capture audio (VAD or fixed) and return the transcript.

        Returns ``None`` if no speech was captured.
        """
        if self._config.vad_enabled:
            audio_path = self._listener.record_until_silence()
        else:
            audio_path = self._listener.record(
                seconds=self._config.record_seconds,
                sample_rate=self._config.sample_rate,
            )

        if not audio_path:
            return None

        text = self.transcribe_file(audio_path)
        if not text:
            return None

        self._logger.info("Transcript: %s", text)
        return text
