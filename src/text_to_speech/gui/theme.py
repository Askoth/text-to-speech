"""Qt-side theme layer: live ``theme.toml`` → ``QColor`` map.

The live file uses Noctalia's standard Material color tokens, so a Noctalia
template can render it 1:1 from the active palette (one
``{{ colors.<token>.default.hex }}`` per role). Beyond that, this module does
no color derivation — only the fixed state opacities in :data:`STATE`, which
``styles.py`` applies for the derived UI states (dim text, accent glow,
progress track, accent hover/pressed tints).
"""

from dataclasses import dataclass

from PyQt5.QtGui import QColor

from src.config import THEME_ROLES, load_theme, parse_color


@dataclass(frozen=True)
class State:
    """Fixed state-layer opacities applied by ``styles.py`` over palette roles."""

    text_dim: float = 0.40  # on_surface → hint / counter text
    glow: float = 0.15  # primary → accent glow (active language button)
    progress_track: float = 0.07  # on_surface → progress bar track
    accent_hover: float = 0.15  # on_primary over primary → play button hover
    accent_pressed: float = 0.30  # on_primary over primary → play button pressed


STATE = State()


@dataclass(frozen=True)
class Theme:
    """Concrete role → ``QColor`` map, validated and seed-fallback-applied."""

    colors: dict[str, QColor]
    warnings: tuple[str, ...]

    def color(self, role: str) -> QColor:
        return self.colors[role]


def load() -> Theme:
    """Read the live theme into a :class:`Theme` (seeding is done by the caller)."""
    values, warnings = load_theme()
    colors: dict[str, QColor] = {}
    for role in THEME_ROLES:
        r, g, b, a = parse_color(values[role])
        colors[role] = QColor(r, g, b, round(a * 255))
    return Theme(colors, tuple(warnings))
