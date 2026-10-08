"""Tests for the theme file layer: ``parse_color`` and ``load_theme``.

No Qt involved — this is the shared, pure part of the theme contract.
"""

from src.config import (
    _SEED_THEME,
    THEME_ROLES,
    load_theme,
    parse_color,
)


def _seed_values() -> dict[str, str]:
    import tomllib

    with open(_SEED_THEME, "rb") as fh:
        return dict(tomllib.load(fh))


class TestParseColor:
    def test_rgb_short(self):
        assert parse_color("#abc") == (0xAA, 0xBB, 0xCC, 1.0)

    def test_hex6(self):
        assert parse_color("#112233") == (0x11, 0x22, 0x33, 1.0)

    def test_hex8_alpha(self):
        assert parse_color("#11223380") == (0x11, 0x22, 0x33, 0x80 / 255)

    def test_case_insensitive(self):
        assert parse_color("#ABCDEF") == (0xAB, 0xCD, 0xEF, 1.0)

    def test_rgba(self):
        assert parse_color("rgba(1, 2, 3, 0.5)") == (1, 2, 3, 0.5)

    def test_rgba_whitespace(self):
        assert parse_color("rgba( 1 ,2 ,3, 1 )") == (1, 2, 3, 1.0)

    def test_invalid(self):
        assert parse_color(None) is None
        assert parse_color(5) is None
        assert parse_color("") is None
        assert parse_color("#12345") is None  # bad length
        assert parse_color("#1234567") is None  # bad length
        assert parse_color("#123456789") is None  # bad length
        assert parse_color("#12345g") is None  # bad digit
        assert parse_color("rgb(1, 2, 3)") is None  # rgb() without alpha is not accepted
        assert parse_color("rgba(256, 0, 0, 1)") is None  # r out of range
        assert parse_color("rgba(0, 0, 0, 1.5)") is None  # alpha out of range
        assert parse_color("rgba(0, 0, 0, -0.1)") is None


class TestLoadTheme:
    """``load_theme`` reads the live file with per-key / whole-seed fallback."""

    seed = _seed_values()

    def _cfg(self, tmp_path, monkeypatch, body: str):
        d = tmp_path / "text-to-speech"
        d.mkdir()
        (d / "theme.toml").write_text(body)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    def test_full_valid_file(self, tmp_path, monkeypatch):
        body = "".join(f'{k} = "{v}"\n' for k, v in self.seed.items())
        self._cfg(tmp_path, monkeypatch, body)
        values, warnings = load_theme()
        assert values == self.seed
        assert warnings == []

    def test_partial_file_falls_back_per_key(self, tmp_path, monkeypatch):
        body = 'surface = "#123456"\n'
        self._cfg(tmp_path, monkeypatch, body)
        values, warnings = load_theme()
        assert values["surface"] == "#123456"
        for role in THEME_ROLES:
            if role != "surface":
                assert values[role] == self.seed[role]
        assert warnings == []

    def test_invalid_value_falls_back_with_warning(self, tmp_path, monkeypatch):
        body = 'primary = "not-a-color"\nerror = 42\n'
        self._cfg(tmp_path, monkeypatch, body)
        values, warnings = load_theme()
        assert values["primary"] == self.seed["primary"]
        assert values["error"] == self.seed["error"]
        assert len(warnings) == 2
        assert all("not a valid color" in w for w in warnings)

    def test_unknown_role_ignored_with_warning(self, tmp_path, monkeypatch):
        body = 'btn_hover = "#123456"\n'
        self._cfg(tmp_path, monkeypatch, body)
        values, warnings = load_theme()
        assert values == self.seed
        assert len(warnings) == 1
        assert "btn_hover" in warnings[0]

    def test_missing_file_whole_seed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        values, warnings = load_theme()
        assert values == self.seed
        assert len(warnings) == 1

    def test_unparsable_file_whole_seed(self, tmp_path, monkeypatch):
        self._cfg(tmp_path, monkeypatch, "this = [ not toml\n")
        values, warnings = load_theme()
        assert values == self.seed
        assert len(warnings) == 1

    def test_all_seed_values_parse(self):
        for role, value in self.seed.items():
            assert role in THEME_ROLES
            assert parse_color(value) is not None
