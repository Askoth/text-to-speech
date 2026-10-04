"""
tests/test_i18n.py
Test suite for the internationalization (i18n) system.

Covers: translations.py (get_lang, tr)
       and the API endpoints with the ?lang= parameter.
"""

from unittest.mock import MagicMock

from src.translations import (
    DEFAULT_LANG,
    TRANSLATIONS,
    get_lang,
    tr,
)

# ===========================================================================
# Tests — translations.get_lang()
# ===========================================================================


class TestGetLang:
    """Determines the language from the HTTP request."""

    def _make_request(self, lang_param="", accept_language=""):
        """Create a mock Flask request with query param and header."""
        req = MagicMock()
        req.args = {"lang": lang_param} if lang_param else {}
        req.headers = {"Accept-Language": accept_language} if accept_language else {}
        return req

    def test_default_no_indications(self):
        """Without a param or header it must return the default language."""
        # Arrange
        req = self._make_request()

        # Act
        lang = get_lang(req)

        # Assert
        assert lang == DEFAULT_LANG

    def test_query_param_it(self):
        """?lang=it must return 'it'."""
        # Arrange
        req = self._make_request(lang_param="it")

        # Act
        lang = get_lang(req)

        # Assert
        assert lang == "it"

    def test_query_param_en(self):
        """?lang=en must return 'en'."""
        # Arrange
        req = self._make_request(lang_param="en")

        # Act
        lang = get_lang(req)

        # Assert
        assert lang == "en"

    def test_query_param_case_insensitive(self):
        """?lang=EN (uppercase) must return 'en'."""
        # Arrange
        req = self._make_request(lang_param="EN")

        # Act
        lang = get_lang(req)

        # Assert
        assert lang == "en"

    def test_query_param_unsupported_language(self):
        """?lang=fr (unsupported) must fall back to the default."""
        # Arrange
        req = self._make_request(lang_param="fr")

        # Act
        lang = get_lang(req)

        # Assert
        assert lang == DEFAULT_LANG

    def test_accept_language_header_it(self):
        """Accept-Language: it-IT must return 'it'."""
        # Arrange
        req = self._make_request(accept_language="it-IT,it;q=0.9")

        # Act
        lang = get_lang(req)

        # Assert
        assert lang == "it"

    def test_accept_language_header_en(self):
        """Accept-Language: en-US,en;q=0.9 must return 'en'."""
        # Arrange
        req = self._make_request(accept_language="en-US,en;q=0.9")

        # Act
        lang = get_lang(req)

        # Assert
        assert lang == "en"

    def test_accept_language_header_fallback(self):
        """Accept-Language: fr-FR (unsupported) must fall back to the default."""
        # Arrange
        req = self._make_request(accept_language="fr-FR,fr;q=0.9")

        # Act
        lang = get_lang(req)

        # Assert
        assert lang == DEFAULT_LANG

    def test_query_param_takes_priority_over_header(self):
        """The ?lang= param must take priority over the Accept-Language header."""
        # Arrange
        req = self._make_request(lang_param="en", accept_language="it-IT")

        # Act
        lang = get_lang(req)

        # Assert
        assert lang == "en"


# ===========================================================================
# Tests — translations.tr()
# ===========================================================================


class TestTr:
    """Translation with interpolation and fallback."""

    def test_translation_it(self):
        """tr() with language 'it' must return the Italian message."""
        # Act
        msg = tr("it", "error.no_file")

        # Assert
        assert msg == "Nessun file inviato"

    def test_translation_en(self):
        """tr() with language 'en' must return the English message."""
        # Act
        msg = tr("en", "error.no_file")

        # Assert
        assert msg == "No file provided"

    def test_single_interpolation(self):
        """tr() must correctly interpolate a parameter."""
        # Act
        msg = tr("it", "error.invalid_voice", voice="mario")

        # Assert
        assert "mario" in msg
        assert "{voice}" not in msg

    def test_multiple_interpolation(self):
        """tr() must interpolate multiple parameters."""
        # Act
        msg = tr("en", "error.unsupported_format", formats=".md, .txt")

        # Assert
        assert ".md, .txt" in msg
        assert "{formats}" not in msg

    def test_fallback_unknown_language(self):
        """tr() with an unsupported language must use the default."""
        # Act
        msg = tr("fr", "error.no_file")

        # Assert
        assert msg == tr(DEFAULT_LANG, "error.no_file")

    def test_nonexistent_key(self):
        """tr() with a nonexistent key must return the key itself."""
        # Act
        msg = tr("it", "error.ghost_key")

        # Assert
        assert msg == "error.ghost_key"

    def test_all_keys_exist_in_both_languages(self):
        """Every key in 'it' must also exist in 'en' and vice versa."""
        # Arrange
        keys_it = {k for k in TRANSLATIONS["it"] if k != "styles"}
        keys_en = {k for k in TRANSLATIONS["en"] if k != "styles"}

        # Assert
        assert keys_it == keys_en, (
            f"Missing keys — only in IT: {keys_it - keys_en}, "
            f"only in EN: {keys_en - keys_it}"
        )


# ===========================================================================
# Tests — API endpoints with the ?lang= parameter
# ===========================================================================


class TestEndpointI18n:
    """Verify that the endpoints return messages in the requested language."""

    def test_load_error_in_italian(self, client):
        """POST /api/load?lang=it without a file must return an Italian error."""
        # Act
        response = client.post("/api/load?lang=it", data={})

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "Nessun file inviato"

    def test_load_error_in_english(self, client):
        """POST /api/load?lang=en without a file must return an English error."""
        # Act
        response = client.post("/api/load?lang=en", data={})

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "No file provided"

    def test_audio_error_invalid_voice_en(self, client):
        """GET /api/audio/0?voice=xxx&lang=en must return an English error."""
        # Act
        response = client.get("/api/audio/0?voice=xxx&lang=en")

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "not valid" in data["error"]

    def test_audio_error_invalid_voice_it(self, client):
        """GET /api/audio/0?voice=xxx&lang=it must return an Italian error."""
        # Act
        response = client.get("/api/audio/0?voice=xxx&lang=it")

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "non valida" in data["error"]

    def test_save_error_no_file_en(self, client):
        """POST /api/save?lang=en without a loaded file must return an English error."""
        # Act
        response = client.post(
            "/api/save?lang=en",
            data='{"voice": "paola"}',
            content_type="application/json",
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "No file loaded"

    def test_default_language_without_param(self, client):
        """Without ?lang=, errors must be in the default language (English)."""
        # Act
        response = client.post("/api/load", data={})

        # Assert
        data = response.get_json()
        assert data["error"] == "No file provided"
