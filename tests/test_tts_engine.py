"""
tests/test_tts_engine.py
Tests for tts_engine.py: LRU cache, synthesis, prefetch, save_all, load_file.

External dependencies (piper, ffmpeg) are always mocked.
"""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ===========================================================================
# Fixture
# ===========================================================================


@pytest.fixture()
def engine_with_text(engine):
    """Engine with 3 loaded paragraphs."""
    engine.load_text(
        "Primo paragrafo.\n\nSecondo paragrafo.\n\nTerzo paragrafo.",
        "test.md",
    )
    return engine


# ===========================================================================
# Tests — _concat_mp3_bytes
# ===========================================================================


class TestConcatMp3Bytes:
    """Tests for direct MP3 concatenation."""

    def test_concatenates_two_mp3(self):
        """Two MP3 chunks must be joined in sequence."""
        from src.tts_engine import _concat_mp3_bytes

        # Arrange
        chunk1 = b"\xff\xfb\x90\x00" + b"\x00" * 100
        chunk2 = b"\xff\xfb\x90\x00" + b"\x00" * 200

        # Act
        result = _concat_mp3_bytes([chunk1, chunk2])

        # Assert
        assert result == chunk1 + chunk2
        assert len(result) == len(chunk1) + len(chunk2)

    def test_concatenates_empty_list(self):
        """An empty list must return empty bytes."""
        from src.tts_engine import _concat_mp3_bytes

        # Act
        result = _concat_mp3_bytes([])

        # Assert
        assert result == b""

    def test_concatenates_single_element(self):
        """A single chunk must be returned unchanged."""
        from src.tts_engine import _concat_mp3_bytes

        # Arrange
        chunk = b"\xff\xfb\x90\x00data"

        # Act
        result = _concat_mp3_bytes([chunk])

        # Assert
        assert result == chunk


# ===========================================================================
# Tests — TTSEngine.load_file
# ===========================================================================


class TestTTSEngineLoadFile:
    """Tests for loading Markdown files."""

    def test_load_file_calls_markdown_to_text(self, engine, tmp_path):
        """load_file must use file_to_text for the conversion."""
        # Arrange
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Titolo\n\nParagrafo uno.\n\nParagrafo due.")

        with patch(
            "src.tts_engine.file_to_text",
            return_value="Paragrafo uno.\n\nParagrafo due.",
        ) as mock_conv:
            # Act
            paragrafi = engine.load_file(md_file)

        # Assert
        mock_conv.assert_called_once_with(md_file)
        assert len(paragrafi) == 2
        assert paragrafi[0] == "Paragrafo uno."
        assert paragrafi[1] == "Paragrafo due."
        assert engine.filename == "doc.md"

    def test_load_file_clears_previous_cache(self, engine):
        """Loading a new file must empty the cache."""
        # Arrange — load a first text and populate the cache manually
        engine.load_text("Vecchio testo.", "old.md")
        engine._put_cache("paola:0", b"fake_mp3")
        assert len(engine._cache) == 1

        # Act — load a new text
        with patch(
            "src.tts_engine.file_to_text",
            return_value="Nuovo testo.",
        ):
            engine.load_file(Path("/fake/new.md"))

        # Assert
        assert len(engine._cache) == 0
        assert engine.filename == "new.md"

    def test_load_file_ignores_empty_paragraphs(self, engine):
        """Empty paragraphs (whitespace only) must be excluded."""
        # Arrange
        with patch(
            "src.tts_engine.file_to_text",
            return_value="Testo.\n\n   \n\n\n\nAltro testo.",
        ):
            # Act
            paragrafi = engine.load_file(Path("/fake/test.md"))

        # Assert
        assert len(paragrafi) == 2
        assert paragrafi[0] == "Testo."
        assert paragrafi[1] == "Altro testo."


# ===========================================================================
# Tests — TTSEngine LRU cache
# ===========================================================================


