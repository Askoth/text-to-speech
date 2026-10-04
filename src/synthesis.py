"""
synthesis.py
Funzioni di sintesi vocale: Piper TTS (offline), Edge TTS (online), download modelli.

Questo modulo è importato sia dal web server (tts_engine.py) sia dalla CLI (leggi.py).
Non deve mai chiamare sys.exit() — gli errori sono segnalati tramite eccezioni.
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


def scarica_voce_piper(voce: str):
    """Scarica i file (modello + config) della voce Piper se non già presenti.

    Parameters
    ----------
    voce : str
        Nome voce nel registro PIPER_VOICES.

    Raises
    ------
    ValueError
        Se la voce non è nel registro.
    RuntimeError
        Se il download fallisce.
    """
    if voce not in PIPER_VOICES:
        raise ValueError(f"Voce Piper sconosciuta: {voce}")
    cfg = PIPER_VOICES[voce]
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    for dest, url in (
        (cfg.model, cfg.url_model),
        (cfg.json, cfg.url_json),
    ):
        if dest.exists():
            info(f"Voce già presente: {dest.name}")
            continue
        warn(f"Scarico {dest.name} ...")
        try:
            with urllib.request.urlopen(url) as response, open(dest, "wb") as f:  # noqa: S310
                total = int(response.headers.get("Content-Length", 0))
                scaricati = 0
                while True:
                    chunk = response.read(1024 * 64)
                    if not chunk:
                        break
                    f.write(chunk)
                    scaricati += len(chunk)
                    if total:
                        print(f"\r  {scaricati / total * 100:.1f}%", end="", flush=True)
            print()
            info(f"{dest.name} scaricato.")
        except Exception as e:
            error(f"Errore durante il download: {e}")
            raise RuntimeError(f"Download voce Piper fallito: {e}") from e


def sintetizza_piper(voce_piper, testo: str, sample_rate: int) -> bytes:
    """Sintetizza testo con Piper TTS.

    Parameters
    ----------
    voce_piper : PiperVoice
        Istanza del modello Piper caricato.
    testo : str
        Testo da sintetizzare.
    sample_rate : int
        Frequenza di campionamento del modello.

    Returns
    -------
    bytes
        Audio WAV in memoria.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        voce_piper.synthesize_wav(testo, wf)
    return buf.getvalue()
