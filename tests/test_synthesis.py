"""
tests/test_synthesis.py
Test per le funzioni di sintesi vocale: Piper TTS.
"""

import io
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import PiperVoices, Voice
from src.synthesis import scarica_voce_piper, sintetizza_piper


def _registry(tmp_path: Path, existing: tuple[str, ...] = ()) -> PiperVoices:
    """Registro 'paola' con model/json sotto tmp_path (crea i file in existing)."""
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
    """Risposta urlopen mock: read() restituisce i chunks in sequenza."""
    mock = MagicMock()
    mock.headers = headers
    mock.read.side_effect = [*chunks, b""]
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


# ===========================================================================
# Test — sintetizza_piper
# ===========================================================================


class TestSintetizzaPiper:
    """Test per la sintesi WAV con Piper."""

    def test_restituisce_wav_valido(self):
        """Il risultato deve essere un WAV mono 16-bit con il sample rate dato."""
        mock_voce = MagicMock()
        sample_rate = 22050

        risultato = sintetizza_piper(mock_voce, "Ciao mondo", sample_rate)

        assert isinstance(risultato, bytes)
        with wave.open(io.BytesIO(risultato), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == sample_rate

    def test_chiama_synthesize_wav_con_testo(self):
        """Deve passare il testo e il wave writer a PiperVoice."""
        mock_voce = MagicMock()
        testo = "Paragrafo di prova"

        sintetizza_piper(mock_voce, testo, 16000)

        mock_voce.synthesize_wav.assert_called_once()
        args = mock_voce.synthesize_wav.call_args
        assert args[0][0] == testo

    def test_sample_rate_diversi(self):
        """Deve rispettare il sample rate fornito."""
        mock_voce = MagicMock()

        for sr in [16000, 22050, 44100]:
            risultato = sintetizza_piper(mock_voce, "Test", sr)
            with wave.open(io.BytesIO(risultato), "rb") as wf:
                assert wf.getframerate() == sr


# ===========================================================================
# Test — scarica_voce_piper (download e errore)
# ===========================================================================


class TestScaricaVocePiperDownload:
    """Test per il download effettivo e la gestione errori."""

    def test_download_effettivo_scrive_file(self, tmp_path):
        """Deve scaricare e scrivere i file se non esistono."""
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
            scarica_voce_piper("paola")

        assert (tmp_path / "model.onnx").read_bytes() == b"x" * 64 + b"y" * 64
        assert (tmp_path / "model.onnx.json").read_bytes() == b"z" * 64

    def test_download_fallito_solleva_runtime_error(self, tmp_path):
        """Deve sollevare RuntimeError se il download fallisce."""
        with (
            patch("src.synthesis.VOICE_DIR", tmp_path),
            patch("src.synthesis.PIPER_VOICES", _registry(tmp_path)),
            patch(
                "src.synthesis.urllib.request.urlopen",
                side_effect=ConnectionError("Network down"),
            ),
            pytest.raises(RuntimeError, match="Download voce Piper fallito"),
        ):
            scarica_voce_piper("paola")

    def test_download_senza_content_length(self, tmp_path):
        """Deve funzionare anche senza header Content-Length (no progress bar)."""
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
            scarica_voce_piper("paola")

        assert (tmp_path / "model.onnx").read_bytes() == b"data"
        assert (tmp_path / "model.onnx.json").read_bytes() == b"data2"