class TestTTSEngineCache:
    """Tests for the LRU cache with eviction."""

    def test_cache_eviction_on_exceeding_max(self, engine):
        """The cache must evict the oldest elements beyond MAX_CACHE."""
        from src.tts_engine import MAX_CACHE

        # Arrange — insert MAX_CACHE + 5 elements
        for i in range(MAX_CACHE + 5):
            engine._put_cache(f"voice:{i}", f"data_{i}".encode())

        # Assert — the cache must not exceed MAX_CACHE
        assert len(engine._cache) == MAX_CACHE

        # The first 5 elements must have been evicted
        assert "voice:0" not in engine._cache
        assert "voice:4" not in engine._cache

        # The last element must be present
        assert f"voice:{MAX_CACHE + 4}" in engine._cache

    def test_cache_move_to_end_on_access(self, engine_with_text):
        """Accessing a cached element must move it to the end (MRU)."""
        # Arrange — populate the cache with 3 elements
        engine_with_text._put_cache("paola:0", b"mp3_0")
        engine_with_text._put_cache("paola:1", b"mp3_1")
        engine_with_text._put_cache("paola:2", b"mp3_2")

        # Act — access the first element (should move it to the end)
        with patch.object(engine_with_text, "_synthesize", return_value=b"mp3_0"):
            engine_with_text.get_audio(0, "paola")

        # Assert — "paola:0" must be the last one (MRU)
        keys = list(engine_with_text._cache.keys())
        assert keys[-1] == "paola:0"

    def test_clear_cache_completely(self, engine):
        """_clear_cache must remove all elements."""
        # Arrange
        engine._put_cache("a", b"1")
        engine._put_cache("b", b"2")
        assert len(engine._cache) == 2

        # Act
        engine._clear_cache()

        # Assert
        assert len(engine._cache) == 0


# ===========================================================================
# Tests — TTSEngine._synthesize
# ===========================================================================


class TestTTSEngineSynthesize:
    """Tests for the synthesis dispatch toward Piper."""

    def test_synthesize_piper_lazy_loads_model(self, engine_with_text):
        """For Piper voices, must load the model on first use."""
        # Arrange
        fake_wav = b"RIFF\x00\x00\x00\x00WAVEfmt "
        fake_mp3 = b"ID3\x00piper_audio"

        with (
            patch.object(engine_with_text, "_load_piper") as mock_load,
            patch("src.tts_engine.synthesize_piper", return_value=fake_wav),
            patch("src.tts_engine._wav_to_mp3_bytes", return_value=fake_mp3),
        ):
            # Act
            result = engine_with_text._synthesize(0, "paola")

        # Assert
        mock_load.assert_called_once()
        assert result == fake_mp3

    def test_synthesize_piper_does_not_reload_model(self, engine_with_text):
        """If the model is already in _piper_voices, _synthesize must not regenerate it."""
        # Arrange — simulate the model already loaded in the dict
        mock_voice = MagicMock()
        mock_voice.config.sample_rate = 22050
        engine_with_text._piper_voices["paola"] = mock_voice
        fake_wav = b"RIFF\x00\x00\x00\x00WAVEfmt "
        fake_mp3 = b"ID3\x00piper_audio"

        # Act — _load_piper NOT mocked: must only do the dict lookup
        with (
            patch("src.tts_engine.synthesize_piper", return_value=fake_wav) as mock_synth,
            patch("src.tts_engine._wav_to_mp3_bytes", return_value=fake_mp3),
        ):
            engine_with_text._synthesize(0, "paola")

        # Assert — synthesize_piper receives the model already in the dict
        assert mock_synth.call_count == 1
        assert mock_synth.call_args[0][0] is mock_voice


# ===========================================================================
# Tests — TTSEngine.save_all
# ===========================================================================


