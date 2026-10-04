"""
tts_engine.py
TTS wrapper with in-memory cache and async prefetch.
Imports the synthesis functions from synthesis.py.
"""

import asyncio
import logging
import subprocess
import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from src.config import PIPER_VOICES
from src.converters import file_to_text
from src.synthesis import download_piper_voice, synthesize_piper

log = logging.getLogger(__name__)

# Dedicated event loop for the Edge TTS coroutines (thread-safe)
_async_loop = asyncio.new_event_loop()
threading.Thread(target=_async_loop.run_forever, daemon=True, name="tts-async-loop").start()

MAX_CACHE = 50
_executor = ThreadPoolExecutor(max_workers=2)


def _wav_to_mp3_bytes(wav_bytes: bytes) -> bytes:
    """Convert WAV to MP3 in memory via ffmpeg (pipe in/out)."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            "pipe:0",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-loglevel",
            "error",
            "-f",
            "mp3",
            "pipe:1",
        ],
        input=wav_bytes,
        capture_output=True,
        check=True,
        timeout=30,
    )
    return result.stdout


def _concat_mp3_bytes(mp3_list: list[bytes]) -> bytes:
    """Concatenate a list of MP3s into a single file.

    MP3 frames are self-synchronizing: direct concatenation
    of the bytes produces a valid file without re-encoding.
    """
    return b"".join(mp3_list)


class TTSEngine:
    """Manages synthesis, cache, and prefetch for the web UI."""

    def __init__(self):
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._inflight: dict[str, Future] = {}
        self._lock = threading.Lock()
        self._paragraphs: list[str] = []
        self._filename: str = ""
        self._piper_voices: dict = {}

    @property
    def paragraphs(self) -> list[str]:
        return self._paragraphs

    @property
    def filename(self) -> str:
        return self._filename

    def load_file(self, path: Path) -> list[str]:
        """Load a file and return the list of paragraphs.

        Supports: .md, .txt, .epub, .docx, .html, .htm, .pdf
        """
        text = file_to_text(path)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        with self._lock:
            self._paragraphs = paragraphs
            self._filename = path.name
            self._cache.clear()
        return paragraphs

    def load_text(self, text: str, filename: str) -> list[str]:
        """Load raw text and return the list of paragraphs."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        with self._lock:
            self._paragraphs = paragraphs
            self._filename = filename
            self._cache.clear()
        return paragraphs

    def get_audio(self, index: int, voice: str) -> bytes:
        """Return MP3 bytes for the paragraph. Use cache if available."""
        if index < 0 or index >= len(self._paragraphs):
            raise IndexError(f"Paragraph {index} out of range")

        cache_key = f"{voice}:{index}"
        with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                log.info("Serving paragraph %d from cache (voice %s)", index, voice)
                return self._cache[cache_key]

        # Cache miss: join (or start) the in-flight job for this paragraph and
        # wait on it, so the same text is never synthesized twice.
        future = self._job_or_existing(index, voice, cache_key)
        mp3_bytes = future.result()

        # Prefetch next paragraph in background
        if index + 1 < len(self._paragraphs):
            self.prefetch(index + 1, voice)

        return mp3_bytes

    def prefetch(self, index: int, voice: str):
        """Ensure a background synthesis job for the paragraph.

        Non-blocking: if a job is already in flight for the same key it is
        shared instead of starting a second one.
        """
        if index < 0 or index >= len(self._paragraphs):
            return
        cache_key = f"{voice}:{index}"
        with self._lock:
            if cache_key in self._cache:
                return
        self._job_or_existing(index, voice, cache_key)

    def _job_or_existing(self, index: int, voice: str, cache_key: str) -> Future:
        """Return the in-flight job for cache_key, starting one if needed.

        Submit happens outside the lock: the job body re-acquires it (cache
        put / tracking pop), so it must never run on the calling thread while
        this lock is held.
        """
        with self._lock:
            existing = self._inflight.get(cache_key)
        if existing is not None:
            log.info("Paragraph %d still processing (voice %s); reusing job", index, voice)
            return existing

        future = _executor.submit(self._synth_job, index, voice, cache_key)
        with self._lock:
            winner = self._inflight.get(cache_key)
            if winner is None:
                self._inflight[cache_key] = future
                return future
            return winner

    def _synth_job(self, index: int, voice: str, cache_key: str) -> bytes:
        """Synthesis job body: synthesize, cache the result, clear the tracking.

        Any exception is logged and re-raised so waiters on the future get it.
        """
        try:
            mp3 = self._synthesize(index, voice)
            self._put_cache(cache_key, mp3)
            return mp3
        except Exception:
            log.warning("Synthesis failed for paragraph %d", index, exc_info=True)
            raise
        finally:
            with self._lock:
                self._inflight.pop(cache_key, None)

    def save_all(self, voice: str) -> bytes:
        """Synthesize all paragraphs and return concatenated MP3.

        Uses a snapshot of the paragraph list to avoid corruption
        if a new file is loaded during the operation.
        """
        with self._lock:
            snapshot = list(self._paragraphs)

        all_mp3 = []
        for i in range(len(snapshot)):
            all_mp3.append(self.get_audio(i, voice))
        return _concat_mp3_bytes(all_mp3)

    def _synthesize(self, index: int, voice: str) -> bytes:
        """Synthesize a paragraph. Always returns MP3."""
        with self._lock:
            if index < 0 or index >= len(self._paragraphs):
                raise IndexError(f"Paragraph {index} out of range (during synthesis)")
            text = self._paragraphs[index]

        # Piper (offline) — load the voice model lazily, style ignored
        piper_voice = self._load_piper(voice)
        wav_bytes = synthesize_piper(piper_voice, text, piper_voice.config.sample_rate)
        return _wav_to_mp3_bytes(wav_bytes)

    def _load_piper(self, voice):
        """Load the Piper model for the voice once (thread-safe)."""
        with self._lock:
            if voice in self._piper_voices:
                return self._piper_voices[voice]
            from piper import PiperVoice

            download_piper_voice(voice)
            cfg = PIPER_VOICES[voice]
            piper_voice = PiperVoice.load(str(cfg.model), config_path=str(cfg.json))
            self._piper_voices[voice] = piper_voice
            return piper_voice

    def _put_cache(self, key: str, data: bytes):
        with self._lock:
            self._cache[key] = data
            while len(self._cache) > MAX_CACHE:
                self._cache.popitem(last=False)

    def _clear_cache(self):
        with self._lock:
            self._cache.clear()
