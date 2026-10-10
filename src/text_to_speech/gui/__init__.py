"""GUI package entrypoint — QApplication bootstrap, single-instance guard, config loading."""

import os
import socket
import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from src.config import ensure_seeded, load_settings
from src.text_to_speech.gui import player as _player_mod
from src.text_to_speech.gui import strings as _strings
from src.text_to_speech.gui import styles as _styles
from src.text_to_speech.gui import theme as _theme_mod
from src.text_to_speech.gui import window as _window_mod
from src.tts_engine import TTSEngine

SOCKET_NAME = "\0text-to-speech-gui"

_INSTANCE_LOCK: socket.socket | None = None


def _single_instance_guard() -> None:
    """Bind an abstract Unix-domain socket; if already bound, exit with message."""
    global _INSTANCE_LOCK
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(SOCKET_NAME)
    except OSError:
        print("only one instance allowed", file=sys.stderr)
        raise SystemExit(1) from None
    _INSTANCE_LOCK = sock  # keep alive for the whole process lifetime


def main(*, verbose: bool = False) -> int:
    """Launch the GUI. Returns exit code."""
    _single_instance_guard()

    try:
        ensure_seeded()
        cfg, config_warnings = load_settings()
    except Exception as e:
        print(f"config error: {e}", file=sys.stderr)
        return 1

    _strings.set_lang(cfg["lang"])

    app = QApplication.instance() or QApplication([])

    theme_obj = _theme_mod.load()
    _styles.apply(theme_obj)

    engine = TTSEngine()
    p = _player_mod.Player(engine)
    w = _window_mod.Window(p, theme_obj)
    w.build()

    if config_warnings:
        w.show_empty_state()
        w.show_banner("\n".join(config_warnings), severity="warning")

    voices = cfg["voices"]
    if w._voice_combo is not None:
        for v in voices:
            label = v["name"].capitalize()
            if v.get("multilingual"):
                label += " (multi)"
            w._voice_combo.addItem(label)
        if voices:
            w._voice_combo.setCurrentIndex(0)

    last_voice = cfg.get("last_voice", "")
    if last_voice and w._voice_combo:
        for i, v in enumerate(voices):
            if v["name"] == last_voice:
                w._voice_combo.setCurrentIndex(i)
                p.set_voice(last_voice)
                break
        else:
            if voices:
                p.set_voice(voices[0]["name"])
    elif voices:
        p.set_voice(voices[0]["name"])

    if verbose:
        _setup_logging()

    return app.exec()


def _setup_logging() -> None:
    """Configure logging to the XDG cache log file."""
    import logging

    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    log_path = Path(base) / "text-to-speech" / "text-to-speech.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        force=True,  # the GUI may already have handlers installed by imports
    )
