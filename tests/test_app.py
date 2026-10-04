"""
tests/test_app.py
Test suite for TTS Reader: leggi, app (Flask), tts_engine.

External dependencies (piper, ffmpeg) are always mocked
to guarantee isolated and fast tests.
"""

import io
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ===========================================================================
# Tests — leggi.py
# ===========================================================================


class TestMarkdownToText:
    """Tests for the Markdown converter (regex fallback, no pandoc)."""

    def _convert(self, markdown: str) -> str:
        """Helper: converts Markdown via a temp file with forced regex fallback."""
        from src.converters import file_to_text

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(markdown)
            tmp_path = Path(f.name)

        try:
            with patch("src.converters.shutil.which", return_value=None):
                return file_to_text(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_markdown_to_text_headers(self):
        """Markdown titles (# ## ###) must be removed from the text."""
        # Arrange
        markdown = "# Titolo principale\n\n## Sottotitolo\n\n### Terzo livello"

        # Act
        result = self._convert(markdown)

        # Assert
        assert "#" not in result
        assert "Titolo principale" in result
        assert "Sottotitolo" in result
        assert "Terzo livello" in result

    def test_markdown_to_text_bold_italic(self):
        """Bold (**text**) and italic (*text*) must be removed."""
        # Arrange
        markdown = "Questo è **grassetto** e questo è *corsivo*."

        # Act
        result = self._convert(markdown)

        # Assert
        assert "**" not in result
        assert "*" not in result
        assert "grassetto" in result
        assert "corsivo" in result

    def test_markdown_to_text_links(self):
        """Links [text](url) must become only the visible text."""
        # Arrange
        markdown = "Visita [OpenAI](https://openai.com) per saperne di più."

        # Act
        result = self._convert(markdown)

        # Assert
        assert "https://openai.com" not in result
        assert "[" not in result
        assert "]" not in result
        assert "OpenAI" in result

    def test_markdown_to_text_code_blocks(self):
        """Inline and multiline code blocks must be removed."""
        # Arrange
        markdown = (
            "Usa il comando `pip install flask` per installare.\n\n"
            "```python\ndef hello():\n    return 'world'\n```"
        )

        # Act
        result = self._convert(markdown)

        # Assert
        assert "```" not in result
        assert "`" not in result
        # The text around the code block stays intact
        assert "Usa il comando" in result
        assert "per installare." in result

    def test_markdown_to_text_empty(self):
        """An empty file must return an empty string."""
        # Arrange
        markdown = ""

        # Act
        result = self._convert(markdown)

        # Assert
        assert result == ""


# ===========================================================================
# Tests — app.py (Flask test client)
# ===========================================================================


class TestIndexEndpoint:
    def test_index_returns_html(self, client):
        """GET / must return 200 with Content-Type text/html."""
        # Act
        response = client.get("/")

        # Assert
        assert response.status_code == 200
        assert b"html" in response.data.lower()


class TestVoicesEndpoint:
    def test_voices_endpoint(self, client):
        """GET /api/voices must return the voices with the correct structure."""
        from src.config import ALL_VOICES

        # Act
        response = client.get("/api/voices")
        data = response.get_json()

        # Assert
        assert response.status_code == 200
        assert "voices" in data
        assert "default" in data
        available_ids = {v["id"] for v in data["voices"]}
        assert available_ids == set(ALL_VOICES)

        # Each voice must have the required fields
        required_fields = {"id", "label", "type", "multilingual", "gender", "lang"}
        for voice in data["voices"]:
            assert required_fields <= voice.keys(), (
                f"Voice {voice.get('id')} missing fields: {required_fields - voice.keys()}"
            )

        # Verify that the default voice exists in the list
        assert data["default"] in available_ids


class TestLoadEndpoint:
    def test_load_no_file(self, client):
        """POST /api/load without a file must return 400."""
        # Act
        response = client.post("/api/load", data={})

        # Assert
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_load_unsupported_format(self, client):
        """POST /api/load with an unsupported format must return 400."""
        # Arrange
        file_csv = (io.BytesIO(b"a,b,c"), "dati.csv")

        # Act
        response = client.post(
            "/api/load",
            data={"file": file_csv},
            content_type="multipart/form-data",
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_load_valid_file(self, client):
        """POST /api/load with a valid .md file must return the paragraphs."""
        # Arrange
        md_content = b"# Titolo\n\nPrimo paragrafo del documento.\n\nSecondo paragrafo."
        file_md = (io.BytesIO(md_content), "test.md")

        mock_paragraphs = ["Primo paragrafo del documento.", "Secondo paragrafo."]

        # Act — mock engine.load_file to avoid real pandoc/filesystem
        with patch("src.app.engine.load_file", return_value=mock_paragraphs):
            response = client.post(
                "/api/load",
                data={"file": file_md},
                content_type="multipart/form-data",
            )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert "filename" in data
        assert "total" in data
        assert "paragraphs" in data
        assert data["total"] == len(mock_paragraphs)
        assert data["filename"] == "test.md"

        # Each paragraph must have idx, text, chars
        for par in data["paragraphs"]:
            assert "idx" in par
            assert "text" in par
            assert "chars" in par
            assert par["chars"] == len(par["text"])


class TestAudioEndpoint:
    def test_audio_no_file_loaded(self, client):
        """GET /api/audio/0 without a loaded file must return 400."""
        # Arrange — engine without paragraphs (reset by the fixture)

        # Act
        response = client.get("/api/audio/0")

        # Assert
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_audio_invalid_voice(self, client):
        """GET /api/audio/0?voice=nonexistent must return 400."""
        # Act
        response = client.get("/api/audio/0?voice=nonexistent")

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "nonexistent" in data["error"]


class TestSaveEndpoint:
    def test_save_no_file_loaded(self, client):
        """POST /api/save without a loaded file must return 400."""
        # Act
        response = client.post(
            "/api/save",
            data='{"voice": "paola"}',
            content_type="application/json",
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"]  # non-empty message
        assert "caricato" in data["error"] or "loaded" in data["error"]


# ===========================================================================
# Tests — tts_engine.py
# ===========================================================================


class TestTTSEngine:
    def test_engine_paragraphs_empty(self, engine):
        """A freshly created engine must have an empty paragraphs list."""
        # Assert
        assert engine.paragraphs == []
        assert engine.filename == ""

    def test_engine_load_text(self, engine):
        """load_text must split the text on double newlines."""
        # Arrange
        text = "Primo paragrafo.\n\nSecondo paragrafo.\n\nTerzo paragrafo."
        filename = "documento.md"

        # Act
        paragraphs = engine.load_text(text, filename)

        # Assert
        assert len(paragraphs) == 3
        assert paragraphs[0] == "Primo paragrafo."
        assert paragraphs[1] == "Secondo paragrafo."
        assert paragraphs[2] == "Terzo paragrafo."
        assert engine.filename == filename
        assert engine.paragraphs == paragraphs

    def test_engine_load_text_strips_whitespace(self, engine):
        """load_text must drop empty paragraphs and leading/trailing spaces."""
        # Arrange
        text = "\n\n  Paragrafo con spazi  \n\n\n\nAltro paragrafo.\n\n"

        # Act
        paragraphs = engine.load_text(text, "test.md")

        # Assert — only non-empty paragraphs after strip
        assert len(paragraphs) == 2
        assert paragraphs[0] == "Paragrafo con spazi"
        assert paragraphs[1] == "Altro paragrafo."

    def test_engine_cache_hit(self, engine):
        """get_audio must use the cache and not call _synthesize twice."""
        # Arrange
        engine.load_text("Paragrafo di test.", "test.md")
        fake_mp3 = b"ID3\x00fake_mp3_content"

        with patch.object(engine, "_synthesize", return_value=fake_mp3) as mock_synth:
            # Act — first call: synthesis + cache insertion
            result_1 = engine.get_audio(0, "paola")

            # Reset the mock to verify the second call does NOT invoke _synthesize
            mock_synth.reset_mock()

            # Act — second call: must use the cache
            result_2 = engine.get_audio(0, "paola")

        # Assert
        assert result_1 == fake_mp3
        assert result_2 == fake_mp3
        # The second call must NOT have invoked _synthesize
        mock_synth.assert_not_called()

    def test_engine_index_out_of_range(self, engine):
        """get_audio with an invalid index must raise IndexError."""
        # Arrange
        engine.load_text("Un solo paragrafo.", "test.md")

        # Act & Assert — index too high
        with pytest.raises(IndexError):
            engine.get_audio(99, "paola")

    def test_engine_index_negative(self, engine):
        """get_audio with a negative index must raise IndexError."""
        # Arrange
        engine.load_text("Paragrafo.", "test.md")

        # Act & Assert
        with pytest.raises(IndexError):
            engine.get_audio(-1, "paola")

    def test_engine_cache_different_voices(self, engine):
        """Cache key includes the voice: different voices do not share the cache."""
        # Arrange
        engine.load_text("Paragrafo test.", "test.md")
        mp3_paola = b"mp3_paola"
        mp3_maria = b"mp3_maria"

        def fake_synthesize(index, voice):
            return mp3_paola if voice == "paola" else mp3_maria

        # We also patch prefetch: the test covers only cache keys
        with (
            patch.object(engine, "_synthesize", side_effect=fake_synthesize),
            patch.object(engine, "prefetch"),
        ):
            # Act
            audio_paola = engine.get_audio(0, "paola")
            audio_maria = engine.get_audio(0, "maria")

        # Assert — distinct results per different voice
        assert audio_paola == mp3_paola
        assert audio_maria == mp3_maria
        assert audio_paola != audio_maria


# ===========================================================================
# Tests — TTSEngine._synthesize
# ===========================================================================


class TestSynthesize:
    def test_synthesize_piper_loads_model_lazy(self, engine):
        """_synthesize with a Piper voice must load the model and convert WAV to MP3."""
        # Arrange
        engine.load_text("Testo Piper.", "test.md")
        fake_wav = b"RIFF\x00\x00fake_wav"
        fake_mp3 = b"ID3\x00fake_piper_mp3"

        with (
            patch.object(engine, "_load_piper") as mock_load,
            patch("src.tts_engine.synthesize_piper", return_value=fake_wav),
            patch("src.tts_engine._wav_to_mp3_bytes", return_value=fake_mp3),
        ):
            # Act
            result = engine._synthesize(0, "paola")

        # Assert
        assert result == fake_mp3
        mock_load.assert_called_once()


# ===========================================================================
# Tests — TTSEngine.save_all
# ===========================================================================


class TestSaveAll:
    def test_save_all_concatenates_all_paragraphs(self, engine):
        """save_all must synthesize all paragraphs and concatenate them."""
        # Arrange
        engine.load_text("Primo.\n\nSecondo.\n\nTerzo.", "test.md")

        call_count = 0

        def fake_get_audio(idx, voice):
            nonlocal call_count
            call_count += 1
            return f"mp3_{idx}".encode()

        with patch.object(engine, "get_audio", side_effect=fake_get_audio):
            # Act
            result = engine.save_all("paola")

        # Assert
        assert call_count == 3
        assert result == b"mp3_0mp3_1mp3_2"


# ===========================================================================
# Tests — TTSEngine.prefetch logging
# ===========================================================================


class TestPrefetchLogging:
    def test_prefetch_logs_warning_on_failure(self, engine):
        """Prefetch must log a warning when synthesis fails."""
        # Arrange
        engine.load_text("Paragrafo test.", "test.md")

        with (
            patch.object(engine, "_synthesize", side_effect=RuntimeError("boom")),
            patch("src.tts_engine.log") as mock_log,
        ):
            # Act
            engine.prefetch(0, "paola")
            # Wait for the thread pool to run the task
            time.sleep(0.5)

        # Assert
        mock_log.warning.assert_called_once()
        call_args = mock_log.warning.call_args
        assert "Synthesis failed for paragraph" in call_args[0][0]
        assert call_args[0][1] == 0  # paragraph index


# ===========================================================================
# Tests — /api/save as a POST endpoint
# ===========================================================================


class TestSaveEndpointPost:
    def test_save_rejects_get(self, client):
        """GET /api/save must return 405 Method Not Allowed."""
        # Act
        response = client.get("/api/save")

        # Assert
        assert response.status_code == 405

    def test_save_post_no_file_loaded(self, client):
        """POST /api/save without a loaded file must return 400."""
        # Act
        response = client.post(
            "/api/save",
            data='{"voice": "paola"}',
            content_type="application/json",
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"]
        assert "caricato" in data["error"] or "loaded" in data["error"]

    def test_save_post_invalid_voice(self, client):
        """POST /api/save with an invalid voice must return 400."""
        # Act
        response = client.post(
            "/api/save",
            data='{"voice": "nonexistent"}',
            content_type="application/json",
        )

        # Assert
        assert response.status_code == 400


# ===========================================================================
# Tests — TTSEngine._load_piper double-checked locking
# ===========================================================================


class TestLoadPiper:
    def test_load_piper_called_once_with_concurrent_threads(self, engine):
        """_load_piper must load the model only once even with concurrent threads."""
        # Arrange
        mock_voice = MagicMock()
        mock_voice.config.sample_rate = 22050
        mock_piper_module = MagicMock()
        mock_piper_module.PiperVoice.load.return_value = mock_voice

        with (
            patch("src.tts_engine.download_piper_voice"),
            patch.dict("sys.modules", {"piper": mock_piper_module}),
        ):
            # Act — 5 concurrent threads calling the real _load_piper
            threads = []
            for _ in range(5):
                t = threading.Thread(target=engine._load_piper, args=("paola",))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

        # Assert — PiperVoice.load must be called only once
        mock_piper_module.PiperVoice.load.assert_called_once()
        assert engine._piper_voices["paola"] is mock_voice
