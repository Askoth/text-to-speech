"""
synthesis.py
Speech synthesis functions: Piper TTS (offline), Edge TTS (online), model downloads.

This module is imported by both the web server (tts_engine.py) and the CLI (reader.py).
It must never call sys.exit() — errors are signaled through exceptions.
"""

import io
import urllib.request
import wave

from src.config import (
    PIPER_VOICES,
    VOICE_DIR,
    error,
    info,
    warn,
)


def download_piper_voice(voice: str):
    """Download the Piper voice files (model + config) if not already present.

    Parameters
    ----------
    voice : str
        Voice name in the PIPER_VOICES registry.

    Raises
    ------
    ValueError
        If the voice is not in the registry.
    RuntimeError
        If the download fails.
    """
    if voice not in PIPER_VOICES:
        raise ValueError(f"Unknown Piper voice: {voice}")
    cfg = PIPER_VOICES[voice]
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    for dest, url in (
        (cfg.model, cfg.url_model),
        (cfg.json, cfg.url_json),
    ):
        if dest.exists():
            info(f"Voice already present: {dest.name}")
            continue
        warn(f"Downloading {dest.name} ...")
        try:
            with urllib.request.urlopen(url) as response, open(dest, "wb") as f:  # noqa: S310
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                while True:
                    chunk = response.read(1024 * 64)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        print(f"\r  {downloaded / total * 100:.1f}%", end="", flush=True)
            print()
            info(f"{dest.name} downloaded.")
        except Exception as e:
            error(f"Error during download: {e}")
            raise RuntimeError(f"Piper voice download failed: {e}") from e


def synthesize_piper(piper_voice, text: str, sample_rate: int) -> bytes:
    """Synthesize text with Piper TTS.

    Parameters
    ----------
    piper_voice : PiperVoice
        Loaded instance of the Piper model.
    text : str
        Text to synthesize.
    sample_rate : int
        Sample rate of the model.

    Returns
    -------
    bytes
        In-memory WAV audio.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        piper_voice.synthesize_wav(text, wf)
    return buf.getvalue()
