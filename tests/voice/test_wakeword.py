"""Tests for WakeWordDetector stub."""

from __future__ import annotations

import pytest

from app.voice.config import VoiceConfig
from app.voice.wakeword import WakeWordDetector


class TestWakeWordDetector:
    def test_disabled_by_default(self):
        detector = WakeWordDetector(VoiceConfig())
        assert detector.enabled is False
        assert detector.detect([0.5] * 480) is False

    def test_enabled_returns_false_below_threshold(self):
        cfg = VoiceConfig(
            wake_word_enabled=True,
            wake_word_energy_threshold=0.5,
        )
        detector = WakeWordDetector(cfg)
        assert detector.enabled is True
        assert detector.detect([0.1] * 480) is False

    def test_enabled_returns_true_above_threshold(self):
        cfg = VoiceConfig(
            wake_word_enabled=True,
            wake_word_energy_threshold=0.01,
        )
        detector = WakeWordDetector(cfg)
        assert detector.detect([0.5] * 480) is True

    def test_wake_word_string(self):
        cfg = VoiceConfig(wake_word="hey jarvis")
        detector = WakeWordDetector(cfg)
        assert detector.wake_word == "hey jarvis"

    def test_detect_with_none(self):
        cfg = VoiceConfig(wake_word_enabled=True, wake_word_energy_threshold=0.0)
        detector = WakeWordDetector(cfg)
        # None is treated as silence -> no detection
        assert detector.detect(None) is False
