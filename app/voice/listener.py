"""Microphone capture for the voice subsystem.

The listener is intentionally thin: it only knows how to record audio
to a WAV file. Decision logic (when to stop, whether the user spoke,
how long to wait) lives in higher-level components
(``SpeechRecognizer`` / ``VoiceManager``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
import soundfile as sf

from app.core.logger import JarvisLogger
from app.voice.config import VoiceConfig
from app.voice.vad import VoiceActivityDetector


class VoiceListener:
    """Capture audio from the default input device.

    Two modes are supported:

    * ``record()`` — fixed duration, no VAD. The original interface.
    * ``record_until_silence()`` — VAD-driven, stops when the speaker
      pauses for ``vad_silence_ms`` or when ``vad_max_seconds`` is hit.
    """

    def __init__(
        self,
        config: VoiceConfig | None = None,
        vad: VoiceActivityDetector | None = None,
    ) -> None:
        self._config = config or VoiceConfig()
        self._vad = vad or VoiceActivityDetector(self._config)
        self._logger = JarvisLogger

    # ------------------------------------------------------------------
    # Fixed-duration recording (legacy / fallback)
    # ------------------------------------------------------------------

    def record(
        self,
        filename: str = "temp.wav",
        seconds: int | None = None,
        sample_rate: int | None = None,
    ) -> str:
        """Record a fixed-duration clip and return the WAV path.

        Parameters
        ----------
        filename:
            Output WAV path. Relative paths are resolved against CWD.
        seconds:
            Recording length. Defaults to ``config.record_seconds``.
        sample_rate:
            Capture rate. Defaults to ``config.sample_rate``.
        """
        seconds = seconds or self._config.record_seconds
        sample_rate = sample_rate or self._config.sample_rate

        self._logger.info("Listening (fixed %ss)...", seconds)

        audio = sd.rec(
            int(seconds * sample_rate),
            samplerate=sample_rate,
            channels=self._config.channels,
            dtype=self._config.dtype,
        )
        sd.wait()

        path = self._resolve_path(filename)
        sf.write(str(path), audio, sample_rate)

        self._logger.info("Recording finished: %s", path)
        return str(path)

    # ------------------------------------------------------------------
    # VAD-driven recording
    # ------------------------------------------------------------------

    def record_until_silence(
        self,
        filename: str = "vad_capture.wav",
        sample_rate: int | None = None,
        max_seconds: int | None = None,
        silence_ms: int | None = None,
    ) -> str | None:
        """Record until the speaker is silent, or ``max_seconds`` elapses.

        Returns the WAV path, or ``None`` if no speech was detected
        before the timeout. The first speech frame is captured too —
        it would be lost if we waited for silence before starting.
        """
        sample_rate = sample_rate or self._config.sample_rate
        max_seconds = max_seconds or self._config.vad_max_seconds
        silence_ms = silence_ms or self._config.vad_silence_ms
        frame_size = self._vad.frame_size

        if frame_size <= 0:
            raise ValueError("vad_frame_duration_ms produces non-positive frame size")

        max_frames = int((max_seconds * sample_rate) / frame_size)
        silence_threshold_frames = int(
            (silence_ms * sample_rate) / (frame_size * 1000)
        )

        self._logger.info("Listening (VAD, max %ss)...", max_seconds)

        chunks: list[Any] = []
        speech_started = False
        silence_frames = 0
        total_frames = 0

        with sd.InputStream(
            samplerate=sample_rate,
            channels=self._config.channels,
            dtype=self._config.dtype,
            blocksize=frame_size,
        ) as stream:
            for _ in range(max_frames):
                frame, _ = stream.read(frame_size)
                total_frames += 1

                if self._vad.is_speech(frame):
                    chunks.append(frame)
                    speech_started = True
                    silence_frames = 0
                    continue

                if speech_started:
                    chunks.append(frame)
                    silence_frames += 1
                    if silence_frames >= silence_threshold_frames:
                        break
                # else: pre-speech silence — drop frame

        if not speech_started:
            self._logger.info("No speech detected before timeout")
            return None

        audio = np.concatenate(chunks, axis=0)

        path = self._resolve_path(filename)
        sf.write(str(path), audio, sample_rate)

        self._logger.info(
            "VAD capture finished: %s (%.2fs captured)",
            path,
            total_frames * frame_size / sample_rate,
        )
        return str(path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(filename: str) -> Path:
        path = Path(filename)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
