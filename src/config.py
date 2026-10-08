"""Reader configuration (file-backed).

The live settings live at  ``~/.config/text-to-speech/settings.toml``  and are the
single source of truth for voices, language, last voice and model storage dir.

The in-repo seed lives at  ``text_to_speech/defaults/settings_default.toml``  and
is the source of the default *values*. This module holds **no** configuration
values of its own — the only thing it derives is the XDG data-dir path used when
``voice_dir`` is omitted.

``load_settings()`` reads the live file (seed in-memory if missing, per-key
fallback if partial, seed + warning if invalid) and never writes. The GUI calls
:func:`ensure_seeded` once at startup to copy the seed into place on first run;
the web/CLI only call :func:`load_settings` (no seeding). :func:`validate_settings`
is the pure, strict schema check used by ``text-to-speech validate``.
"""

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# ─── In-repo seed (package data) ────────────────────────────────────────────

_DEFAULTS = Path(__file__).resolve().parent / "text_to_speech" / "defaults"
_SEED_SETTINGS = _DEFAULTS / "settings_default.toml"
_SEED_THEME = _DEFAULTS / "theme_default.toml"

# ─── XDG locations for the live files ───────────────────────────────────────


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "text-to-speech"


def _data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "text-to-speech"


def settings_path() -> Path:
    return _config_dir() / "settings.toml"


def theme_path() -> Path:
    return _config_dir() / "theme.toml"


# ─── Schema ─────────────────────────────────────────────────────────────────

_SETTING_KEYS = ("lang", "last_voice", "voice_dir")  # per-key fallback targets
_VOICE_REQUIRED = ("name", "gender", "lang", "multilingual", "url_model", "url_json")


def _toml_load(path):
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _seed_settings() -> dict:
    return _toml_load(_SEED_SETTINGS)


def _norm_voice(d):
    """Validate/normalize one raw ``[[voices]]`` dict. Returns a dict, or None."""
    try:
        name = str(d["name"])
        gender = str(d["gender"])
        lang = str(d["lang"])
        multi = bool(d["multilingual"])
        url_model = str(d["url_model"])
        url_json = str(d["url_json"])
    except (KeyError, TypeError, ValueError):
        return None
    if not name or "/" in name:
        return None
    if gender not in ("F", "M"):
        return None
    if not url_model or not url_json:
        return None
    return {"name": name, "gender": gender, "lang": lang,
            "multilingual": multi, "url_model": url_model, "url_json": url_json}


def _normalize(data):
    """Per-key + per-voice fallback over a raw settings dict.

    Returns ``(voice_dicts, lang, last_voice, voice_dir, warnings)`` where
    ``voice_dicts`` is a list of normalized voice dicts (no ``Voice`` yet) and
    ``voice_dir`` a ``str``.
    """
    seed = _seed_settings()
    warnings: list[str] = []

    # --- voices ---
    if "voices" not in data:
        # absent -> per-key fallback, no warning
        voice_dicts = [_norm_voice(v) for v in seed.get("voices", [])]
    else:
        raw = data["voices"]
        if not isinstance(raw, list) or len(raw) == 0:
            voice_dicts = [_norm_voice(v) for v in seed.get("voices", [])]
            warnings.append("Voice list is empty or invalid — using the built-in voices.")
        else:
            seen: set[str] = set()
            voice_dicts = []
            for v in raw:
                e = _norm_voice(v)
                if e is None or e["name"] in seen:
                    continue
                seen.add(e["name"])
                voice_dicts.append(e)
            skipped = len(raw) - len(voice_dicts)
            if not voice_dicts:
                voice_dicts = [_norm_voice(v) for v in seed.get("voices", [])]
                warnings.append("No valid voices found — using the built-in voices.")
            else:
                if skipped:
                    plural = "y" if skipped == 1 else "ies"
                    warnings.append(f"{skipped} voice entr{plural} skipped (invalid or duplicate).")

    # --- scalar keys (per-key fallback to seed) ---
    lang = str(data.get("lang", seed.get("lang")))
    last_voice = data.get("last_voice", seed.get("last_voice"))
    voice_dir_raw = data.get("voice_dir")

    voice_dir = str(_data_dir() / "piper-voices")
    if isinstance(voice_dir_raw, str) and voice_dir_raw.strip():
        voice_dir = os.path.expandvars(os.path.expanduser(voice_dir_raw))

    # --- resolve last_voice against the voice list ---
    names = {d["name"] for d in voice_dicts}
    default_voice = (
        last_voice if (isinstance(last_voice, str) and last_voice in names)
        else (voice_dicts[0]["name"] if voice_dicts else "alba")
    )
    if default_voice != last_voice:
        warnings.append(
            f"last_voice '{last_voice}' not in the voice list — using '{default_voice}'"
        )

    return voice_dicts, lang, default_voice, voice_dir, warnings


