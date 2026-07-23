"""Energy-based Voice Activity Detection.

This is a deliberately minimal stub. It computes the RMS energy of an
audio frame and compares it to a threshold. It does **not** require
``webrtcvad`` or any model file.

Replace with ``webrtcvad`` / ``silero-vad`` when production accuracy
matters. The public API (``is_speech``) is stable, so the swap is
local to this module.
"""

from __future__ import annotations

import math
from typing import Any

from app.voice.config import VoiceConfig


class VoiceActivityDetector:
    """Frame-level VAD.

    A frame is any 1-D iterable of numeric samples. The detector is
    intentionally permissive — false positives are far cheaper than
    false negatives in a voice-orchestration context.
    """

    def __init__(self, config: VoiceConfig | None = None) -> None:
        self._config = config or VoiceConfig()

    @property
    def frame_size(self) -> int:
        """Number of samples per analysis frame."""
        return int(
            self._config.sample_rate
            * self._config.vad_frame_duration_ms
            / 1000
        )

    @property
    def threshold(self) -> float:
        return self._config.vad_energy_threshold

    def rms(self, frame: Any) -> float:
        """Root-mean-square energy of a frame.

        Accepts any iterable of numbers. Avoids requiring ``numpy``
        in the public API even though ``sounddevice`` produces numpy
        arrays internally.
        """
        if frame is None:
            return 0.0

        # numpy fast-path
        if hasattr(frame, "astype") and hasattr(frame, "mean"):
            try:
                squared = frame.astype("float64") ** 2
                return math.sqrt(float(squared.mean()))
            except Exception:
                pass

        # Pure-Python fallback
        total = 0.0
        count = 0
        for sample in frame:
            try:
                value = float(sample)
            except (TypeError, ValueError):
                continue
            total += value * value
            count += 1

        if count == 0:
            return 0.0

        return math.sqrt(total / count)

    def is_speech(self, frame: Any) -> bool:
        """Return True if the frame's energy exceeds the threshold."""
        return self.rms(frame) > self.threshold
