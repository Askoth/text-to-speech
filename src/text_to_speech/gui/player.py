"""Qt-side player: QMediaPlayer + TTSEngine integration.

Mirrors the web player 1:1: states (idle/loading/playing/paused), 6 controls
(start, prev, play/pause, stop, next, repeat), auto-advance on EndOfMedia,
prefetch, spinner while synthesizing, graceful no-backend handling.
"""

import contextlib
import os
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path

from PyQt5.QtCore import QObject, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

from src.tts_engine import TTSEngine


class State(Enum):
    IDLE = "idle"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"


class Player(QObject):
    """Manages QMediaPlayer playback of synthesized paragraphs.

    ``audio_ready`` marshals synthesized bytes from the synthesis worker back to
    the main thread: QMediaPlayer is not thread-safe, so every Qt call happens
    in the connected slot, never in a worker. ``synthesis_failed`` is emitted
    when a synthesis job raises, so the window can surface the error.
    """

    audio_ready = pyqtSignal(object, int)
    synthesis_failed = pyqtSignal(str)

    def __init__(self, engine: TTSEngine):
        super().__init__()
        self._engine = engine
        self._media = QMediaPlayer()
        self._media.mediaStatusChanged.connect(self._on_media_status)

        self._state: State = State.IDLE
        self._current_idx: int = 0
        self._total: int = 0
        self._paragraphs: list[str] = []
        self._voice: str = ""
        self._filename: str = ""

        self._temp_file: str | None = None
        self._prefetch_idx: int = -1

        self._spinner_active: bool = False

        self.audio_ready.connect(self._on_audio_ready)
        self.synthesis_failed.connect(self._on_synthesis_failure)

    @property
    def state(self) -> State:
        return self._state

    @property
    def current_idx(self) -> int:
        return self._current_idx

    @property
    def total(self) -> int:
        return self._total

    @property
    def paragraphs(self) -> list[str]:
        return self._paragraphs

    @property
    def filename(self) -> str:
        return self._filename

    @property
    def spinner_active(self) -> bool:
        return self._spinner_active

    @property
    def voice(self) -> str:
        return self._voice

    def set_voice(self, voice: str) -> None:
        self._voice = voice
        self._clear_prefetch()

    def load_file(self, path: Path) -> list[str]:
        """Load a file, populate paragraphs, reset to idle."""
        self._paragraphs = self._engine.load_file(path)
        self._total = len(self._paragraphs)
        self._filename = path.name
        self._current_idx = 0
        self._state = State.IDLE
        self._clear_prefetch()
        self._media.stop()
        self._cleanup_temp()
        return self._paragraphs

    def prefetch_first(self) -> None:
        """Start background synthesis of paragraph 0 (called after load_file)."""
        if self._total > 0 and self._voice:
            self._engine.prefetch(0, self._voice)
            self._prefetch_idx = 0

    def play(self) -> None:
        """Start or resume playback."""
        if self._total == 0:
            return
        if self._state == State.PLAYING:
            return
        if self._state == State.PAUSED and self._temp_file:
            self._media.play()
            self._state = State.PLAYING
            return
        self._load_and_play(self._current_idx)

    def pause(self) -> None:
        if self._state != State.PLAYING:
            return
        self._media.pause()
        self._state = State.PAUSED

    def stop(self) -> None:
        """Stop playback and reset to first paragraph."""
        self._media.stop()
        self._cleanup_temp()
        self._current_idx = 0
        self._state = State.IDLE
        self._clear_prefetch()

    def next(self) -> None:
        if self._total == 0:
            return
        if self._current_idx >= self._total - 1:
            return
        was_playing = self._state == State.PLAYING
        self._media.pause()
        self._current_idx += 1
        self._clear_prefetch()
        if was_playing:
            self._load_and_play(self._current_idx)
        else:
            self._state = State.IDLE

    def prev(self) -> None:
        if self._total == 0:
            return
        if self._current_idx <= 0:
            return
        was_playing = self._state == State.PLAYING
        self._media.pause()
        self._current_idx -= 1
        self._clear_prefetch()
        if was_playing:
            self._load_and_play(self._current_idx)
        else:
            self._state = State.IDLE

    def repeat(self) -> None:
        """Replay current paragraph from the beginning."""
        if self._total == 0:
            return
        self._media.pause()
        self._clear_prefetch()
        self._load_and_play(self._current_idx)

    def go_to(self, index: int) -> None:
        """Jump to a specific paragraph."""
        if self._total == 0:
            return
        idx = max(0, min(index, self._total - 1))
        was_playing = self._state == State.PLAYING
        self._media.pause()
        self._current_idx = idx
        self._clear_prefetch()
        if was_playing:
            self._load_and_play(self._current_idx)
        else:
            self._state = State.IDLE

    def _load_and_play(self, idx: int) -> None:
        """Synthesize (if needed) and play paragraph at idx."""
        self._state = State.LOADING
        self._spinner_active = True

        voice = self._voice
        future = _executor.submit(self._engine.get_audio, idx, voice)
        future.add_done_callback(lambda f: self._hand_off(f, idx))

    def _hand_off(self, future, idx: int) -> None:
        """Runs on the worker thread: only extract the payload and emit it."""
        try:
            payload = future.result()
        except Exception as e:
            self.synthesis_failed.emit(str(e))
            return
        self.audio_ready.emit(payload, idx)

    def _on_audio_ready(self, mp3_bytes: bytes, idx: int) -> None:
        """Main-thread slot for :attr:`audio_ready` — feed audio to QMediaPlayer."""
        self._spinner_active = False
        if self._state != State.LOADING:
            return
        self._write_and_play(mp3_bytes, idx)

    def _on_synthesis_failure(self, message: str) -> None:
        """Main-thread slot for :attr:`synthesis_failed` — stop loading, no audio."""
        self._spinner_active = False
        self._state = State.IDLE

    def _write_and_play(self, mp3_bytes: bytes, idx: int) -> None:
        """Write MP3 to temp file and start playback."""
        self._cleanup_temp()
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="tts_")
        try:
            os.write(fd, mp3_bytes)
        finally:
            os.close(fd)
        self._temp_file = path

        self._media.setMedia(QMediaContent(QUrl(f"file://{path}")))
        self._media.play()
        self._state = State.PLAYING

        self._prefetch_next(idx)

    def _prefetch_next(self, idx: int) -> None:
        """Start background synthesis for next paragraph."""
        next_idx = idx + 1
        if next_idx >= self._total:
            return
        if self._prefetch_idx == next_idx:
            return
        self._prefetch_idx = next_idx
        self._engine.prefetch(next_idx, self._voice)

    def _clear_prefetch(self) -> None:
        self._prefetch_idx = -1

    def _cleanup_temp(self) -> None:
        if self._temp_file:
            with contextlib.suppress(OSError):
                os.unlink(self._temp_file)
            self._temp_file = None

    def _on_media_status(self, status: int) -> None:
        """Handle QMediaPlayer mediaStatusChanged signal."""
        if status == QMediaPlayer.EndOfMedia:
            self._auto_advance()
        elif status == QMediaPlayer.NoMedia and self._state == State.PLAYING:
            self._state = State.IDLE

    def playback_error(self) -> bool:
        """True if QMediaPlayer reports an error (no GStreamer backend, etc.)."""
        return self._media.error() != QMediaPlayer.NoError

    def _auto_advance(self) -> None:
        """Advance to next paragraph on EndOfMedia (unless paused)."""
        if self._state != State.PLAYING:
            return
        if self._current_idx < self._total - 1:
            self._current_idx += 1
            self._load_and_play(self._current_idx)
        else:
            self._state = State.IDLE

    def controls_enabled(self) -> bool:
        return self._total > 0

    def prev_enabled(self) -> bool:
        return self._total > 0 and self._current_idx > 0

    def next_enabled(self) -> bool:
        return self._total > 0 and self._current_idx < self._total - 1

    def start_enabled(self) -> bool:
        return self._total > 0 and self._current_idx > 0

    def stop_enabled(self) -> bool:
        return self._total > 0 and self._state != State.IDLE

    def play_enabled(self) -> bool:
        return self._total > 0 and self._state != State.LOADING

    def repeat_enabled(self) -> bool:
        return self._total > 0

    def shutdown(self) -> None:
        """Release the synthesis pool (called from the window's closeEvent)."""
        _executor.shutdown(wait=False)

    def save_all(self, voice: str, progress_cb: Callable[[int], None] | None = None) -> bytes:
        """Synthesize every paragraph and return the concatenated MP3.

        The engine runs the whole file as one job, so the only progress it can
        report is completion: ``progress_cb`` receives 100 when the job is done.
        """
        data = self._engine.save_all(voice)
        if progress_cb is not None:
            progress_cb(100)
        return data


_executor = ThreadPoolExecutor(max_workers=2)
