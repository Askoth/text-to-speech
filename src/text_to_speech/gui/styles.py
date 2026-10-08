"""Qt palette + stylesheet built from the theme role map.

Every color here is either a palette role read verbatim or a
:data:`theme.STATE` opacity applied to a role — no other derivation.
"""

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication

from . import theme

_CSS = """
QMainWindow {
    background: @surface@;
}
QFrame#TopBar, QFrame#BottomBar {
    background: @surface_container_high@;
}
QScrollArea {
    background: @surface@;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: @surface@;
}
QFrame#ReaderCard {
    background: @surface_container@;
    border: 1px solid @outline@;
    border-radius: 12px;
}
QFrame#EmptyState {
    background: @surface_container@;
    border: 1px solid @outline@;
    border-radius: 12px;
}
QLabel {
    color: @on_surface@;
}
QLabel#CounterLabel, QLabel#EmptyStateLabel {
    font-family: monospace;
}
QLabel#CounterLabel, QLabel#HintLabel {
    color: @text_dim@;
}
QPushButton {
    background: @surface_container@;
    color: @on_surface@;
    border: 1px solid @outline@;
    border-radius: 8px;
    padding: 6px 14px;
}
QPushButton:hover {
    background: @hover@;
    color: @on_hover@;
}
QPushButton:pressed {
    background: @hover@;
    color: @on_hover@;
    border-color: @outline_variant@;
}
QPushButton:disabled {
    color: @text_dim@;
    border-color: @outline_variant@;
}
QPushButton#PlayButton {
    background: @primary@;
    color: @on_primary@;
    border: none;
    border-radius: 14px;
    padding: 10px 18px;
}
QPushButton#PlayButton:hover {
    background: @accent_hover@;
}
QPushButton#PlayButton:pressed {
    background: @accent_pressed@;
}
QComboBox {
    background: @surface_container@;
    color: @on_surface@;
    border: 1px solid @outline@;
    border-radius: 8px;
    padding: 4px 10px;
}
QComboBox QAbstractItemView {
    background: @surface_container@;
    color: @on_surface@;
    border: 1px solid @outline@;
    selection-background-color: @hover@;
    selection-color: @on_hover@;
}
QProgressBar#ProgressBar {
    background: @track@;
    border-radius: 4px;
}
QProgressBar#ProgressBar::chunk {
    background: @primary@;
    border-radius: 4px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
}
QScrollBar::handle:vertical {
    background: @outline_variant@;
    border-radius: 5px;
    min-height: 32px;
}
QScrollBar::handle:horizontal {
    background: @outline_variant@;
    border-radius: 5px;
    min-width: 32px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
"""


def _hex(color: QColor) -> str:
    return color.name().upper()


def _rgba(color: QColor) -> str:
    a = color.alpha()
    if a == 255:
        return _hex(color)
    alpha = f"{a / 255:.2f}".rstrip("0").rstrip(".")
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


def _alpha(color: QColor, a: float) -> QColor:
    return QColor(color.red(), color.green(), color.blue(), round(a * 255))


def _overlay(base: QColor, over: QColor, a: float) -> QColor:
    return QColor(
        int(base.red() + (over.red() - base.red()) * a),
        int(base.green() + (over.green() - base.green()) * a),
        int(base.blue() + (over.blue() - base.blue()) * a),
    )


def build_palette(t: theme.Theme) -> QPalette:
    """Map the role colors onto :class:`QPalette` roles."""
    c = t.color
    p = QPalette()
    p.setColor(QPalette.Window, c("surface"))
    p.setColor(QPalette.WindowText, c("on_surface"))
    p.setColor(QPalette.Base, c("surface_container"))
    p.setColor(QPalette.AlternateBase, c("surface_container_high"))
    p.setColor(QPalette.Text, c("on_surface"))
    p.setColor(QPalette.Button, c("surface_container"))
    p.setColor(QPalette.ButtonText, c("on_surface"))
    p.setColor(QPalette.BrightText, c("on_surface"))
    p.setColor(QPalette.Highlight, c("hover"))
    p.setColor(QPalette.HighlightedText, c("on_hover"))
    p.setColor(QPalette.ToolTipBase, c("surface_container"))
    p.setColor(QPalette.ToolTipText, c("on_surface"))
    p.setColor(QPalette.PlaceholderText, _alpha(c("on_surface"), theme.STATE.text_dim))
    p.setColor(QPalette.Link, c("primary"))
    p.setColor(QPalette.Mid, c("outline_variant"))
    p.setColor(QPalette.Midlight, c("outline"))
    return p


def build_stylesheet(t: theme.Theme) -> str:
    """Full ``QApplication`` stylesheet (concrete colors, derived states inlined)."""
    s = theme.STATE
    colors: dict[str, QColor] = dict(t.colors)
    colors["text_dim"] = _alpha(colors["on_surface"], s.text_dim)
    colors["glow"] = _alpha(colors["primary"], s.glow)
    colors["track"] = _alpha(colors["on_surface"], s.progress_track)
    colors["accent_hover"] = _overlay(colors["primary"], colors["on_primary"], s.accent_hover)
    colors["accent_pressed"] = _overlay(colors["primary"], colors["on_primary"], s.accent_pressed)
    css = _CSS
    for name, color in colors.items():
        css = css.replace(f"@{name}@", _rgba(color))
    return css


def banner_style(t: theme.Theme, severity: str = "error") -> str:
    """Style for ``QFrame#StatusBanner``. ``severity``: 'error' or 'info'."""
    if severity == "error":
        bg, fg, bd = t.color("error_container"), t.color("on_error_container"), t.color("error")
    else:
        bg, fg, bd = t.color("surface_container"), t.color("on_surface"), t.color("outline")
    return (
        "QFrame#StatusBanner { "
        f"background: {_hex(bg)}; "
        f"color: {_hex(fg)}; "
        f"border: 1px solid {_hex(bd)}; "
        "border-radius: 8px; }"
    )


def apply(t: theme.Theme) -> None:
    """Apply the palette + stylesheet to the running ``QApplication``."""
    app = QApplication.instance()
    app.setPalette(build_palette(t))
    app.setStyleSheet(build_stylesheet(t))