class TestTTSEngineSaveAll:
    """Tests for generating the complete MP3 file."""

    def test_save_all_concatenates_all_paragraphs(self, engine_with_text):
        """save_all must synthesize and concatenate all paragraphs."""
        # Arrange
        mp3_chunks = [b"chunk_0", b"chunk_1", b"chunk_2"]

        with patch.object(
            engine_with_text,
            "_synthesize",
            side_effect=lambda i, v: mp3_chunks[i],
        ):
            # Act
            result = engine_with_text.save_all("paola")

        # Assert — the bytes must be the in-order concatenation
        assert result == b"chunk_0" + b"chunk_1" + b"chunk_2"

    def test_save_all_uses_cache_if_available(self, engine_with_text):
        """save_all must use the cache for already synthesized paragraphs."""
        # Arrange — pre-populate the cache for paragraph 0
        engine_with_text._put_cache("paola:0", b"cached_0")
        call_count = 0

        def fake_synthesize(i, v):
            nonlocal call_count
            call_count += 1
            return f"synth_{i}".encode()

        with patch.object(engine_with_text, "_synthesize", side_effect=fake_synthesize):
            # Act
            result = engine_with_text.save_all("paola")

        # Assert — _synthesize called only for paragraphs 1 and 2 (not 0)
        assert call_count == 2
        assert result == b"cached_0synth_1synth_2"

    def test_save_all_without_paragraphs_returns_empty(self, engine):
        """save_all without loaded paragraphs must return empty bytes."""
        # Act
        result = engine.save_all("paola")

        # Assert
        assert result == b""


# ===========================================================================
# Tests — TTSEngine.prefetch
# ===========================================================================


class TestTTSEnginePrefetch:
    """Tests for background prefetching."""

    def test_prefetch_does_not_block(self, engine_with_text):
        """prefetch must return immediately (non-blocking)."""
        # Arrange
        with patch.object(engine_with_text, "_synthesize", return_value=b"mp3"):
            # Act & Assert — must complete in less than 1 second
            start = time.monotonic()
            engine_with_text.prefetch(0, "paola")
            elapsed = time.monotonic() - start

            assert elapsed < 1.0

    def test_prefetch_skips_if_already_in_cache(self, engine_with_text):
        """If the paragraph is already in the cache, prefetch must do nothing."""
        # Arrange
        engine_with_text._put_cache("paola:0", b"cached")

        with patch.object(engine_with_text, "_synthesize") as mock_synth:
            # Act
            engine_with_text.prefetch(0, "paola")
            # Wait briefly for the thread pool
            time.sleep(0.1)

        # Assert — _synthesize must NOT be called
        mock_synth.assert_not_called()

    def test_prefetch_ignores_out_of_range_index(self, engine_with_text):
        """Out-of-range indices must be silently ignored."""
        # Act & Assert — must not raise exceptions
        engine_with_text.prefetch(-1, "paola")
        engine_with_text.prefetch(999, "paola")

    def test_prefetch_inserts_into_cache(self, engine_with_text):
        """Prefetch must insert the result in the cache on completion."""
        # Arrange
        fake_mp3 = b"prefetched_mp3"

        with (
            patch.object(engine_with_text, "_synthesize", return_value=fake_mp3),
            patch("src.tts_engine._executor") as mock_exec,
        ):
            # Run the synchronous task (remove race condition from CI)
            mock_exec.submit.side_effect = lambda fn, *args: fn(*args)
            # Act
            engine_with_text.prefetch(0, "paola")

        # Assert
        assert "paola:0" in engine_with_text._cache
        assert engine_with_text._cache["paola:0"] == fake_mp3


# ===========================================================================
# Tests — TTSEngine single-flight (inflight dedup)
# ===========================================================================


