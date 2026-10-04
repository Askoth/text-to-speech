"""
config.py
Centralized configuration: TTS voices, model paths, project constants.
"""

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ─── Project directories ────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_INPUT = PROJECT_ROOT / "data" / "input"
DATA_OUTPUT = PROJECT_ROOT / "data" / "output"

# ─── Voice configuration ───────────────────────────────────────────────────

# Directory holding the Piper models (under the user's home).
VOICE_DIR = Path.home() / "piper-voices"

# Registry of Piper voices. A voice declares:
#   model / json              -> local paths of the .onnx and .onnx.json files
#   url_model / url_json      -> where to download them if missing
#   gender / lang / multilingual -> metadata exposed to Web/CLI
# To add a voice, add an entry here.


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


PIPER_VOICES: PiperVoices = PiperVoices(
    [
        Voice(
            name="paola",
            gender="F",
            lang="it",
            multilingual=False,
            url_model="https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx",
            url_json="https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx.json",
        ),
        Voice(
            name="alba",
            gender="F",
            lang="en",
            multilingual=False,
            url_model="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx",
            url_json="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json",
        ),
        Voice(
            name="southern_english_female",
            gender="F",
            lang="en",
            multilingual=False,
            url_model="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/southern_english_female/low/en_GB-southern_english_female-low.onnx",
            url_json="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/southern_english_female/low/en_GB-southern_english_female-low.onnx.json",
        ),
    ]
)


ALL_VOICES = sorted(v.name for v in PIPER_VOICES.voices)
DEFAULT_VOICE = "alba"

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

    Parameters
    ----------
    mode : str
        "cli" for reader.py (needs an audio player), "web" for app.py (needs only ffmpeg).

    Returns
    -------
    list[str]
        List of critical errors. Empty if everything is OK.
    """
    errors = []

    # ffmpeg: required for both modes
    if not shutil.which("ffmpeg"):
        msg = f"ffmpeg not found (required).\n         {suggest_installation('ffmpeg')}"
        error(msg)
        errors.append("ffmpeg")

    # Audio player: only relevant for CLI
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
            warn(
                f"Install ffmpeg (includes ffplay):\n         {suggest_installation('ffmpeg')}"
            )

    # pandoc: optional
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
