"""Tests for the GUI i18n layer (``gui/strings.py``).

``strings.py`` is Qt-free, so no PyQt5 / offscreen setup is needed here —
unlike ``test_theme_gui.py``.
"""

import pytest

import src.text_to_speech.gui.strings as strings


@pytest.fixture(autouse=True)
def _reset_lang():
    """``t`` reads module-level state; reset to EN so tests are order-independent."""
    strings.set_lang("en")
    yield


EXPECTED_KEYS = frozenset(
    {
        # Toolbar
        "toolbar.chooseFile",
        "toolbar.chooseFileAria",
        "toolbar.voice",
        "toolbar.voiceAria",
        "toolbar.loading",
        "toolbar.saveBtn",
        "toolbar.saveAria",
        "toolbar.saveTitle",
        # Empty state
        "empty.title",
        "empty.formats",
        # Error banner
        "error.closeAria",
        # Progress
        "progress.aria",
        "progress.sliderTitle",
        "progress.counter",
        "progress.counterEmpty",
        "progress.valueText",
        # Player controls
        "player.controlsAria",
        "player.startAria",
        "player.startTitle",
        "player.prevAria",
        "player.prevTitle",
        "player.playAria",
        "player.pauseAria",
        "player.playTitle",
        "player.loadingAria",
        "player.stopAria",
        "player.stopTitle",
        "player.nextAria",
        "player.nextTitle",
        "player.repeatAria",
        "player.repeatTitle",
        # Control labels
        "label.start",
        "label.prev",
        "label.playPause",
        "label.stop",
        "label.next",
        "label.repeat",
        # Keyboard hints
        "kbd.space",
        "kbd.playPause",
        "kbd.prev",
        "kbd.next",
        "kbd.repeat",
        "kbd.aria",
        # Dynamic messages
        "msg.loadError",
        "msg.loadErrorDetail",
        "msg.synthesisError",
        "msg.synthesisErrorDetail",
        "msg.playbackError",
        "msg.saveFailed",
    }
)


class TestInventory:
    def test_key_set_exact(self):
        assert set(strings.TRANSLATIONS["en"]) == EXPECTED_KEYS
        assert set(strings.TRANSLATIONS["it"]) == EXPECTED_KEYS

    def test_key_count(self):
        assert len(strings.TRANSLATIONS["en"]) == 49
        assert len(strings.TRANSLATIONS["it"]) == 49

    def test_no_style_keys(self):
        for lang in strings.TRANSLATIONS.values():
            assert "toolbar.style" not in lang
            assert "toolbar.styleAria" not in lang

    def test_all_values_nonempty_strings(self):
        for lang, table in strings.TRANSLATIONS.items():
            for key, value in table.items():
                assert isinstance(value, str) and value, (lang, key)

    def test_langs(self):
        assert strings._LANGS == ("en", "it")
        assert strings.DEFAULT_LANG == "en"


class TestDefaultAndLookup:
    def test_defaults_to_en(self):
        assert strings.t("empty.title") == "Load a file to start"

    def test_missing_key_returns_key(self):
        assert strings.t("does.not.exist") == "does.not.exist"

    def test_apostrophe_ported(self):
        strings.set_lang("it")
        assert strings.t("player.startAria") == "Torna all'inizio"

    def test_em_dash_ported(self):
        assert strings.t("progress.counterEmpty") == "Paragraph — / —"
        strings.set_lang("it")
        assert strings.t("progress.counterEmpty") == "Paragrafo — / —"

    def test_interpolation_en(self):
        strings.set_lang("en")
        assert strings.t("progress.counter", current=3, total=10) == "Paragraph 3 / 10"
        assert strings.t("progress.valueText", current=3, total=10) == "Paragraph 3 of 10"
        assert strings.t("msg.saveFailed", message="boom") == "Save failed: boom"

    def test_interpolation_it(self):
        strings.set_lang("it")
        assert strings.t("progress.counter", current=3, total=10) == "Paragrafo 3 / 10"
        assert strings.t("progress.valueText", current=3, total=10) == "Paragrafo 3 di 10"
        assert strings.t("msg.loadErrorDetail", message="oops") == "Errore nel caricamento: oops"

    def test_unfilled_placeholder_kept_literal(self):
        strings.set_lang("en")
        assert strings.t("progress.counter") == "Paragraph {current} / {total}"
        assert strings.t("msg.saveFailed") == "Save failed: {message}"


class TestSetLang:
    def test_roundtrip(self):
        assert strings.set_lang("en") == "en"
        assert strings.current() == "en"
        assert strings.set_lang("it") == "it"
        assert strings.current() == "it"

    def test_unknown_normalizes_to_default(self):
        assert strings.set_lang("fr") == "en"
        assert strings.current() == "en"

    def test_case_and_whitespace_normalized(self):
        assert strings.set_lang("  IT ") == "it"
        assert strings.current() == "it"

    def test_none_and_empty_default(self):
        assert strings.set_lang(None) == "en"
        assert strings.set_lang("") == "en"

    def test_nonstring_normalized(self):
        assert strings.set_lang(5) == "en"
