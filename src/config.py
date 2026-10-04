"""
config.py
Configurazione centralizzata: voci TTS, path modelli, costanti di progetto.
"""

import shutil
import sys
from pathlib import Path

# ─── Directory di progetto ───────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_INPUT = PROJECT_ROOT / "data" / "input"
DATA_OUTPUT = PROJECT_ROOT / "data" / "output"

# ─── Configurazione voci ─────────────────────────────────────────────────────

# Directory in cui risiedono i modelli Piper (sotto la home dell'utente).
VOICE_DIR = Path.home() / "piper-voices"

# Registro delle voci Piper. Una voce dichiara:
#   model / json              -> path locali dei file .onnx e .onnx.json
#   url_model / url_json      -> da dove scaricarli se mancanti
#   gender / lang / multilingual -> metadati esposti a Web/CLI
# Per aggiungere una voce basta aggiungere una entry qui.
PIPER_VOICES = {
    "paola": {
        "gender": "F",
        "lang": "it",
        "multilingual": False,
        "model": VOICE_DIR / "it_IT-paola-medium.onnx",
        "json": VOICE_DIR / "it_IT-paola-medium.onnx.json",
        "url_model": "https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx",
        "url_json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx.json",
    },
    "alba": {
        "gender": "F",
        "lang": "en",
        "multilingual": False,
        "model": VOICE_DIR / "en_GB-alba-medium.onnx",
        "json": VOICE_DIR / "en_GB-alba-medium.onnx.json",
        "url_model": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx",
        "url_json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json",
    },
}

ALL_VOICES = sorted(PIPER_VOICES)
DEFAULT_VOICE = "paola"

# ─── Piattaforma e dipendenze di sistema ────────────────────────────────────

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


def suggerisci_installazione(pacchetto: str) -> str:
    """Restituisce il comando di installazione per il pacchetto sull'OS corrente."""
    comandi = _INSTALL_COMMANDS.get(PLATFORM, {})
    return comandi.get(pacchetto, f"Installa '{pacchetto}' con il package manager del tuo sistema")


def verifica_prerequisiti(modalita: str = "cli") -> list[str]:
    """Verifica le dipendenze di sistema e stampa warning/errori.

    Parameters
    ----------
    modalita : str
        "cli" per leggi.py (serve player audio), "web" per app.py (serve solo ffmpeg).

    Returns
    -------
    list[str]
        Lista di errori critici. Vuota se tutto OK.
    """
    errori = []

    # ffmpeg: obbligatorio per entrambe le modalità
    if not shutil.which("ffmpeg"):
        msg = f"ffmpeg non trovato (obbligatorio).\n         {suggerisci_installazione('ffmpeg')}"
        error(msg)
        errori.append("ffmpeg")

    # Player audio: rilevante solo per CLI
    if modalita == "cli":
        ha_player = False
        if PLATFORM == "darwin":
            ha_player = bool(shutil.which("afplay") or shutil.which("ffplay"))
        elif PLATFORM == "win32":
            ha_player = bool(shutil.which("ffplay"))
        else:
            ha_player = bool(shutil.which("aplay") or shutil.which("ffplay"))

        if not ha_player:
            warn("Nessun player audio trovato. La riproduzione non funzionerà.")
            warn(
                f"Installa ffmpeg (include ffplay):\n         {suggerisci_installazione('ffmpeg')}"
            )

    # pandoc: opzionale
    if not shutil.which("pandoc"):
        warn("pandoc non trovato (opzionale, migliora la conversione Markdown)")

    return errori


# ─── Colori terminale ────────────────────────────────────────────────────────

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


def info(msg):
    print(f"{GREEN}[INFO]{NC}  {msg}", flush=True)


def warn(msg):
    print(f"{YELLOW}[WARN]{NC}  {msg}", flush=True)


def error(msg):
    print(f"{RED}[ERRORE]{NC} {msg}", flush=True)