class TestSingleFlight:
    """One synthesis job per key: concurrent requests share the in-flight job."""

    def test_get_audio_joins_inflight_job(self, engine_with_text):
        """get_audio must wait for the in-flight job, not synthesize again."""
        # Arrange — last paragraph so get_audio triggers no follow-up prefetch
        idx = len(engine_with_text.paragraphs) - 1
        started = threading.Event()
        release = threading.Event()
        calls = []

        def fake_synthesize(i, voice):
            calls.append((i, voice))
            started.set()
            assert release.wait(5)
            return b"mp3"

        outcome = {}

        def caller():
            outcome["audio"] = engine_with_text.get_audio(idx, "paola")

        # Act
        with patch.object(engine_with_text, "_synthesize", side_effect=fake_synthesize):
            engine_with_text.prefetch(idx, "paola")
            assert started.wait(5)  # job running inside _synthesize

            waiter = threading.Thread(target=caller)
            waiter.start()
            release.set()  # unblock the job
            waiter.join(5)

        # Assert — exactly one synthesis for the key
        assert outcome.get("audio") == b"mp3"
        assert calls == [(idx, "paola")]

    def test_second_prefetch_is_noop(self, engine_with_text):
        """A second prefetch for a key with a running job must not submit again."""
        # Arrange
        started = threading.Event()
        release = threading.Event()

        def fake_synthesize(i, voice):
            started.set()
            assert release.wait(5)
            return b"mp3"

        # Act
        with patch.object(engine_with_text, "_synthesize", side_effect=fake_synthesize):
            engine_with_text.prefetch(0, "paola")
            assert started.wait(5)
            engine_with_text.prefetch(0, "paola")  # must join, not resubmit
            job = engine_with_text._inflight["paola:0"]
            release.set()
            job.result(5)  # wait for the job to fully finish

        # Assert
        assert len(engine_with_text._inflight) == 0
        assert "paola:0" in engine_with_text._cache


# ===========================================================================
# Tests — TTSEngine.get_audio (integration with cache and prefetch)
# ===========================================================================


class TestTTSEngineGetAudioIntegration:
    """Integration tests for get_audio with cache and prefetch."""

    def test_get_audio_triggers_prefetch_for_next(self, engine_with_text):
        """get_audio must trigger the prefetch of the next paragraph."""
        # Arrange
        with (
            patch.object(engine_with_text, "_synthesize", return_value=b"mp3"),
            patch.object(engine_with_text, "prefetch") as mock_prefetch,
        ):
            # Act
            engine_with_text.get_audio(0, "paola")

        # Assert — prefetch called for paragraph 1
        mock_prefetch.assert_called_once_with(1, "paola")

    def test_get_audio_no_prefetch_on_last_paragraph(self, engine_with_text):
        """The last paragraph must not trigger a prefetch."""
        # Arrange
        last_idx = len(engine_with_text.paragraphs) - 1

        with (
            patch.object(engine_with_text, "_synthesize", return_value=b"mp3"),
            patch.object(engine_with_text, "prefetch") as mock_prefetch,
        ):
            # Act
            engine_with_text.get_audio(last_idx, "paola")

        # Assert — prefetch NOT called
        mock_prefetch.assert_not_called()

    def test_get_audio_different_voices_do_not_share_cache(self, engine_with_text):
        """Different voices must have separate cache entries."""

        # Arrange
        def fake_synth(idx, voice):
            return f"mp3_{voice}".encode()

        # We also patch prefetch: the test covers only cache keys,
        # it must not leak a background worker with a nonexistent voice
        with (
            patch.object(engine_with_text, "_synthesize", side_effect=fake_synth),
            patch.object(engine_with_text, "prefetch"),
        ):
            # Act
            audio_p = engine_with_text.get_audio(0, "paola")
            audio_m = engine_with_text.get_audio(0, "maria")

        # Assert
        assert audio_p != audio_m
        assert "paola:0" in engine_with_text._cache
        assert "maria:0" in engine_with_text._cache


# ===========================================================================
# Tests — TTSEngine._load_piper (idempotency)
# ===========================================================================


