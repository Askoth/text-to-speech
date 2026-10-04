"""
tests/test_synthesis.py
Test per le funzioni di sintesi vocale: Piper TTS.
"""

import io
import wave
from unittest.mock import MagicMock, patch

import pytest

from src.synthesis import scarica_voce_piper, sintetizza_piper


def _mock_dest(exists: bool, name: str) -> MagicMock:
    """Simula un path del modello: .exists() restituisce il flag, .name il file."""
    d = MagicMock()
    d.exists.return_value = exists
    d.name = name
    return d

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

    def test_download_effettivo_scrive_file(self):
        """Deve scaricare e scrivere il file se non esiste."""
        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": "128"}
        mock_response.read.side_effect = [b"x" * 64, b"y" * 64, b""]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        registry = {
            "paola": {
                "model": _mock_dest(False, "model.onnx"),
                "json": _mock_dest(True, "model.onnx.json"),
                "url_model": "http://example.com/model.onnx",
                "url_json": "http://example.com/model.onnx.json",
            }
        }

        with (
            patch("src.synthesis.VOICE_DIR"),
            patch("src.synthesis.PIPER_VOICES", registry),
            patch("src.synthesis.urllib.request.urlopen", return_value=mock_response),
            patch("builtins.open", return_value=mock_file),
            patch("builtins.print"),
        ):
            scarica_voce_piper("paola")

        assert mock_file.write.call_count == 2

    def test_download_fallito_solleva_runtime_error(self):
        """Deve sollevare RuntimeError se il download fallisce."""
        registry = {
            "paola": {
                "model": _mock_dest(False, "model.onnx"),
                "json": _mock_dest(True, "model.onnx.json"),
                "url_model": "http://example.com/model.onnx",
                "url_json": "http://example.com/model.onnx.json",
            }
        }

        with (
            patch("src.synthesis.VOICE_DIR"),
            patch("src.synthesis.PIPER_VOICES", registry),
            patch(
                "src.synthesis.urllib.request.urlopen",
                side_effect=ConnectionError("Network down"),
            ),
            pytest.raises(RuntimeError, match="Download voce Piper fallito"),
        ):
            scarica_voce_piper("paola")

    def test_download_senza_content_length(self):
        """Deve funzionare anche senza header Content-Length (no progress bar)."""
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.read.side_effect = [b"data", b""]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        registry = {
            "paola": {
                "model": _mock_dest(False, "model.onnx"),
                "json": _mock_dest(True, "model.onnx.json"),
                "url_model": "http://example.com/model.onnx",
                "url_json": "http://example.com/model.onnx.json",
            }
        }

        with (
            patch("src.synthesis.VOICE_DIR"),
            patch("src.synthesis.PIPER_VOICES", registry),
            patch("src.synthesis.urllib.request.urlopen", return_value=mock_response),
            patch("builtins.open", return_value=mock_file),
            patch("builtins.print"),
        ):
            scarica_voce_piper("paola")

        mock_file.write.assert_called_once_with(b"data")
