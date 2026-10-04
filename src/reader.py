#!/usr/bin/env python3
"""
reader.py
Reads text files aloud in Italian using Piper TTS.
Supports: Markdown, TXT, EPUB, DOCX, HTML, PDF.

Usage:
    python reader.py file.md
    python reader.py document.pdf --voice giuseppe
    python reader.py book.epub --voice paola --save output.mp3

Available voices:
    paola     - Piper TTS, female, offline

Initial setup (one time only):
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
"""

import argparse
import asyncio
import io
import shutil
import subprocess
import sys
import wave
from pathlib import Path

from src.config import (
    ALL_VOICES,
    DATA_OUTPUT,
    DEFAULT_VOICE,
    GREEN,
    NC,
    PIPER_VOICES,
    PLATFORM,
    check_prerequisites,
    error,
    info,
    suggest_installation,
)
from src.synthesis import download_piper_voice, synthesize_piper

# ─── Audio utilities ────────────────────────────────────────────────────────


def wav_to_mp3(wav_bytes: bytes, output_path: Path):
    subprocess.run(
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
            str(output_path),
        ],
        input=wav_bytes,
        check=True,
        timeout=30,
    )


def concat_wav(wav_list: list[bytes], sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf_out:
        wf_out.setnchannels(1)
        wf_out.setsampwidth(2)
        wf_out.setframerate(sample_rate)
        for wav_bytes in wav_list:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf_in:
                wf_out.writeframes(wf_in.readframes(wf_in.getnframes()))
    return buf.getvalue()


def concat_mp3(mp3_list: list[bytes], output_path: Path):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            "concat:pipe:0",
            "-codec:a",
            "copy",
            "-loglevel",
            "error",
            str(output_path),
        ],
        input=b"".join(mp3_list),
        check=True,
        timeout=30,
    )


# ─── Audio playback ─────────────────────────────────────────────────────────


def _find_player(fmt: str) -> tuple[list[str], bool]:
    """Find the audio playback command for the current OS.

    Parameters
    ----------
    fmt : str
        Audio format: "wav" or "mp3".

    Returns
    -------
    tuple[list[str], bool]
        (command with arguments, supports_stdin). If supports_stdin is False,
        the command requires a temporary file.
    """
    if PLATFORM == "darwin":
        # afplay: native to macOS, supports WAV and MP3, but not stdin
        if shutil.which("afplay"):
            return ["afplay"], False
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-"], True

    elif PLATFORM == "win32":
        # Windows: ffplay is the primary player (included in ffmpeg)
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-"], True

    else:
        # Linux: aplay for WAV, ffplay for MP3
        if fmt == "wav" and shutil.which("aplay"):
            return ["aplay", "-q", "-"], True
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-"], True

    return [], False


def _has_player(fmt: str) -> bool:
    """Check whether an audio player is available for the format on the current OS."""
    cmd, _ = _find_player(fmt)
    return len(cmd) > 0


def play_audio(audio_bytes: bytes, fmt: str):
    """Play audio using the player available on the current OS."""
    cmd, supports_stdin = _find_player(fmt)
    if not cmd:
        error(f"No audio player found for {fmt}.")
        error(f"Install ffmpeg:\n         {suggest_installation('ffmpeg')}")
        return

    if supports_stdin:
        subprocess.run(cmd, input=audio_bytes, check=False, timeout=60)
    else:
        # afplay (macOS) does not support stdin: use a temporary file
        import tempfile

        ext = f".{fmt}"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            subprocess.run([*cmd, tmp_path], check=False, timeout=60)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ─── Reading with Piper TTS ─────────────────────────────────────────────────