# ─── Voice model (shared with web / CLI) ────────────────────────────────────


@dataclass
class Voice:
    name: str
    gender: str
    lang: str
    multilingual: bool
    model: Path = field(init=False)
    json: Path = field(init=False)
    url_model: str
    url_json: str

    def __post_init__(self):
        self.model = VOICE_DIR / self.url_model.split("/")[-1]
        self.json = VOICE_DIR / self.url_json.split("/")[-1]


@dataclass
class PiperVoices:
    voices: list[Voice]

    def __contains__(self, name: str) -> bool:
        return any(voice.name == name for voice in self.voices)

    def __getitem__(self, name: str) -> Voice:
        for voice in self.voices:
            if voice.name == name:
                return voice
        raise KeyError(f"Unknown Piper voice: {name}")

    def __iter__(self):
        return (voice.name for voice in self.voices)


# ─── Module values (loaded at import; seed in-memory, never writes) ─────────


def _read_live() -> dict:
    path = settings_path()
    if not path.exists():
        return _seed_settings()
    try:
        return _toml_load(path)
    except (tomllib.TOMLDecodeError, OSError):
        return _seed_settings()  # invalid -> seed in-memory (GUI warns via load_settings)


def _module_init():
    data = _read_live()
    try:
        voice_dicts, _lang, default_voice, voice_dir, _w = _normalize(data)
    except Exception:
        seed_voices = [_norm_voice(v) for v in _seed_settings().get("voices", [])] or []
        return seed_voices, "alba", str(_data_dir() / "piper-voices")
    return voice_dicts, default_voice, voice_dir


_voice_dicts, DEFAULT_VOICE, _voice_dir = _module_init()
VOICE_DIR = Path(_voice_dir)
PIPER_VOICES: PiperVoices = PiperVoices([Voice(**d) for d in _voice_dicts])
ALL_VOICES: list[str] = [v.name for v in PIPER_VOICES.voices]

# ─── Settings API ───────────────────────────────────────────────────────────


def load_settings() -> tuple[dict, list[str]]:
    """Load + normalize the live settings. Never writes.

    Returns ``(cfg, warnings)`` where ``cfg`` has keys ``voices`` (list of dict),
    ``lang``, ``last_voice`` and ``voice_dir``.
    """
    voice_dicts, lang, default_voice, voice_dir, warnings = _normalize(_read_live())
    return (
        {"voices": voice_dicts, "lang": lang, "last_voice": default_voice, "voice_dir": voice_dir},
        warnings,
    )


def ensure_seeded() -> list[Path]:
    """Copy missing seed files into the live config dir. Returns the files created.

    Called by the GUI at startup (web/CLI do not). Idempotent.
    """
    created: list[Path] = []
    _config_dir().mkdir(parents=True, exist_ok=True)
    for seed, live in ((_SEED_SETTINGS, settings_path()), (_SEED_THEME, theme_path())):
        if not live.exists():
            live.write_bytes(seed.read_bytes())
            created.append(live)
    return created


