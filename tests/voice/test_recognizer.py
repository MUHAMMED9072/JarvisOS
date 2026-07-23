"""Tests for SpeechRecognizer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.voice.config import VoiceConfig
from app.voice.recognizer import SpeechRecognizer


class TestSpeechRecognizer:
    def test_transcribe_file_strips_whitespace(self):
        recognizer = SpeechRecognizer(VoiceConfig())
        whisper = MagicMock()
        whisper.transcribe.return_value = "  hello world  "
        recognizer.set_whisper(whisper)

        result = recognizer.transcribe_file("dummy.wav")

        assert result == "hello world"
        whisper.transcribe.assert_called_once_with("dummy.wav")

    def test_transcribe_file_returns_empty_on_failure(self):
        recognizer = SpeechRecognizer(VoiceConfig())
        whisper = MagicMock()
        whisper.transcribe.side_effect = RuntimeError("boom")
        recognizer.set_whisper(whisper)

        result = recognizer.transcribe_file("dummy.wav")

        assert result == ""

    def test_ensure_whisper_lazy_loads(self):
        cfg = VoiceConfig(whisper_model="tiny")
        recognizer = SpeechRecognizer(cfg)
        assert recognizer._whisper is None

        with patch("app.voice.recognizer.WhisperProvider") as mock_cls:
            mock_cls.return_value = MagicMock()
            recognizer._ensure_whisper()
        mock_cls.assert_called_once_with(
            model_name="tiny", device="cpu", compute_type="int8"
        )

    def test_ensure_whisper_caches(self):
        recognizer = SpeechRecognizer(VoiceConfig())
        whisper = MagicMock()
        recognizer.set_whisper(whisper)

        with patch("app.voice.recognizer.WhisperProvider") as mock_cls:
            recognizer._ensure_whisper()
        mock_cls.assert_not_called()
        assert recognizer._whisper is whisper

    def test_listen_and_transcribe_fixed_mode(self):
        cfg = VoiceConfig(vad_enabled=False, record_seconds=1)
        recognizer = SpeechRecognizer(cfg)
        recognizer.set_whisper(MagicMock(transcribe=lambda p: "hi there"))

        with patch.object(recognizer._listener, "record", return_value="/tmp/a.wav") as mock_rec, \
             patch.object(recognizer._listener, "record_until_silence") as mock_vad:
            text = recognizer.listen_and_transcribe()

        assert text == "hi there"
        mock_rec.assert_called_once()
        mock_vad.assert_not_called()

    def test_listen_and_transcribe_vad_mode(self):
        cfg = VoiceConfig(vad_enabled=True)
        recognizer = SpeechRecognizer(cfg)
        recognizer.set_whisper(MagicMock(transcribe=lambda p: "from vad"))

        with patch.object(recognizer._listener, "record") as mock_rec, \
             patch.object(recognizer._listener, "record_until_silence", return_value="/tmp/v.wav") as mock_vad:
            text = recognizer.listen_and_transcribe()

        assert text == "from vad"
        mock_vad.assert_called_once()
        mock_rec.assert_not_called()

    def test_listen_and_transcribe_returns_none_when_no_audio(self):
        recognizer = SpeechRecognizer(VoiceConfig())
        with patch.object(recognizer._listener, "record", return_value=None):
            assert recognizer.listen_and_transcribe() is None

    def test_listen_and_transcribe_returns_none_on_empty_transcript(self):
        recognizer = SpeechRecognizer(VoiceConfig())
        recognizer.set_whisper(MagicMock(transcribe=lambda p: ""))
        with patch.object(recognizer._listener, "record", return_value="/tmp/a.wav"):
            assert recognizer.listen_and_transcribe() is None
