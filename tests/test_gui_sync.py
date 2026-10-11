"""Window ↔ player sync: widgets must mirror player state after every transition.

The web reference re-runs ``updateUI()`` after every state/paragraph change;
the PyQt5 window does the same through ``Player.state_changed``. These tests
pin the contract: paragraph text, progress/counter, button enable states,
spinner text, save button, and error banners all follow the player.
"""

import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from PyQt5.QtWidgets import QApplication
except ImportError:
    pytest.importorskip("PyQt5 not installed")

from src.text_to_speech.gui import player as _player_mod
from src.text_to_speech.gui import strings as _strings
from src.text_to_speech.gui import theme as _theme_mod
from src.text_to_speech.gui import window as _window_mod
from src.text_to_speech.gui.player import State

VOICES = [
    {"name": "alba", "multilingual": False},
    {"name": "paola", "multilingual": True},
]


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def _pump(app, cond, timeout=5.0):
    """Process events until *cond* holds (or the timeout elapses)."""
    deadline = time.time() + timeout
    while time.time() < deadline and not cond():
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture
def gui(qapp):
    """Built window + player (stub engine, three-paragraph file loaded)."""
    _strings.set_lang(_strings.DEFAULT_LANG)
    engine = MagicMock()
    engine.load_file.return_value = ["Alpha.", "Beta.", "Gamma."]
    p = _player_mod.Player(engine)
    w = _window_mod.Window(p, _theme_mod.load(), VOICES)
    w.build()
    p.load(Path(__file__))
    _pump(qapp, lambda: p.total == 3)
    assert p.total == 3
    return w, p


class TestReaderSync:
    def test_load_syncs_reader_and_controls(self, gui):
        w, _ = gui
        assert w._paragraph_label.text() == "Alpha."
        assert w._counter_label.text() == "Paragraph 1 / 3"
        assert not w._btn_start.isEnabled()
        assert not w._btn_prev.isEnabled()
        assert w._btn_play.isEnabled()
        assert not w._btn_stop.isEnabled()
        assert w._btn_next.isEnabled()
        assert w._btn_repeat.isEnabled()
        assert w._save_btn.isEnabled()

    def test_go_to_syncs_label_counter_and_nav(self, gui):
        w, p = gui
        p.go_to(1)
        assert w._paragraph_label.text() == "Beta."
        assert w._counter_label.text() == "Paragraph 2 / 3"
        assert w._btn_prev.isEnabled()
        assert w._btn_start.isEnabled()
        assert w._btn_next.isEnabled()  # idx 1 of 3, next still possible

    def test_last_paragraph_disables_next(self, gui):
        w, p = gui
        p.go_to(2)
        assert not w._btn_next.isEnabled()
        assert w._counter_label.text() == "Paragraph 3 / 3"


class TestPlaybackStates:
    def test_loading_disables_play_and_sets_spinner(self, gui):
        w, p = gui
        p._state = State.LOADING
        p._spinner_active = True
        p.state_changed.emit()
        assert not w._btn_play.isEnabled()
        assert w._btn_play.text() == _strings.t("player.loadingAria")

    def test_synthesis_failure_resets_to_idle(self, gui):
        w, p = gui
        p._state = State.LOADING
        p._spinner_active = True
        p.state_changed.emit()
        p.synthesis_failed.emit("synth broke")
        assert p.state == State.IDLE
        assert not p.spinner_active
        assert w._btn_play.isEnabled()
        assert w._btn_play.text() == _strings.t("label.playPause")
        expected = _strings.t("msg.synthesisErrorDetail", message="synth broke")
        assert w._banner_label.text() == expected

    def test_playback_failed_shows_banner(self, gui):
        w, p = gui
        p.playback_failed.emit()
        assert w._banner.isVisible()
        assert w._banner_label.text() == _strings.t("msg.playbackError")


class TestParseFailure:
    def test_parse_failure_shows_banner_and_resets(self, qapp):
        _strings.set_lang(_strings.DEFAULT_LANG)
        engine = MagicMock()
        engine.load_file.side_effect = ValueError("corrupt file")
        p = _player_mod.Player(engine)
        w = _window_mod.Window(p, _theme_mod.load(), VOICES)
        w.build()
        p.load(Path("does-not-matter.txt"))
        _pump(qapp, lambda: w._banner.isVisible()
               and "corrupt file" in w._banner_label.text())
        assert p.total == 0
        assert p.state == State.IDLE
        assert not p.spinner_active
        assert not w._save_btn.isEnabled()


class TestOpenButton:
    def test_open_button_triggers_load(self, qapp, monkeypatch):
        """Toolbar Open button must open the dialog and start a background load."""
        from PyQt5.QtWidgets import QFileDialog

        _strings.set_lang(_strings.DEFAULT_LANG)
        engine = MagicMock()
        engine.load_file.return_value = ["One.", "Two."]
        p = _player_mod.Player(engine)
        w = _window_mod.Window(p, _theme_mod.load(), VOICES)
        w.build()
        assert w._btn_open is not None
        assert w._btn_open.text() == _strings.t("toolbar.chooseFile")
        assert w._btn_open.isEnabled()

        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            lambda *a, **k: (str(Path(__file__)), ""),
        )
        w._btn_open.click()
        _pump(qapp, lambda: p.total == 2)
        assert p.filename == Path(__file__).name
        assert not w._empty_state.isVisible()


class TestSaveButton:
    def test_save_disabled_before_load(self, qapp):
        _strings.set_lang(_strings.DEFAULT_LANG)
        p = _player_mod.Player(MagicMock())
        w = _window_mod.Window(p, _theme_mod.load(), VOICES)
        w.build()
        assert not w._save_btn.isEnabled()
        assert not w._btn_play.isEnabled()

    def test_save_suppressed_while_saving(self, gui):
        w, p = gui
        w._saving = True
        p.state_changed.emit()
        assert not w._save_btn.isEnabled()
        w._saving = False
        p.state_changed.emit()
        assert w._save_btn.isEnabled()


class TestVoiceCombo:
    def test_combo_wired_to_player(self, gui):
        w, p = gui
        assert p.voice == ""
        w._voice_combo.setCurrentIndex(1)
        assert p.voice == "paola"
        w._voice_combo.setCurrentIndex(0)
        assert p.voice == "alba"
