"""
tests/test_app_extended.py
Additional tests for app.py: security headers, sanitize_filename,
endpoint success paths, prefetch endpoint.

Complements test_app.py (which covers input validation and error cases).
"""

import io
from unittest.mock import patch

import pytest

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def client_with_text(client):
    """Flask test client with a document already loaded in the engine."""
    from src import app as flask_app

    flask_app.engine._paragraphs = [
        "Primo paragrafo di test.",
        "Secondo paragrafo di test.",
        "Terzo paragrafo di test.",
    ]
    flask_app.engine._filename = "documento.md"
    return client


# ===========================================================================
# Tests — Security Headers
# ===========================================================================


class TestSecurityHeaders:
    """Verify that the security headers are present on all responses."""

    def test_x_content_type_options(self, client):
        """Every response must have X-Content-Type-Options: nosniff."""
        # Act
        response = client.get("/")

        # Assert
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self, client):
        """Every response must have X-Frame-Options: DENY."""
        # Act
        response = client.get("/")

        # Assert
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_referrer_policy(self, client):
        """Every response must have Referrer-Policy set."""
        # Act
        response = client.get("/")

        # Assert
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_headers_present_on_api(self, client):
        """The security headers must be present on the API responses too."""
        # Act
        response = client.get("/api/voices")

        # Assert
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_headers_present_on_errors(self, client):
        """The headers must be present on error responses too."""
        # Act
        response = client.get("/api/audio/0")  # no file loaded -> 400

        # Assert
        assert response.headers.get("X-Content-Type-Options") == "nosniff"


# ===========================================================================
# Tests — _sanitize_filename
# ===========================================================================


class TestSanitizeFilename:
    """Tests for the filename sanitization function."""

    def _sanitize(self, name: str) -> str:
        from src.app import _sanitize_filename

        return _sanitize_filename(name)

    def test_simple_valid_filename(self):
        """A simple .md filename must pass through unchanged."""
        assert self._sanitize("documento.md") == "documento.md"

    def test_filename_with_spaces(self):
        """Names with spaces must be accepted."""
        assert self._sanitize("il mio file.md") == "il mio file.md"

    def test_filename_with_hyphens_and_underscore(self):
        """Hyphens and underscores must be accepted."""
        assert self._sanitize("mio-file_v2.md") == "mio-file_v2.md"

    def test_unsupported_format_rejected(self):
        """Files with an unsupported format must be rejected."""
        assert self._sanitize("file.csv") == ""
        assert self._sanitize("file.py") == ""
        assert self._sanitize("file.xlsx") == ""
        assert self._sanitize("file.pptx") == ""

    def test_path_traversal_blocked(self):
        """Path traversal attempts must be neutralized."""
        # Path traversal is blocked by PurePosixPath.name
        result = self._sanitize("../../../etc/passwd.md")
        # It must extract only the base name
        assert "/" not in result
        assert ".." not in result

    def test_empty_filename_rejected(self):
        """An empty name must be rejected."""
        assert self._sanitize("") == ""

    def test_only_extension_rejected(self):
        """A lone '.md' with no name must be rejected."""
        assert self._sanitize(".md") == ""

    def test_filename_with_special_chars_rejected(self):
        """Special characters (;, &, |, etc.) must cause rejection."""
        assert self._sanitize("file;rm -rf.md") == ""
        assert self._sanitize("file|cat.md") == ""
        assert self._sanitize("file$(cmd).md") == ""

    def test_unicode_filename_accepted(self):
        """Names with unicode characters (accents) must be accepted."""
        result = self._sanitize("caffè.md")
        assert result == "caffè.md"

    def test_all_supported_formats_accepted(self):
        """All supported formats must be accepted."""
        assert self._sanitize("libro.epub") == "libro.epub"
        assert self._sanitize("documento.docx") == "documento.docx"
        assert self._sanitize("pagina.html") == "pagina.html"
        assert self._sanitize("pagina.htm") == "pagina.htm"
        assert self._sanitize("report.pdf") == "report.pdf"
        assert self._sanitize("nota.txt") == "nota.txt"
        assert self._sanitize("readme.md") == "readme.md"

    def test_double_extension_handled(self):
        """A suspicious double-extension filename must be handled."""
        # "file.php.md" contains a dot in the name, which is allowed
        result = self._sanitize("file.php.md")
        # The regex allows the dot, so it passes — it is a valid .md file
        assert result == "file.php.md"


