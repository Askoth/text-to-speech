"""End-to-end GUI smoke checks: layout, single-instance guard, thread cleanup.

Skipped when PyQt5 is not installed.
"""

import os
import socket
import subprocess
import sys
import threading
import time

import pytest

try:
    from PyQt5.QtWidgets import QApplication
except ImportError:
    pytest.importorskip("PyQt5 not installed")

from src.text_to_speech.gui import main
from src.text_to_speech.gui.player import Player
from src.tts_engine import TTSEngine

SOCKET_NAME = "\0text-to-speech-gui"


def _isolate_xdg(monkeypatch, tmp_path):
    """Keep the bootstrap from touching the user's real XDG dirs."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def _hold_socket():
    """Bind the guard socket and hand it back still open."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_NAME)
    return sock


def _assert_window_populated(app):
    """Stand-in for ``QApplication.exec``: inspect the window, never block."""
    app.processEvents()
    window = QApplication.activeWindow()
    assert window is not None, "no active window after build()"
    assert window.centralWidget() is not None, "window has no central widget"

    win = window._window
    assert win._top_bar.isVisible()
    assert win._reader_area.isVisible()
    assert win._bottom_bar.isVisible()
    assert all(btn.isVisible() for btn in win._control_buttons())
    assert win._progress_bar.isVisible()
    assert win._counter_label.isVisible()
    assert win._empty_state.isVisible(), "empty state must start visible"
    assert not win._reader_card.isVisible()
    assert not win._banner.isVisible(), "banner must start hidden"
    return 0


class TestGuiSmoke:
    def test_single_instance_guard_blocks_second_launch(self, tmp_path, monkeypatch):
        _isolate_xdg(monkeypatch, tmp_path)
        sock = _hold_socket()
        try:
            result = subprocess.run(
                [sys.executable, "gui.py"],
                capture_output=True,
                text=True,
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                timeout=30,
            )
        finally:
            sock.close()

        assert result.returncode == 1
        assert "only one instance allowed" in result.stderr

    def test_window_renders_non_empty(self, tmp_path, monkeypatch):
        _isolate_xdg(monkeypatch, tmp_path)
        monkeypatch.setattr(QApplication, "exec", _assert_window_populated)

        assert main() == 0

    def test_shutdown_leaves_no_thread_leak(self, tmp_path, monkeypatch):
        _isolate_xdg(monkeypatch, tmp_path)
        engine = TTSEngine()
        p = Player(engine)

        text = tmp_path / "sample.txt"
        text.write_text("First paragraph.\n\nSecond paragraph.\n")
        p.load(text)
        p.shutdown()

        time.sleep(0.2)
        assert threading.active_count() <= 5, f"thread leak: {threading.active_count()}"