def read_with_piper(
    text: str,
    voice: str = DEFAULT_VOICE,
    save_path: Path | None = None,
    paragraphs_dir: Path | None = None,
):
    try:
        from piper import PiperVoice
    except ImportError:
        error("Piper not found. Install with: pip install piper-tts")
        sys.exit(1)

    will_play = _has_player("wav")
    if not will_play and save_path is None:
        install_hint = suggest_installation("ffmpeg")
        error(f"No audio player found.\n         Install ffmpeg:\n         {install_hint}")
        sys.exit(1)

    if save_path and not shutil.which("ffmpeg"):
        error(f"ffmpeg not found.\n         {suggest_installation('ffmpeg')}")
        sys.exit(1)

    cfg = PIPER_VOICES[voice]
    info(f"Loading voice {voice}...")
    piper_voice = PiperVoice.load(str(cfg.model), config_path=str(cfg.json))
    sample_rate = piper_voice.config.sample_rate

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    info(f"Paragraphs to read: {len(paragraphs)}")

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        if paragraphs_dir:
            paragraphs_dir.mkdir(parents=True, exist_ok=True)
        info(f"Saving to: {save_path}")

    if will_play:
        info("Starting reading... (Ctrl+C to interrupt)")

    all_wav = []

    try:
        for i, paragraph in enumerate(paragraphs, 1):
            show_paragraph(i, len(paragraphs), paragraph, will_play)
            wav_bytes = synthesize_piper(piper_voice, paragraph, sample_rate)

            if save_path:
                all_wav.append(wav_bytes)
                if paragraphs_dir:
                    wav_to_mp3(wav_bytes, paragraphs_dir / f"{i:03d}.mp3")
                if not will_play:
                    info(f"[{i}/{len(paragraphs)}] saved")

            if will_play:
                play_audio(wav_bytes, "wav")

    except KeyboardInterrupt:  # pragma: no cover — requires real SIGINT
        print()
        info("Reading interrupted.")

    if save_path and all_wav:
        info("Creating full audio file...")
        full_wav = concat_wav(all_wav, sample_rate)
        wav_to_mp3(full_wav, save_path)
        info(f"Saved: {save_path} ({len(all_wav)} paragraphs)")


async def _play_async(mp3_bytes: bytes):
    """Play MP3 non-blockingly for the event loop."""
    cmd, supports_stdin = _find_player("mp3")
    if not cmd:
        return

    if supports_stdin:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
        )
        await proc.communicate(input=mp3_bytes)
    else:
        # afplay (macOS): requires a temporary file
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(mp3_bytes)
            tmp_path = tmp.name
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, tmp_path)
            await proc.wait()
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ─── UI utilities ────────────────────────────────────────────────────────────


def calc_output_path(input_file: Path):
    """Calculate the output directories from the data/ structure.

    Parameters
    ----------
    input_file : Path
        Source file (e.g. data/input/document.md).

    Returns
    -------
    tuple[Path, Path, Path]
        (base_dir, full_mp3_path, paragraphs_dir)
        E.g. data/output/document/full/document.mp3,
             data/output/document/paragraphs/
    """
    stem = input_file.stem
    base_dir = DATA_OUTPUT / stem
    full_dir = base_dir / "full"
    paragraphs_dir = base_dir / "paragraphs"
    mp3_path = full_dir / f"{stem}.mp3"
    return base_dir, mp3_path, paragraphs_dir


def show_paragraph(i: int, total: int, text: str, visible: bool):
    if not visible:
        return
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.write(f"{GREEN}[{i}/{total}]{NC}\n\n")
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    from src.converters import SUPPORTED_EXTENSIONS, file_to_text

    ext_list = ", ".join(sorted(SUPPORTED_EXTENSIONS))
    parser = argparse.ArgumentParser(
        description="Reads text files aloud in Italian.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""supported formats: {ext_list}

available voices:
  paola     Piper TTS, female, offline

output structure (with --save):
  data/output/<file_name>/full/<file_name>.mp3
  data/output/<file_name>/paragraphs/001.mp3, 002.mp3, ...""",
    )
    parser.add_argument("file", type=Path, help="File to read")
    parser.add_argument(
        "--voice",
        choices=ALL_VOICES,
        default=DEFAULT_VOICE,
        help=f"Voice to use (default: {DEFAULT_VOICE})",
    )
    parser.add_argument(
        "--salva",
        action="store_true",
        help="Save the audio to data/output/<file_name>/",
    )
    args = parser.parse_args()

    errors = check_prerequisites(mode="cli")
    if errors:
        sys.exit(1)

    if not args.file.exists():
        error(f"File not found: {args.file}")
        sys.exit(1)

    info(f"File: {args.file.name}")
    info(f"Voice: {args.voice}")

    save_path = None
    paragraphs_dir = None
    if args.salva:
        _, save_path, paragraphs_dir = calc_output_path(args.file)
        info(f"Output: {save_path.parent.parent}/")

    info("Converting to text...")
    text = file_to_text(args.file)

    if not text.strip():
        error("The file seems empty after conversion.")
        sys.exit(1)

    info(f"Extracted text: {len(text)} characters")

    download_piper_voice(args.voice)
    read_with_piper(text, args.voice, save_path=save_path, paragraphs_dir=paragraphs_dir)

    info("Done.")


if __name__ == "__main__":  # pragma: no cover
    main()
