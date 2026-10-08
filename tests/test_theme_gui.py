"""Tests for the Qt theme layer (``gui/theme.py`` + ``gui/styles.py``).

Skipped when PyQt5 is not installed (it is not a declared dependency until T9).
"""

import pytest

py = pytest.importorskip("PyQt5.QtGui")

from PyQt5.QtGui import QColor, QPalette

from src.config import THEME_ROLES
from src.text_to_speech.gui import styles, theme


def _theme(tmp_path, monkeypatch, body: str = "") -> theme.Theme:
    if body:
        d = tmp_path / "text-to-speech"
        d.mkdir(exist_ok=True)
        (d / "theme.toml").write_text(body)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return theme.load()


class TestTheme:
    def test_loads_all_roles(self, tmp_path, monkeypatch):
        t = _theme(tmp_path, monkeypatch)  # no live file → whole-seed fallback
        assert set(t.colors) == set(THEME_ROLES)
        assert all(isinstance(c, QColor) for c in t.colors.values())
        assert t.warnings == ("theme.toml is missing or invalid — using the built-in theme.",)
        assert t.color("surface") == QColor("#070722")

    def test_color_alpha(self, tmp_path, monkeypatch):
        body = 'surface = "#11223380"\n'
        t = _theme(tmp_path, monkeypatch, body)
        assert t.color("surface").alpha() == 0x80

    def test_state_defaults(self):
        s = theme.STATE
        assert s.text_dim == 0.40
        assert s.glow == 0.15
        assert s.progress_track == 0.07
        assert 0 < s.accent_hover < s.accent_pressed < 1


class TestStyles:
    def test_build_palette(self, tmp_path, monkeypatch):
        t = _theme(tmp_path, monkeypatch)
        p = styles.build_palette(t)
        assert p.color(QPalette.Window).name() == "#070722"
        assert p.color(QPalette.Text).name() == "#f3edf7"
        assert p.color(QPalette.Highlight).name() == "#9bfece"
        assert p.color(QPalette.HighlightedText).name() == "#0e0e43"

    def test_stylesheet_has_concrete_colors(self, tmp_path, monkeypatch):
        css = styles.build_stylesheet(_theme(tmp_path, monkeypatch))
        # roles appear verbatim…
        assert "#070722" in css
        assert "#FFF59B" in css
        # …and state layers are inlined rgba() with the STATE opacities
        assert "rgba(243, 237, 247, 0.4)" in css  # on_surface @ text_dim
        assert "rgba(243, 237, 247, 0.07)" in css  # on_surface @ progress_track
        assert "QPushButton#PlayButton" in css
        assert "QProgressBar#ProgressBar" in css

    def test_banner_style(self, tmp_path, monkeypatch):
        t = _theme(tmp_path, monkeypatch)
        err = styles.banner_style(t, "error")
        assert "#8F0118" in err and "#FECDD4" in err and "#FD4663" in err
        info = styles.banner_style(t, "info")
        assert "#11112D" in info and "#F3EDF7" in info and "#51589B" in info