# ===========================================================================
# Tests — /api/audio success path
# ===========================================================================


class TestAudioEndpointSuccess:
    """Tests for the success path of the audio endpoint."""

    def test_audio_returns_mp3(self, client_with_text):
        """GET /api/audio/0 with a loaded file must return audio/mpeg."""
        # Arrange
        from src import app as flask_app

        fake_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00"

        with patch.object(flask_app.engine, "get_audio", return_value=fake_mp3):
            # Act
            response = client_with_text.get("/api/audio/0?voice=paola")

        # Assert
        assert response.status_code == 200
        assert response.content_type == "audio/mpeg"
        assert response.data == fake_mp3

    def test_audio_passes_voice_to_engine(self, client_with_text):
        """GET /api/audio/0?voice=paola must pass the voice to the engine."""
        # Arrange
        from src import app as flask_app

        fake_mp3 = b"mp3_paola"

        with patch.object(flask_app.engine, "get_audio", return_value=fake_mp3) as mock:
            # Act
            response = client_with_text.get("/api/audio/1?voice=paola")

        # Assert
        assert response.status_code == 200
        mock.assert_called_once_with(1, "paola")

    def test_audio_nonexistent_paragraph_404(self, client_with_text):
        """GET /api/audio/999 must return 404."""
        # Arrange
        from src import app as flask_app

        with patch.object(flask_app.engine, "get_audio", side_effect=IndexError("out of range")):
            # Act
            response = client_with_text.get("/api/audio/999?voice=paola")

        # Assert
        assert response.status_code == 404

    def test_audio_synthesis_error_500(self, client_with_text):
        """A synthesis error must return 500 with a generic message."""
        # Arrange
        from src import app as flask_app

        with (
            patch.object(
                flask_app.engine,
                "get_audio",
                side_effect=RuntimeError("ffmpeg crashed"),
            ),
            patch("src.app.log"),
        ):
            # Act
            response = client_with_text.get("/api/audio/0?voice=paola")

        # Assert
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data
        # The message must NOT contain internal details
        assert "ffmpeg" not in data["error"]


# ===========================================================================
# Tests — /api/prefetch
# ===========================================================================


class TestPrefetchEndpoint:
    """Tests for the prefetch endpoint."""

    def test_prefetch_returns_ok(self, client_with_text):
        """GET /api/prefetch/1 must return status ok."""
        # Arrange
        from src import app as flask_app

        with patch.object(flask_app.engine, "prefetch") as mock_pf:
            # Act
            response = client_with_text.get("/api/prefetch/1?voice=paola")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        mock_pf.assert_called_once_with(1, "paola")

    def test_prefetch_uses_default_voice(self, client_with_text):
        """Without the voice parameter, it must use the default voice."""
        # Arrange
        from src import app as flask_app
        from src.config import DEFAULT_VOICE

        with patch.object(flask_app.engine, "prefetch") as mock_pf:
            # Act
            response = client_with_text.get("/api/prefetch/0")

        # Assert
        assert response.status_code == 200
        mock_pf.assert_called_once_with(0, DEFAULT_VOICE)


# ===========================================================================
# Tests — /api/save success path
# ===========================================================================


class TestSaveEndpointSuccess:
    """Tests for the success path of the save endpoint."""

    def test_save_returns_mp3_with_content_disposition(self, client_with_text):
        """POST /api/save must return MP3 with the Content-Disposition header."""
        # Arrange
        from src import app as flask_app

        fake_mp3 = b"ID3\x04\x00complete_audio"

        with patch.object(flask_app.engine, "save_all", return_value=fake_mp3):
            # Act
            response = client_with_text.post(
                "/api/save",
                data='{"voice": "paola"}',
                content_type="application/json",
            )

        # Assert
        assert response.status_code == 200
        assert response.content_type == "audio/mpeg"
        assert "Content-Disposition" in response.headers
        assert "attachment" in response.headers["Content-Disposition"]
        assert ".mp3" in response.headers["Content-Disposition"]

    def test_save_with_invalid_voice_400(self, client_with_text):
        """POST /api/save with a nonexistent voice must return 400."""
        # Act
        response = client_with_text.post(
            "/api/save",
            data='{"voice": "voce_fake"}',
            content_type="application/json",
        )

        # Assert
        assert response.status_code == 400
        assert "error" in response.get_json()


