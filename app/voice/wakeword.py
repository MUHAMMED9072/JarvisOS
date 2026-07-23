"""Wake-word detection stub.

The shipped implementation is an energy-threshold placeholder. It does
**not** perform real word recognition. Swap in ``pvporcupine`` or
``openwakeword`` when ready — the public API
(``detect(frame) -> bool``) is stable.
"""

from __future__ import annotations

from typing import Any

from app.core.logger import JarvisLogger
from app.voice.config import VoiceConfig
from app.voice.vad import VoiceActivityDetector


class WakeWordDetector:
    """Energy-threshold wake-word stub.

    Returns True when the energy of an incoming frame exceeds a
    configurable threshold AND ``wake_word_enabled`` is on. This is a
    placeholder, not a real keyword spotter.
    """

    def __init__(
        self,
        config: VoiceConfig | None = None,
        vad: VoiceActivityDetector | None = None,
    ) -> None:
        self._config = config or VoiceConfig()
        self._vad = vad or VoiceActivityDetector(self._config)
        self._logger = JarvisLogger

    @property
    def enabled(self) -> bool:
        return self._config.wake_word_enabled

    @property
    def wake_word(self) -> str:
        return self._config.wake_word

    def detect(self, frame: Any) -> bool:
        """Return True if a wake word is detected in ``frame``.

        The stub fires whenever energy exceeds
        ``wake_word_energy_threshold`` while the detector is enabled.
        """
        if not self.enabled:
            return False

        energy = self._vad.rms(frame)
        if energy > self._config.wake_word_energy_threshold:
            self._logger.info("Wake word candidate (energy=%.4f)", energy)
            return True

        return False
