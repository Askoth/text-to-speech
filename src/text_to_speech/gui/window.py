"""Qt window: QMainWindow with top toolbar, middle reader, bottom controls.

Adaptive layout: below width/height thresholds the toolbar collapses to icon-only
and player controls switch to a single compact row. All breakpoints live in
:data:`BREAKPOINTS` for easy tuning.
"""

from pathlib import Path

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import player as _player_mod
from . import strings as _strings
from .player import State


# --- Adaptive breakpoints (tune after it works) ---
class BREAKPOINTS:
    toolbar_icon_only_below = 560  # px width → hide toolbar text labels
    controls_single_row_below = 520  # px width → single-row controls
    controls_compact_below = 400  # px height → hide keyboard hint


class _MainWindow(QMainWindow):
    """``QMainWindow`` that re-runs the adaptive layout on every resize."""

    def __init__(self):
        super().__init__()
        self._window = None  # Window instance, wired in Window.build()

    def resizeEvent(self, _event) -> None:
        if self._window is not None:
            self._window.apply_adaptive_layout()

    def closeEvent(self, _event) -> None:
        if self._window is not None:
            self._window.release_player()


class Window:
    """QMainWindow with toolbar / reader / bottom-bar layout."""

    def __init__(self, p: _player_mod.Player):
        self._player = p

        self._main = None
        self._layout = None
        self._reader_content = None
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
        self._banner_close = None
        self._kbd_hint = None
        self._empty_title = None
        self._empty_sub = None
        self._btn_max: dict[str, QSize] = {}

        self._shortcuts: list[QShortcut] = []

    def build(self) -> None:
        """Construct the full widget tree and show the window."""
        w = _MainWindow()
        w.setMinimumSize(480, 360)
        self._main = w
        w._window = self

        central = QWidget()
        central.setObjectName("CentralArea")
        w.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self._layout = layout

        self._build_banner()
        self._build_top_bar()
        self._build_reader_area()
        self._build_bottom_bar()

        for widget in (self._banner, self._top_bar, self._reader_area, self._bottom_bar):
            layout.addWidget(widget)

        self._bind_keyboard()

        if self._banner:
            self._banner.setVisible(False)
        self.show_empty_state()
        self.apply_adaptive_layout()
        w.show()

    def _build_top_bar(self) -> None:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._file_name_label = QLabel("")
        self._file_name_label.setObjectName("FileNameLabel")
        self._file_name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._voice_combo = QComboBox()
        self._voice_combo.setObjectName("VoiceCombo")

        self._save_btn = QPushButton(_strings.t("toolbar.saveBtn"))
        self._save_btn.setObjectName("SaveButton")
        self._save_btn.setToolTip(_strings.t("toolbar.saveAria"))

        row = QHBoxLayout(bar)
        row.addWidget(self._file_name_label)
        row.addWidget(self._voice_combo)
        row.addWidget(self._save_btn)

        self._top_bar = bar

    def _build_reader_area(self) -> None:
        scroll = QScrollArea()
        scroll.setObjectName("ReaderScroll")
        scroll.setVerticalScrollBarPolicy(1)  # 1 = ScrollBarOff
        scroll.setHorizontalScrollBarPolicy(1)  # 1 = ScrollBarOff

        card = QFrame()
        card.setObjectName("ReaderCard")
        card_layout = QVBoxLayout(card)

        self._paragraph_label = QLabel("")
        self._paragraph_label.setObjectName("ParagraphText")
        self._paragraph_label.setWordWrap(True)
        self._paragraph_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        card_layout.addWidget(self._paragraph_label)

        self._empty_state = QFrame()
        self._empty_state.setObjectName("EmptyState")

        empty_title = QLabel(_strings.t("empty.title"))
        empty_title.setObjectName("EmptyStateLabel")
        empty_sub = QLabel(_strings.t("empty.formats"))
        empty_sub.setObjectName("EmptyStateFormats")

        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_sub)

        content = QWidget()
        content.setObjectName("ReaderContent")
        inner = QVBoxLayout(content)
        inner.addWidget(card)
        inner.addWidget(self._empty_state)
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)

        self._reader_card = card
        self._reader_area = scroll
        self._reader_content = content
        self._empty_title = empty_title
        self._empty_sub = empty_sub

    def _build_bottom_bar(self) -> None:
        bar = QFrame()
        bar.setObjectName("BottomBar")
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("ProgressBar")

        self._counter_label = QLabel(_strings.t("progress.counterEmpty"))
        self._counter_label.setObjectName("CounterLabel")

        for attr, name, aria in (
            ("_btn_start", "StartButton", "player.startTitle"),
            ("_btn_prev", "PrevButton", "player.prevTitle"),
            ("_btn_play", "PlayButton", "player.playTitle"),
            ("_btn_stop", "StopButton", "player.stopTitle"),
            ("_btn_next", "NextButton", "player.nextTitle"),
            ("_btn_repeat", "RepeatButton", "player.repeatTitle"),
        ):
            btn = QPushButton()
            btn.setObjectName(name)
            btn.setToolTip(_strings.t(aria))
            self._btn_max[name] = btn.maximumSize()
            setattr(self, attr, btn)

        self._btn_play.setText(_strings.t("label.playPause"))
        self._btn_start.setText(_strings.t("label.start"))
        self._btn_prev.setText(_strings.t("label.prev"))
        self._btn_stop.setText(_strings.t("label.stop"))
        self._btn_next.setText(_strings.t("label.next"))
        self._btn_repeat.setText(_strings.t("label.repeat"))

        self._kbd_hint = QLabel(
            f"{_strings.t('kbd.space')} {_strings.t('kbd.playPause')}  "
            f"\u2190 {_strings.t('kbd.prev')}  "
            f"\u2192 {_strings.t('kbd.next')}  "
            f"R {_strings.t('kbd.repeat')}"
        )
        self._kbd_hint.setObjectName("KeyboardHint")

        row = QHBoxLayout(bar)
        row.addWidget(self._progress_bar)
        row.addWidget(self._counter_label)
        for btn in self._control_buttons():
            row.addWidget(btn)
        row.addWidget(self._kbd_hint)

        self._bottom_bar = bar

    def _control_buttons(self) -> tuple[QPushButton, ...]:
        """The six player controls, in display order."""
        return (
            self._btn_start,
            self._btn_prev,
            self._btn_play,
            self._btn_stop,
            self._btn_next,
            self._btn_repeat,
        )

    def _build_banner(self) -> None:
        self._banner = QFrame()
        self._banner.setObjectName("StatusBanner")
        self._banner_label = QLabel("")
        self._banner_label.setObjectName("BannerLabel")
        self._banner_close = QPushButton()
        self._banner_close.setObjectName("BannerCloseButton")
        self._banner_close.setText("\u2715")
        self._banner_close.setToolTip(_strings.t("error.closeAria"))
        self._banner_close.clicked.connect(self.dismiss_banner)

        row = QHBoxLayout(self._banner)
        row.addWidget(self._banner_label)
        row.addWidget(self._banner_close)

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
            self._btn_play.setText(
                _strings.t("player.loadingAria") if active else _strings.t("label.playPause")
            )

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
        else:
            self._expand_toolbar()
        if single_row:
            self._collapse_controls()
        else:
            self._expand_controls()

    def _collapse_toolbar(self) -> None:
        """Hide text labels in toolbar (icon-only mode)."""
        if self._file_name_label:
            self._file_name_label.setVisible(False)

    def _expand_toolbar(self) -> None:
        """Restore toolbar text labels."""
        if self._file_name_label:
            self._file_name_label.setVisible(True)

    def _collapse_controls(self) -> None:
        """Cap player controls so all six fit one row."""
        for btn in self._control_buttons():
            btn.setMaximumSize(QSize(44, 44))
        if self._btn_play:
            self._btn_play.setMaximumSize(QSize(56, 56))

    def _expand_controls(self) -> None:
        """Restore the default (unbounded) control sizes."""
        for btn in self._control_buttons():
            btn.setMaximumSize(self._btn_max[btn.objectName()])

    def open_file(self) -> str:
        """Show file dialog, load the chosen file, reset player. Returns path or ''."""
        if self._main is None:
            return ""
        path, _ = QFileDialog.getOpenFileName(
            self._main,
            _strings.t("toolbar.chooseFileAria"),
            "",
            "Text files (*.md *.txt *.epub *.docx *.html *.htm *.pdf)",
        )
        if not path:
            return ""
        self._player.load_file(Path(path))
        if self._file_name_label:
            self._file_name_label.setText(Path(path).name)
        self.hide_empty_state()
        self.update_progress()
        self.sync_controls()
        self._player.prefetch_first()
        return path

    def save_mp3(self) -> None:
        """Show save dialog, synthesize all paragraphs, write MP3."""
        if self._main is None or self._player.total == 0:
            return
        path, _ = QFileDialog.getSaveFileName(
            self._main,
            _strings.t("toolbar.saveTitle"),
            "",
            "MP3 files (*.mp3)",
        )
        if not path:
            return
        self._save_btn.setEnabled(False)
        self.set_spinner(True)
        self.show_banner(
            _strings.t("toolbar.saveBtn"),
            severity="info",
        )

        voice = self._player.voice

        mp3_data = self._player._engine.save_all(voice)

        with open(path, "wb") as f:
            f.write(mp3_data)

        self.set_spinner(False)
        self._save_btn.setEnabled(True)
        self.show_banner(f"Saved to {path}", severity="info")

    def dismiss_banner(self) -> None:
        """Hide the status banner."""
        if self._banner:
            self._banner.setVisible(False)
        if self._banner_label:
            self._banner_label.setText("")

    def release_player(self) -> None:
        """Release player resources when the window is closed."""
        self._player.shutdown()
