"""CLI validate — strict check of live settings.toml + theme.toml."""

import sys
import tomllib

from src.config import THEME_ROLES, parse_color, settings_path, theme_path


def _validate_settings() -> list[str]:
    """Strict validation of the live settings file. Returns error strings."""
    path = settings_path()
    if not path.exists():
        return [f"{path}: file not found"]
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        return [f"{path}: TOML parse error — {e}"]
    except OSError as e:
        return [f"{path}: cannot read — {e}"]

    from src.config import validate_settings

    return validate_settings(data)


def _validate_theme() -> list[str]:
    """Strict validation of the live theme file. Returns error strings."""
    path = theme_path()
    if not path.exists():
        return [f"{path}: file not found"]
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        return [f"{path}: TOML parse error — {e}"]
    except OSError as e:
        return [f"{path}: cannot read — {e}"]

    errors: list[str] = []
    for role in THEME_ROLES:
        if role not in data:
            errors.append(f"{path}: missing role '{role}'")
        elif parse_color(data[role]) is None:
            errors.append(f"{path}: '{role}' = {data[role]!r} is not a valid color")
    for key in data:
        if key not in THEME_ROLES:
            errors.append(f"{path}: unknown key '{key}'")
    return errors


def validate() -> int:
    """Run strict validation. Returns exit code (0=valid, 1=invalid)."""
    errors = _validate_settings() + _validate_theme()
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0