def validate_settings(data: dict) -> list[str]:
    """Strict schema check (for ``text-to-speech validate``). Returns error strings.

    An empty/absent voice list is an **error** here (strict); the app, by contrast,
    falls back to the built-in voices.
    """
    errors: list[str] = []

    for key in data:
        if key not in _SETTING_KEYS and key != "voices":
            errors.append(f"Unknown key: '{key}'")

    lang = data.get("lang")
    if lang is None:
        errors.append("Missing required key: 'lang'")
    elif not isinstance(lang, str) or lang not in ("en", "it"):
        errors.append(f"'lang' must be 'en' or 'it' (got {lang!r})")

    vd = data.get("voice_dir")
    if vd is not None and (not isinstance(vd, str) or not vd.strip()):
        errors.append("'voice_dir' must be a non-empty string")

    raw = data.get("voices")
    if not isinstance(raw, list) or len(raw) == 0:
        errors.append("Missing or empty 'voices' — at least one valid [[voices]] entry is required")
    else:
        seen: set[str] = set()
        for i, v in enumerate(raw):
            if not isinstance(v, dict):
                errors.append(f"voices[{i}] is not a table")
                continue
            for req in _VOICE_REQUIRED:
                if req not in v:
                    errors.append(f"voices[{i}] missing required key '{req}'")
            name = v.get("name")
            if not isinstance(name, str) or not name or "/" in name:
                errors.append(f"voices[{i}].name must be a non-empty string without '/'")
            elif name in seen:
                errors.append(f"voices[{i}].name '{name}' is duplicated")
            else:
                seen.add(name)
            if v.get("gender") not in ("F", "M"):
                errors.append(f"voices[{i}].gender must be 'F' or 'M'")
            if not isinstance(v.get("multilingual"), bool):
                errors.append(f"voices[{i}].multilingual must be a boolean")
            for url in ("url_model", "url_json"):
                u = v.get(url)
                if not isinstance(u, str) or not u.strip():
                    errors.append(f"voices[{i}].{url} must be a non-empty string")

    lv = data.get("last_voice")
    if lv is not None:
        if not isinstance(lv, str):
            errors.append("'last_voice' must be a string")
        else:
            names = {v.get("name") for v in raw if isinstance(v, dict)}
            if lv not in names:
                errors.append(f"last_voice '{lv}' does not match any [[voices]].name")

    return errors


# ─── Project directories (used by converters / temp I/O) ───────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_INPUT = PROJECT_ROOT / "data" / "input"
DATA_OUTPUT = PROJECT_ROOT / "data" / "output"

# ─── Platform and system dependencies ───────────────────────────────────────

PLATFORM = sys.platform  # "linux", "darwin", "win32"

_INSTALL_COMMANDS = {
    "linux": {
        "ffmpeg": (
            "sudo apt install ffmpeg  (Debian/Ubuntu)\n"
            "         sudo dnf install ffmpeg  (Fedora)\n"
            "         sudo pacman -S ffmpeg    (Arch)"
        ),
        "alsa-utils": (
            "sudo apt install alsa-utils  (Debian/Ubuntu)\n"
            "              sudo dnf install alsa-utils  (Fedora)\n"
            "              sudo pacman -S alsa-utils    (Arch)"
        ),
    },
    "darwin": {
        "ffmpeg": "brew install ffmpeg",
    },
    "win32": {
        "ffmpeg": "choco install ffmpeg   (Chocolatey)\n         scoop install ffmpeg   (Scoop)",
    },
}


def suggest_installation(package: str) -> str:
    """Return the install command for the package on the current OS."""
    commands = _INSTALL_COMMANDS.get(PLATFORM, {})
    return commands.get(package, f"Install '{package}' with your system package manager")


def check_prerequisites(mode: str = "cli") -> list[str]:
    """Check system dependencies and print warnings/errors.

    mode : "cli" (reader.py, needs an audio player) or "web" (app.py, needs ffmpeg).
    Returns a list of critical errors (empty if OK).
    """
    errors = []
    if not shutil.which("ffmpeg"):
        msg = f"ffmpeg not found (required).\n         {suggest_installation('ffmpeg')}"
        error(msg)
        errors.append("ffmpeg")
    if mode == "cli":
        has_player = False
        if PLATFORM == "darwin":
            has_player = bool(shutil.which("afplay") or shutil.which("ffplay"))
        elif PLATFORM == "win32":
            has_player = bool(shutil.which("ffplay"))
        else:
            has_player = bool(shutil.which("aplay") or shutil.which("ffplay"))
        if not has_player:
            warn("No audio player found. Playback will not work.")
            warn(f"Install ffmpeg (includes ffplay):\n         {suggest_installation('ffmpeg')}")
    if not shutil.which("pandoc"):
        warn("pandoc not found (optional, improves Markdown conversion)")
    return errors


# ─── Terminal colors ────────────────────────────────────────────────────────

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


def info(msg):
    print(f"{GREEN}[INFO]{NC}  {msg}", flush=True)


def warn(msg):
    print(f"{YELLOW}[WARN]{NC}  {msg}", flush=True)


def error(msg):
    print(f"{RED}[ERROR]{NC} {msg}", flush=True)
