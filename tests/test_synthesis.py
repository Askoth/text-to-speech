"""
tests/test_synthesis.py
Tests for the voice synthesis functions: Piper TTS.
"""

import io
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import PiperVoices, Voice
from src.synthesis import download_piper_voice, synthesize_piper


def _registry(tmp_path: Path, existing: tuple[str, ...] = ()) -> PiperVoices:
    """'paola' registry with model/json under tmp_path (create files in existing)."""
    with patch("src.config.VOICE_DIR", tmp_path):
        voice = Voice(
            name="paola",
            gender="F",
            lang="it",
            multilingual=False,
            url_model="http://example.com/model.onnx",
            url_json="http://example.com/model.onnx.json",
        )
    for name in existing:
        (tmp_path / name).touch()
    return PiperVoices([voice])


def _make_response(headers: dict, chunks: list[bytes]) -> MagicMock:
    """Mock urlopen response: read() returns the chunks in sequence."""
    mock = MagicMock()
    mock.headers = headers
    mock.read.side_effect = [*chunks, b""]
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


# ===========================================================================
# Tests — synthesize_piper
# ===========================================================================


class TestSynthesizePiper:
    """Tests for WAV synthesis with Piper."""

    def test_returns_valid_wav(self):
        """The result must be a mono 16-bit WAV with the given sample rate."""
        mock_voice = MagicMock()
        sample_rate = 22050

        result = synthesize_piper(mock_voice, "Ciao mondo", sample_rate)

        assert isinstance(result, bytes)
        with wave.open(io.BytesIO(result), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == sample_rate

    def test_calls_synthesize_wav_with_text(self):
        """Must pass the text and the wave writer to PiperVoice."""
        mock_voice = MagicMock()
        text = "Paragrafo di prova"

        synthesize_piper(mock_voice, text, 16000)

        mock_voice.synthesize_wav.assert_called_once()
        args = mock_voice.synthesize_wav.call_args
        assert args[0][0] == text

    def test_different_sample_rates(self):
        """Must respect the provided sample rate."""
        mock_voice = MagicMock()

        for sr in [16000, 22050, 44100]:
            result = synthesize_piper(mock_voice, "Test", sr)
            with wave.open(io.BytesIO(result), "rb") as wf:
                assert wf.getframerate() == sr


# ===========================================================================
# Tests — download_piper_voice (download and errors)
# ===========================================================================


class TestDownloadPiperVoiceDownload:
    """Tests for the actual download and error handling."""

    def test_actual_download_writes_files(self, tmp_path):
        """Must download and write the files if they do not exist."""
        mock_urlopen = MagicMock()
        mock_urlopen.side_effect = [
            _make_response({"Content-Length": "128"}, [b"x" * 64, b"y" * 64]),
            _make_response({"Content-Length": "128"}, [b"z" * 64]),
        ]

        with (
            patch("src.synthesis.VOICE_DIR", tmp_path),
            patch("src.synthesis.PIPER_VOICES", _registry(tmp_path)),
            patch("src.synthesis.urllib.request.urlopen", mock_urlopen),
            patch("builtins.print"),
        ):
            download_piper_voice("paola")

        assert (tmp_path / "model.onnx").read_bytes() == b"x" * 64 + b"y" * 64
        assert (tmp_path / "model.onnx.json").read_bytes() == b"z" * 64

    def test_failed_download_raises_runtime_error(self, tmp_path):
        """Must raise RuntimeError if the download fails."""
        with (
            patch("src.synthesis.VOICE_DIR", tmp_path),
            patch("src.synthesis.PIPER_VOICES", _registry(tmp_path)),
            patch(
                "src.synthesis.urllib.request.urlopen",
                side_effect=ConnectionError("Network down"),
            ),
            pytest.raises(RuntimeError, match="Piper voice download failed"),
        ):
            download_piper_voice("paola")

    def test_download_without_content_length(self, tmp_path):
        """Must work even without the Content-Length header (no progress bar)."""
        mock_urlopen = MagicMock()
        mock_urlopen.side_effect = [
            _make_response({}, [b"data"]),
            _make_response({}, [b"data2"]),
        ]

        with (
            patch("src.synthesis.VOICE_DIR", tmp_path),
            patch("src.synthesis.PIPER_VOICES", _registry(tmp_path)),
            patch("src.synthesis.urllib.request.urlopen", mock_urlopen),
            patch("builtins.print"),
        ):
            download_piper_voice("paola")

        assert (tmp_path / "model.onnx").read_bytes() == b"data"
        assert (tmp_path / "model.onnx.json").read_bytes() == b"data2"
