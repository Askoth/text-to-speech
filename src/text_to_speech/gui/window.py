"""Qt window: QMainWindow with top toolbar, middle reader, bottom controls.

Adaptive layout: below width/height thresholds the toolbar collapses to icon-only
and player controls switch to a single compact row. All breakpoints live in
:data:`BREAKPOINTS` for easy tuning.
"""

from enum import Enum

from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
)

from . import player as _player_mod
from . import strings as _strings


# --- Adaptive breakpoints (tune after it works) ---
class BREAKPOINTS:
    toolbar_icon_only_below = 560  # px width → hide toolbar text labels
    controls_single_row_below = 520  # px width → single-row controls
    controls_compact_below = 400  # px height → hide keyboard hint


class State(Enum):
    IDLE = "idle"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"


class Window:
    """QMainWindow with toolbar / reader / bottom-bar layout."""

    def __init__(self, p: _player_mod.Player):
        self._player = p

        self._main = None
        self._top_bar = None
        self._bottom_bar = None
        self._reader_area = None
        self._reader_card = None
        self._empty_state = None
        self._paragraph_label = None
        self._progress_bar = None
        self._counter_label = None
        self._btn_start = None
        self._btn_prev = None
        self._btn_play = None
        self._btn_stop = None
        self._btn_next = None
        self._btn_repeat = None
        self._voice_combo = None
        self._file_name_label = None
        self._save_btn = None
        self._banner = None
        self._banner_label = None
        self._kbd_hint = None

        self._shortcuts: list[QShortcut] = []

    def build(self) -> None:
        """Construct the full widget tree."""
        from PyQt5.QtWidgets import QMainWindow

        w = QMainWindow()
        w.setMinimumSize(480, 360)
        self._main = w

        self._build_top_bar()
        self._build_reader_area()
        self._build_bottom_bar()
        self._build_banner()
        self._bind_keyboard()

    def _build_top_bar(self) -> None:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._file_name_label = QLabel("")
        self._file_name_label.setObjectName("FileNameLabel")

        self._voice_combo = QComboBox()
        self._voice_combo.setObjectName("VoiceCombo")

        self._save_btn = QPushButton()
        self._save_btn.setObjectName("SaveButton")

        self._top_bar = bar

    def _build_reader_area(self) -> None:
        scroll = QScrollArea()
        scroll.setObjectName("ReaderScroll")
        scroll.setVerticalScrollBarPolicy(1)  # Never
        scroll.setHorizontalScrollBarPolicy(1)  # Never

        card = QFrame()
        card.setObjectName("ReaderCard")

        self._paragraph_label = QLabel("")
        self._paragraph_label.setObjectName("ParagraphText")
        self._paragraph_label.setWordWrap(True)
        self._paragraph_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._empty_state = QFrame()
        self._empty_state.setObjectName("EmptyState")

        empty_title = QLabel(_strings.t("empty.title"))
        empty_title.setObjectName("EmptyStateLabel")
        empty_sub = QLabel(_strings.t("empty.formats"))
        empty_sub.setObjectName("EmptyStateFormats")

        self._reader_card = card
        self._reader_area = scroll

    def _build_bottom_bar(self) -> None:
        bar = QFrame()
        bar.setObjectName("BottomBar")
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("ProgressBar")

        self._counter_label = QLabel(_strings.t("progress.counterEmpty"))
        self._counter_label.setObjectName("CounterLabel")

        self._btn_start = QPushButton()
        self._btn_start.setObjectName("StartButton")
        self._btn_prev = QPushButton()
        self._btn_prev.setObjectName("PrevButton")
        self._btn_play = QPushButton()
        self._btn_play.setObjectName("PlayButton")
        self._btn_stop = QPushButton()
        self._btn_stop.setObjectName("StopButton")
        self._btn_next = QPushButton()
        self._btn_next.setObjectName("NextButton")
        self._btn_repeat = QPushButton()
        self._btn_repeat.setObjectName("RepeatButton")

        self._kbd_hint = QLabel(
            f"{_strings.t('kbd.space')} {_strings.t('kbd.playPause')}  "
            f"\u2190 {_strings.t('kbd.prev')}  "
            f"\u2192 {_strings.t('kbd.next')}  "
            f"R {_strings.t('kbd.repeat')}"
        )
        self._kbd_hint.setObjectName("KeyboardHint")

        self._bottom_bar = bar

    def _build_banner(self) -> None:
        self._banner = QFrame()
        self._banner.setObjectName("StatusBanner")
        self._banner_label = QLabel("")
        self._banner_label.setObjectName("BannerLabel")

    def _bind_keyboard(self) -> None:
        if self._main is None:
            return
        for key, action in (
            (" ", self._toggle_play_pause),
            ("Left", self._prev),
            ("Right", self._next),
            ("r", self._repeat),
            ("R", self._repeat),
        ):
            sc = QShortcut(key, self._main)
            sc.activated.connect(action)
            self._shortcuts.append(sc)

    def _toggle_play_pause(self) -> None:
        if self._player.state == State.PLAYING:
            self._player.pause()
        else:
            self._player.play()

    def _prev(self) -> None:
        self._player.prev()

    def _next(self) -> None:
        self._player.next()

    def _repeat(self) -> None:
        self._player.repeat()

    def update_paragraph(self, text: str) -> None:
        """Update the reader card text."""
        if self._paragraph_label:
            self._paragraph_label.setText(text)

    def update_progress(self) -> None:
        """Sync progress bar + counter to player state."""
        p = self._player
        if p.total == 0:
            if self._progress_bar:
                self._progress_bar.setRange(0, 0)
                self._progress_bar.setValue(0)
            if self._counter_label:
                self._counter_label.setText(_strings.t("progress.counterEmpty"))
            return

        pct = int(p.current_idx / max(p.total - 1, 1) * 100)
        if self._progress_bar:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(pct)
        if self._counter_label:
            self._counter_label.setText(
                _strings.t("progress.counter", current=p.current_idx + 1, total=p.total)
            )

    def sync_controls(self) -> None:
        """Enable/disable player buttons based on state."""
        p = self._player

        for btn, is_enabled in (
            (self._btn_start, p.start_enabled()),
            (self._btn_prev, p.prev_enabled()),
            (self._btn_play, p.play_enabled()),
            (self._btn_stop, p.stop_enabled()),
            (self._btn_next, p.next_enabled()),
            (self._btn_repeat, p.repeat_enabled()),
        ):
            if btn is None:
                continue
            btn.setEnabled(is_enabled)

    def show_empty_state(self) -> None:
        """Show the empty-state card, hide paragraph."""
        if self._reader_card:
            self._reader_card.setVisible(False)
        if self._empty_state:
            self._empty_state.setVisible(True)

    def hide_empty_state(self) -> None:
        """Hide empty-state, show paragraph card."""
        if self._empty_state:
            self._empty_state.setVisible(False)
        if self._reader_card:
            self._reader_card.setVisible(True)

    def set_spinner(self, active: bool) -> None:
        """Toggle spinner indicator on the play button."""
        if self._btn_play:
            if active:
                self._btn_play.setText(_strings.t("player.loadingAria"))
            else:
                self._btn_play.setText("")

    def show_banner(self, message: str, severity: str = "error") -> None:
        """Display the top status banner with a message."""
        if self._banner_label:
            self._banner_label.setText(message)
        if self._banner:
            self._banner.setVisible(True)

    def apply_adaptive_layout(self) -> None:
        """Collapse toolbar/controls based on current window size."""
        if self._main is None:
            return
        w = self._main.width()
        h = self._main.height()

        icon_only = w < BREAKPOINTS.toolbar_icon_only_below
        single_row = w < BREAKPOINTS.controls_single_row_below
        hide_hint = h < BREAKPOINTS.controls_compact_below

        if self._kbd_hint:
            self._kbd_hint.setVisible(not hide_hint)

        if icon_only:
            self._collapse_toolbar()
        if single_row:
            self._collapse_controls()

    def _collapse_toolbar(self) -> None:
        """Hide text labels in toolbar (icon-only mode)."""
        if self._file_name_label:
            self._file_name_label.setVisible(False)

    def _collapse_controls(self) -> None:
        """Switch player controls to compact single-row layout."""
        pass