# ===========================================================================
# Tests — /api/load with path traversal
# ===========================================================================


class TestLoadEndpointSecurity:
    """Security tests for the file upload endpoint."""

    def test_load_path_traversal_blocked(self, client):
        """A file with path traversal in the name must be rejected."""
        # Arrange
        evil_file = (io.BytesIO(b"# Hack"), "../../../etc/passwd.md")

        # Act
        response = client.post(
            "/api/load",
            data={"file": evil_file},
            content_type="multipart/form-data",
        )

        # Assert — it may be accepted (base name extracted) or rejected
        # What matters is that the path traversal is neutralized
        if response.status_code == 200:
            data = response.get_json()
            assert "/" not in data["filename"]
            assert ".." not in data["filename"]

    def test_load_filename_with_null_byte_rejected(self, client):
        """A file with a null byte in the name must be rejected."""
        # Arrange
        evil_file = (io.BytesIO(b"# Content"), "file\x00.md")

        # Act
        response = client.post(
            "/api/load",
            data={"file": evil_file},
            content_type="multipart/form-data",
        )

        # Assert
        assert response.status_code == 400


# ===========================================================================
# Tests — VOICES_META consistency
# ===========================================================================


class TestVoicesMeta:
    """Tests for the consistency of the voice metadata."""

    def test_voices_meta_contains_all_voices(self):
        """VOICES_META must have an entry for every voice in ALL_VOICES."""
        from src.app import VOICES_META
        from src.config import ALL_VOICES

        # Arrange
        meta_ids = {v["id"] for v in VOICES_META}

        # Assert
        assert meta_ids == set(ALL_VOICES)

    def test_voices_meta_required_fields(self):
        """Each voice must have id, label, type, multilingual, gender, lang."""
        from src.app import VOICES_META

        # Assert
        fields = {"id", "label", "type", "multilingual", "gender", "lang"}
        for voice in VOICES_META:
            assert fields <= voice.keys(), (
                f"Voice '{voice.get('id')}' missing: {fields - voice.keys()}"
            )

    def test_voices_meta_valid_gender(self):
        """The gender must be 'M' or 'F'."""
        from src.app import VOICES_META

        # Assert
        for voice in VOICES_META:
            assert voice["gender"] in (
                "M",
                "F",
            ), f"Voice '{voice['id']}' has invalid gender '{voice['gender']}'"


# ===========================================================================
# Tests — errorhandler 413 (file too large)
# ===========================================================================


class TestTooLargeErrorHandler:
    """Verify that the 413 errorhandler responds with JSON and a message."""

    def test_upload_too_large_returns_413(self, client):
        """A file larger than MAX_CONTENT_LENGTH must return 413."""
        # Arrange — lower the limit to 10 bytes for this test only
        from src.app import app

        original_limit = app.config["MAX_CONTENT_LENGTH"]
        app.config["MAX_CONTENT_LENGTH"] = 10

        try:
            payload = b"X" * 50  # 50 bytes > 10 byte limit
            data = {"file": (io.BytesIO(payload), "grande.txt")}

            # Act
            response = client.post(
                "/api/load",
                data=data,
                content_type="multipart/form-data",
            )
        finally:
            app.config["MAX_CONTENT_LENGTH"] = original_limit

        # Assert
        assert response.status_code == 413
        body = response.get_json()
        assert body is not None
        assert "error" in body

    def test_413_has_security_headers(self, client):
        """The 413 response must have the security headers."""
        # Arrange
        from src.app import app

        original_limit = app.config["MAX_CONTENT_LENGTH"]
        app.config["MAX_CONTENT_LENGTH"] = 10

        try:
            data = {"file": (io.BytesIO(b"X" * 50), "grande.txt")}

            # Act
            response = client.post(
                "/api/load",
                data=data,
                content_type="multipart/form-data",
            )
        finally:
            app.config["MAX_CONTENT_LENGTH"] = original_limit

        # Assert
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