class TestTTSEngineLoadPiper:
    """Tests for lazy loading of the Piper model."""

    def test_load_piper_idempotent(self, engine):
        """Calling _load_piper twice must load the model only once."""
        # Arrange
        mock_voice = MagicMock()
        mock_voice.config.sample_rate = 22050
        mock_piper_module = MagicMock()
        mock_piper_module.PiperVoice.load.return_value = mock_voice

        # PiperVoice is imported lazily inside _load_piper with
        # "from piper import PiperVoice", so we patch the piper module
        with (
            patch("src.tts_engine.download_piper_voice"),
            patch.dict("sys.modules", {"piper": mock_piper_module}),
        ):
            # Act — call twice
            engine._load_piper("paola")
            engine._load_piper("paola")

        # Assert — PiperVoice.load called only once
        mock_piper_module.PiperVoice.load.assert_called_once()
        assert engine._piper_voices["paola"] is mock_voice


# ===========================================================================
# Tests — _wav_to_mp3_bytes
# ===========================================================================


class TestWavToMp3Bytes:
    """Tests for the WAV→MP3 conversion via ffmpeg."""

    def test_calls_ffmpeg_with_pipe(self):
        """Must invoke ffmpeg with pipe input/output and the lame codec."""
        from src.tts_engine import _wav_to_mp3_bytes

        # Arrange
        fake_wav = b"RIFF\x00\x00\x00\x00WAVEfmt "
        fake_mp3 = b"ID3\x00fake_mp3"
        mock_result = MagicMock()
        mock_result.stdout = fake_mp3

        with patch("src.tts_engine.subprocess.run", return_value=mock_result) as mock_run:
            # Act
            _wav_to_mp3_bytes(fake_wav)

        # Assert — check the key arguments of the ffmpeg command
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[0] == "ffmpeg"
        assert "pipe:0" in cmd
        assert "libmp3lame" in cmd
        assert "pipe:1" in cmd
        assert kwargs["input"] == fake_wav
        assert kwargs["check"] is True

    def test_returns_ffmpeg_stdout(self):
        """The return value must match result.stdout."""
        from src.tts_engine import _wav_to_mp3_bytes

        # Arrange
        fake_wav = b"RIFF\x00\x00\x00\x00WAVEfmt "
        fake_mp3 = b"ID3\x00fake_mp3_output"
        mock_result = MagicMock()
        mock_result.stdout = fake_mp3

        with patch("src.tts_engine.subprocess.run", return_value=mock_result):
            # Act
            result = _wav_to_mp3_bytes(fake_wav)

        # Assert
        assert result == fake_mp3

    def test_propagates_ffmpeg_error(self):
        """If ffmpeg fails, CalledProcessError must propagate to the caller."""
        import subprocess as stdlib_subprocess

        from src.tts_engine import _wav_to_mp3_bytes

        # Arrange
        fake_wav = b"RIFF\x00\x00\x00\x00WAVEfmt "
        error = stdlib_subprocess.CalledProcessError(returncode=1, cmd=["ffmpeg"], stderr=b"error")

        with (
            patch("src.tts_engine.subprocess.run", side_effect=error),
            pytest.raises(stdlib_subprocess.CalledProcessError),
        ):
            # Act
            _wav_to_mp3_bytes(fake_wav)


# ===========================================================================
# Tests — TTSEngine._synthesize (race condition)
# ===========================================================================


class TestSynthesizeRaceCondition:
    """Tests for the IndexError path during synthesis (race condition)."""

    def test_synthesize_index_out_of_range_during_synthesis(self, engine):
        """If the paragraphs are emptied between the check in get_audio and the
        lock acquisition in _synthesize, an IndexError must be raised."""
        # Arrange — load a paragraph, then simulate the race condition by emptying the list
        engine.load_text("Solo un paragrafo.", "test.md")
        engine._paragraphs = []  # race: emptied before _synthesize acquires the lock

        # Act & Assert
        with pytest.raises(IndexError, match="out of range"):
            engine._synthesize(0, "paola")
