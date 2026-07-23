"""Tests for VoiceListener (audio capture)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.voice.config import VoiceConfig
from app.voice.listener import VoiceListener


class TestVoiceListener:
    @pytest.fixture
    def listener(self):
        return VoiceListener(VoiceConfig(vad_max_seconds=2, vad_silence_ms=200))

    def test_record_creates_wav(self, listener, tmp_path):
        # Mock sounddevice and soundfile
        with patch("app.voice.listener.sd") as mock_sd, \
             patch("app.voice.listener.sf") as mock_sf:
            mock_sd.rec.return_value = MagicMock()
            mock_sd.wait.return_value = None

            out_path = listener.record(
                filename=str(tmp_path / "out.wav"),
                seconds=1,
                sample_rate=16000,
            )

        assert out_path == str(tmp_path / "out.wav")
        mock_sd.rec.assert_called_once()
        mock_sd.wait.assert_called_once()
        mock_sf.write.assert_called_once()

    def test_record_uses_default_seconds(self, listener, tmp_path):
        with patch("app.voice.listener.sd") as mock_sd, \
             patch("app.voice.listener.sf") as mock_sf:
            mock_sd.rec.return_value = MagicMock()

            listener.record(filename=str(tmp_path / "default.wav"))

        # sample_rate=16000, record_seconds=5 (config default) -> 80000 frames
        args, kwargs = mock_sd.rec.call_args
        assert args[0] == 5 * 16000
        assert kwargs["samplerate"] == 16000

    def test_record_uses_default_sample_rate(self, listener, tmp_path):
        cfg = VoiceConfig(sample_rate=8000, record_seconds=1)
        listener_custom = VoiceListener(cfg)
        with patch("app.voice.listener.sd") as mock_sd, \
             patch("app.voice.listener.sf") as mock_sf:
            mock_sd.rec.return_value = MagicMock()
            listener_custom.record(filename=str(tmp_path / "x.wav"))
        args, kwargs = mock_sd.rec.call_args
        assert args[0] == 1 * 8000
        assert kwargs["samplerate"] == 8000

    def test_record_until_silence_returns_none_when_no_speech(self, listener):
        """When every frame is silence, no file is written."""
        # Force VAD to consider every frame non-speech.
        listener._vad.is_speech = MagicMock(return_value=False)

        with patch("app.voice.listener.sd") as mock_sd, \
             patch("app.voice.listener.sf") as mock_sf:
            # Build a fake InputStream context manager
            fake_stream = MagicMock()
            fake_stream.read.return_value = (MagicMock(), None)
            mock_sd.InputStream.return_value.__enter__.return_value = fake_stream

            result = listener.record_until_silence(filename="never.wav")

        assert result is None
        mock_sf.write.assert_not_called()

    def test_record_until_silence_writes_file_on_speech(self, listener, tmp_path):
        """When speech is followed by silence, a WAV is written."""
        # Two speech chunks then enough silence chunks to stop the loop.
        is_speech_side_effects = [True, True] + [False] * 10
        listener._vad.is_speech = MagicMock(side_effect=is_speech_side_effects)

        with patch("app.voice.listener.sd") as mock_sd, \
             patch("app.voice.listener.sf") as mock_sf, \
             patch("app.voice.listener.np") as mock_np:
            fake_stream = MagicMock()
            fake_stream.read.return_value = (MagicMock(), None)
            mock_sd.InputStream.return_value.__enter__.return_value = fake_stream

            mock_np.concatenate.return_value = MagicMock()

            out_path = listener.record_until_silence(
                filename=str(tmp_path / "out.wav"),
                max_seconds=5,
                silence_ms=200,
            )

        assert out_path == str(tmp_path / "out.wav")
        mock_sf.write.assert_called_once()

    def test_resolve_path_creates_parent_dirs(self, listener, tmp_path):
        target = tmp_path / "subdir" / "out.wav"
        path = listener._resolve_path(str(target))
        assert path == target
        assert target.parent.exists()

    def test_resolve_path_keeps_absolute(self, tmp_path):
        listener = VoiceListener(VoiceConfig())
        target = tmp_path / "abs.wav"
        path = listener._resolve_path(str(target))
        assert path == target
