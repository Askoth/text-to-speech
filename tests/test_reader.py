"""
tests/test_reader.py
Tests for the functions in reader.py and related modules.

Covers: voice configuration constants, Markdown converter (edge cases),
download_piper_voice (synthesis), concat_wav, show_paragraph,
calc_output_path, read_with_piper, main.
"""

import asyncio
import io
import tempfile
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import PiperVoices, Voice


def _registry(tmp_path: Path, existing: tuple[str, ...] = ()) -> PiperVoices:
    """'paola' registry with model/json under tmp_path (create files in existing)."""
    with patch("src.config.VOICE_DIR", tmp_path):
        voice = Voice(
            name="paola",
            gender="F",
            lang="it",
            multilingual=False,
            url_model="http://example.com/model.onnx",
            url_json="http://example.com/model.onnx.json",
        )
    for name in existing:
        (tmp_path / name).touch()
    return PiperVoices([voice])


# ===========================================================================
# Tests — voice configuration constants
# ===========================================================================


class TestVoiceConstants:
    """Verify consistency among the voice configuration constants."""

    def test_all_voices_is_sorted(self):
        """ALL_VOICES must be sorted alphabetically."""
        from src.config import ALL_VOICES

        # Assert
        assert sorted(ALL_VOICES) == ALL_VOICES

    def test_all_voices_no_duplicates(self):
        """ALL_VOICES must not have duplicates."""
        from src.config import ALL_VOICES

        # Assert
        assert len(ALL_VOICES) == len(set(ALL_VOICES))

    def test_default_voice_exists(self):
        """DEFAULT_VOICE must be present in ALL_VOICES."""
        from src.config import ALL_VOICES, DEFAULT_VOICE

        # Assert
        assert DEFAULT_VOICE in ALL_VOICES

    def test_voice_urls_point_to_existing_files(self):
        """Every Piper voice must have model, json and the download URLs."""
        from src.config import PIPER_VOICES

        for voice in PIPER_VOICES.voices:
            assert voice.model, f"voice {voice.name} without model"
            assert voice.json, f"voice {voice.name} without json"
            assert voice.url_model, f"voice {voice.name} without url_model"
            assert voice.url_json, f"voice {voice.name} without url_json"

    def test_voice_model_path_uses_home_directory(self):
        """VOICE_DIR must be under the user's home directory."""
        from src.config import VOICE_DIR

        # Assert
        assert str(VOICE_DIR).startswith(str(Path.home()))


# ===========================================================================
# Tests — file_to_text (Markdown edge cases, regex fallback)
# ===========================================================================


class TestMarkdownToTextEdgeCases:
    """Tests for edge cases of the Markdown regex parser (without pandoc)."""

    def _convert(self, markdown: str) -> str:
        """Helper: convert markdown via a temp file with the regex fallback forced."""
        from src.converters import file_to_text

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(markdown)
            tmp_path = Path(f.name)
        try:
            with patch("src.converters.shutil.which", return_value=None):
                return file_to_text(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_removes_markdown_tables(self):
        """Table rows with | must be removed."""
        # Arrange
        md = "| Col1 | Col2 |\n|------|------|\n| A | B |\n\nTesto dopo."

        # Act
        result = self._convert(md)

        # Assert
        assert "|" not in result
        assert "Testo dopo." in result

    def test_removes_images(self):
        """Images ![alt](url) must be removed completely."""
        # Arrange
        md = "Prima. ![screenshot](img.png) Dopo."

        # Act
        result = self._convert(md)

        # Assert — the contract says: images must be removed
        assert "img.png" not in result
        assert "screenshot" not in result

    def test_removes_horizontal_separators(self):
        """The --- and *** separators must be removed."""
        # Arrange
        md = "Prima\n\n---\n\nDopo\n\n***\n\nFine"

        # Act
        result = self._convert(md)

        # Assert
        assert "---" not in result
        assert "***" not in result
        assert "Prima" in result
        assert "Fine" in result

    def test_removes_bullet_list_markers(self):
        """List markers (- * +) must be removed."""
        # Arrange
        md = "- Primo elemento\n- Secondo elemento\n* Terzo\n+ Quarto"

        # Act
        result = self._convert(md)

        # Assert
        assert "Primo elemento" in result
        assert "Secondo elemento" in result
        # Must not start with markers
        for line in result.strip().split("\n"):
            stripped = line.strip()
            if stripped:
                assert not stripped.startswith("- "), f"Marker not removed: '{line}'"
                assert not stripped.startswith("* "), f"Marker not removed: '{line}'"
                assert not stripped.startswith("+ "), f"Marker not removed: '{line}'"

    def test_unicode_text_preserved(self):
        """Unicode text (accents, emoji) must be preserved."""
        # Arrange
        md = "# Caffè e più\n\nÈ una giornata bellissima."

        # Act
        result = self._convert(md)

        # Assert
        assert "Caffè e più" in result
        assert "È una giornata bellissima." in result

    def test_multiple_blank_lines_collapsed(self):
        """More than 2 consecutive empty lines must be collapsed to 2."""
        # Arrange
        md = "Primo\n\n\n\n\n\nSecondo"

        # Act
        result = self._convert(md)

        # Assert — must not have more than 2 consecutive newlines
        assert "\n\n\n" not in result

    def test_nested_formatting(self):
        """Bold inside italic and vice versa must be removed."""
        # Arrange
        md = "Testo ***grassetto e corsivo*** qui."

        # Act
        result = self._convert(md)

        # Assert
        assert "***" not in result
        assert "grassetto e corsivo" in result

    def test_inline_code_removed(self):
        """Inline code `code` must be removed."""
        # Arrange
        md = "Usa `pip install` per installare."

        # Act
        result = self._convert(md)

        # Assert
        assert "`" not in result

    def test_multiline_code_block_removed(self):
        """Multiline code blocks must be removed completely."""
        # Arrange
        md = "Prima.\n\n```python\ndef foo():\n    return 42\n```\n\nDopo."

        # Act
        result = self._convert(md)

        # Assert
        assert "def foo" not in result
        assert "```" not in result
        assert "Prima." in result
        assert "Dopo." in result

    def test_only_whitespace_returns_empty(self):
        """A file with only spaces and newlines must return an empty string."""
        # Arrange
        md = "   \n\n   \n   "

        # Act
        result = self._convert(md)

        # Assert
        assert result == ""


# ===========================================================================
# Tests — file_to_text with pandoc
# ===========================================================================


class TestMarkdownToTextWithPandoc:
    """Tests for the pandoc path of the Markdown converter."""

    def test_uses_pandoc_when_available(self):
        """Must use pandoc if it is available in PATH."""
        from src.converters import file_to_text

        # Arrange
        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("# Titolo\n\nTesto semplice.")
            tmp_path = Path(f.name)

        try:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Titolo\n\nTesto semplice."

            with (
                patch("src.converters.shutil.which", return_value="/usr/bin/pandoc"),
                patch("src.converters.subprocess.run", return_value=mock_result) as mock_run,
            ):
                # Act
                result = file_to_text(tmp_path)

            # Assert
            mock_run.assert_called_once()
            assert "Titolo" in result
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_regex_fallback_if_pandoc_fails(self):
        """If pandoc returns an error, it must fall back to the regex."""
        from src.converters import file_to_text

        # Arrange
        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("# Titolo\n\nContenuto.")
            tmp_path = Path(f.name)

        try:
            mock_result = MagicMock()
            mock_result.returncode = 1  # pandoc fails
            mock_result.stdout = ""

            with (
                patch("src.converters.shutil.which", return_value="/usr/bin/pandoc"),
                patch("src.converters.subprocess.run", return_value=mock_result),
            ):
                # Act
                result = file_to_text(tmp_path)

            # Assert — the regex fallback must still work
            assert "#" not in result
            assert "Titolo" in result
            assert "Contenuto." in result
        finally:
            tmp_path.unlink(missing_ok=True)


# ===========================================================================
# Tests — concat_wav
# ===========================================================================


class TestConcatWav:
    """Tests for the concat_wav function."""

    def _make_wav(self, sample_rate: int, n_frames: int = 100) -> bytes:
        """Helper: create a valid WAV in memory."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * n_frames)
        return buf.getvalue()

    def test_concatenates_two_wav(self):
        """Two concatenated WAVs must have the sum of their frames."""
        from src.reader import concat_wav

        # Arrange
        sr = 22050
        wav1 = self._make_wav(sr, n_frames=100)
        wav2 = self._make_wav(sr, n_frames=200)

        # Act
        result = concat_wav([wav1, wav2], sr)

        # Assert
        with wave.open(io.BytesIO(result), "rb") as wf:
            assert wf.getnframes() == 300
            assert wf.getframerate() == sr
            assert wf.getnchannels() == 1

    def test_concatenates_empty_list(self):
        """An empty list must produce a valid WAV with 0 frames."""
        from src.reader import concat_wav

        # Arrange & Act
        result = concat_wav([], 22050)

        # Assert
        with wave.open(io.BytesIO(result), "rb") as wf:
            assert wf.getnframes() == 0

    def test_concatenates_single_wav(self):
        """A single WAV must return a WAV with the same frames."""
        from src.reader import concat_wav

        # Arrange
        sr = 16000
        wav1 = self._make_wav(sr, n_frames=50)

        # Act
        result = concat_wav([wav1], sr)

        # Assert
        with wave.open(io.BytesIO(result), "rb") as wf:
            assert wf.getnframes() == 50


# ===========================================================================
# Tests — download_piper_voice
# ===========================================================================


class TestDownloadPiperVoice:
    """Tests for the Piper model download (with a network mock)."""

    def test_skip_download_if_files_exist(self, tmp_path):
        """Must not download if the model files already exist."""
        from src.synthesis import download_piper_voice

        # Arrange — files already present in tmp_path
        registry = _registry(tmp_path, existing=("model.onnx", "model.onnx.json"))

        with (
            patch("src.synthesis.VOICE_DIR", tmp_path),
            patch("src.synthesis.PIPER_VOICES", registry),
            patch("src.synthesis.urllib.request.urlopen") as mock_urlopen,
        ):
            # Act
            download_piper_voice("paola")

            # Assert — urlopen must not be called (everything already downloaded)
            mock_urlopen.assert_not_called()

    def test_creates_directory_if_not_exists(self, tmp_path):
        """Must create the models directory with parents=True."""
        from src.synthesis import download_piper_voice

        # Arrange — files present, only mkdir is verified
        registry = _registry(tmp_path, existing=("model.onnx", "model.onnx.json"))

        with (
            patch("src.synthesis.VOICE_DIR") as mock_dir,
            patch("src.synthesis.PIPER_VOICES", registry),
        ):
            # Act
            download_piper_voice("paola")

            # Assert
            mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)


# ===========================================================================
# Tests — cross-platform: _find_player, _has_player, suggest_installation
# ===========================================================================


class TestFindPlayer:
    """Tests for the audio player selection based on the OS."""

    def test_linux_wav_with_aplay(self):
        """On Linux with aplay available, must use aplay for WAV."""
        from src.reader import _find_player

        # Arrange & Act
        with (
            patch("src.reader.PLATFORM", "linux"),
            patch("src.reader.shutil.which", return_value="/usr/bin/aplay"),
        ):
            cmd, stdin = _find_player("wav")

        # Assert
        assert cmd[0] == "aplay"
        assert stdin is True

    def test_linux_mp3_with_ffplay(self):
        """On Linux must use ffplay for MP3."""
        from src.reader import _find_player

        # Arrange & Act
        with (
            patch("src.reader.PLATFORM", "linux"),
            patch("src.reader.shutil.which", return_value="/usr/bin/ffplay"),
        ):
            cmd, stdin = _find_player("mp3")

        # Assert
        assert cmd[0] == "ffplay"
        assert stdin is True

    def test_darwin_with_afplay(self):
        """On macOS with afplay available, must use afplay."""
        from src.reader import _find_player

        # Arrange & Act
        with (
            patch("src.reader.PLATFORM", "darwin"),
            patch("src.reader.shutil.which", return_value="/usr/bin/afplay"),
        ):
            cmd, stdin = _find_player("mp3")

        # Assert
        assert cmd == ["afplay"]
        assert stdin is False

    def test_darwin_fallback_ffplay(self):
        """On macOS without afplay, must use ffplay as a fallback."""
        from src.reader import _find_player

        # Arrange
        def which_side_effect(name):
            return "/usr/bin/ffplay" if name == "ffplay" else None

        # Act
        with (
            patch("src.reader.PLATFORM", "darwin"),
            patch("src.reader.shutil.which", side_effect=which_side_effect),
        ):
            cmd, stdin = _find_player("mp3")

        # Assert
        assert cmd[0] == "ffplay"
        assert stdin is True

    def test_win32_with_ffplay(self):
        """On Windows with ffplay, must use ffplay."""
        from src.reader import _find_player

        # Arrange & Act
        with (
            patch("src.reader.PLATFORM", "win32"),
            patch("src.reader.shutil.which", return_value="C:\\ffplay.exe"),
        ):
            cmd, stdin = _find_player("wav")

        # Assert
        assert cmd[0] == "ffplay"
        assert stdin is True

    def test_no_player_available(self):
        """Without a player, must return an empty list."""
        from src.reader import _find_player

        # Arrange & Act
        with (
            patch("src.reader.PLATFORM", "linux"),
            patch("src.reader.shutil.which", return_value=None),
        ):
            cmd, stdin = _find_player("wav")

        # Assert
        assert cmd == []
        assert stdin is False


class TestHasPlayer:
    """Tests for the player availability check."""

    def test_has_player_true(self):
        """Must return True if a player is available."""
        from src.reader import _has_player

        # Arrange & Act
        with (
            patch("src.reader.PLATFORM", "linux"),
            patch("src.reader.shutil.which", return_value="/usr/bin/aplay"),
        ):
            result = _has_player("wav")

        # Assert
        assert result is True

    def test_has_player_false(self):
        """Must return False if no player is available."""
        from src.reader import _has_player

        # Arrange & Act
        with (
            patch("src.reader.PLATFORM", "win32"),
            patch("src.reader.shutil.which", return_value=None),
        ):
            result = _has_player("mp3")

        # Assert
        assert result is False


class TestSuggestInstallation:
    """Tests for the OS-specific installation messages."""

    def test_linux_ffmpeg(self):
        """On Linux must suggest apt/dnf/pacman for ffmpeg."""
        from src.config import suggest_installation

        # Act
        with patch("src.config.PLATFORM", "linux"):
            msg = suggest_installation("ffmpeg")

        # Assert
        assert "apt" in msg

    def test_darwin_ffmpeg(self):
        """On macOS must suggest brew for ffmpeg."""
        from src.config import suggest_installation

        # Act
        with patch("src.config.PLATFORM", "darwin"):
            msg = suggest_installation("ffmpeg")

        # Assert
        assert "brew" in msg

    def test_win32_ffmpeg(self):
        """On Windows must suggest choco/scoop for ffmpeg."""
        from src.config import suggest_installation

        # Act
        with patch("src.config.PLATFORM", "win32"):
            msg = suggest_installation("ffmpeg")

        # Assert
        assert "choco" in msg

    def test_unknown_package(self):
        """For unmapped packages must return a generic message."""
        from src.config import suggest_installation

        # Act
        with patch("src.config.PLATFORM", "linux"):
            msg = suggest_installation("nonexistent_package")

        # Assert
        assert "package manager" in msg


# ===========================================================================
# Tests — check_prerequisites
# ===========================================================================


class TestCheckPrerequisites:
    """Tests for the system dependency check at startup."""

    def test_all_present_no_error(self):
        """With all dependencies present, must return an empty list."""
        from src.config import check_prerequisites

        # Arrange & Act
        with (
            patch("src.config.PLATFORM", "linux"),
            patch("src.config.shutil.which", return_value="/usr/bin/found"),
        ):
            errors = check_prerequisites(mode="cli")

        # Assert
        assert errors == []

    def test_missing_ffmpeg_critical_error(self):
        """Without ffmpeg must return a critical error."""
        from src.config import check_prerequisites

        # Arrange
        def which_side_effect(name):
            return None if name == "ffmpeg" else "/usr/bin/found"

        # Act
        with (
            patch("src.config.PLATFORM", "linux"),
            patch("src.config.shutil.which", side_effect=which_side_effect),
        ):
            errors = check_prerequisites(mode="cli")

        # Assert
        assert "ffmpeg" in errors

    def test_web_mode_does_not_check_player(self):
        """In web mode must not check the audio player."""
        from src.config import check_prerequisites

        # Arrange
        def which_side_effect(name):
            if name == "ffmpeg":
                return "/usr/bin/ffmpeg"
            if name == "pandoc":
                return "/usr/bin/pandoc"
            return None  # no audio player

        # Act
        with (
            patch("src.config.PLATFORM", "linux"),
            patch("src.config.shutil.which", side_effect=which_side_effect),
        ):
            errors = check_prerequisites(mode="web")

        # Assert — no error, even without a player
        assert errors == []

    def test_missing_pandoc_only_warning(self, capsys):
        """Missing pandoc must generate a warning, not a critical error."""
        from src.config import check_prerequisites

        # Arrange
        def which_side_effect(name):
            if name == "pandoc":
                return None
            return "/usr/bin/found"

        # Act
        with (
            patch("src.config.PLATFORM", "linux"),
            patch("src.config.shutil.which", side_effect=which_side_effect),
        ):
            errors = check_prerequisites(mode="cli")

        # Assert
        assert errors == []
        captured = capsys.readouterr()
        assert "pandoc" in captured.out

    def test_darwin_without_player_prints_warning(self, capsys):
        """On darwin CLI, without afplay or ffplay, must print a player warning."""
        from src.config import check_prerequisites

        # Arrange — ffmpeg and pandoc present, no player
        def which_side_effect(name):
            if name in ("afplay", "ffplay"):
                return None
            return "/usr/bin/found"

        # Act
        with (
            patch("src.config.PLATFORM", "darwin"),
            patch("src.config.shutil.which", side_effect=which_side_effect),
        ):
            errors = check_prerequisites(mode="cli")

        # Assert — no critical error, but warning printed
        assert errors == []
        captured = capsys.readouterr()
        assert "player" in captured.out.lower() or "player" in captured.err.lower()

    def test_darwin_with_afplay_no_player_warning(self, capsys):
        """On darwin CLI with afplay available, must NOT warn about the player."""
        from src.config import check_prerequisites

        # Arrange — everything present, including afplay
        def which_side_effect(name):
            return f"/usr/bin/{name}"

        # Act
        with (
            patch("src.config.PLATFORM", "darwin"),
            patch("src.config.shutil.which", side_effect=which_side_effect),
        ):
            errors = check_prerequisites(mode="cli")

        # Assert — no error, no player warning in the output
        assert errors == []
        captured = capsys.readouterr()
        # Must not warn about the absence of a player
        assert "No audio player" not in captured.out
        assert "No audio player" not in captured.err

    def test_win32_without_ffplay_prints_warning(self, capsys):
        """On win32 CLI, without ffplay, must print a player warning."""
        from src.config import check_prerequisites

        # Arrange — ffmpeg and pandoc present, ffplay missing
        def which_side_effect(name):
            if name == "ffplay":
                return None
            return "C:\\tools\\found.exe"

        # Act
        with (
            patch("src.config.PLATFORM", "win32"),
            patch("src.config.shutil.which", side_effect=which_side_effect),
        ):
            errors = check_prerequisites(mode="cli")

        # Assert — no critical error, warning printed
        assert errors == []
        captured = capsys.readouterr()
        assert "player" in captured.out.lower() or "player" in captured.err.lower()


# ===========================================================================
# Tests — show_paragraph
# ===========================================================================


class TestShowParagraph:
    """Tests for the terminal display function."""

    def test_does_not_print_if_not_visible(self, capsys):
        """If visible=False, must not print anything."""
        from src.reader import show_paragraph

        # Act
        show_paragraph(1, 10, "Testo del paragrafo", visible=False)

        # Assert
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_prints_if_visible(self, capsys):
        """If visible=True, must print the counter and the text."""
        from src.reader import show_paragraph

        # Act
        show_paragraph(3, 10, "Contenuto paragrafo", visible=True)

        # Assert
        captured = capsys.readouterr()
        assert "3/10" in captured.out
        assert "Contenuto paragrafo" in captured.out


# ===========================================================================
# Tests — calc_output_path
# ===========================================================================


class TestCalcOutputPath:
    """Tests for the output directory calculation."""

    def test_correct_output_structure(self):
        """Must return base_dir, full MP3 path and paragraphs directory."""
        from src.reader import calc_output_path

        # Act
        base_dir, mp3_path, paragraphs_dir = calc_output_path(Path("data/input/documento.md"))

        # Assert
        assert base_dir.name == "documento"
        assert mp3_path.name == "documento.mp3"
        assert mp3_path.parent.name == "full"
        assert paragraphs_dir.name == "paragraphs"

    def test_mp3_path_inside_full(self):
        """The MP3 file must be in base_dir/full/."""
        from src.reader import calc_output_path

        _, mp3_path, _ = calc_output_path(Path("test.epub"))

        assert mp3_path.parts[-2] == "full"
        assert mp3_path.suffix == ".mp3"
        assert mp3_path.stem == "test"

    def test_paragraphs_folder_inside_base(self):
        """The paragraphs folder must be in base_dir/paragraphs/."""
        from src.reader import calc_output_path

        base_dir, _, paragraphs_dir = calc_output_path(Path("libro.pdf"))

        assert paragraphs_dir.parent == base_dir
        assert paragraphs_dir.name == "paragraphs"

    def test_extension_does_not_affect_stem(self):
        """The stem must be the file name without extension."""
        from src.reader import calc_output_path

        for ext in [".md", ".txt", ".epub", ".docx", ".pdf"]:
            _, mp3_path, _ = calc_output_path(Path(f"mio_file{ext}"))
            assert mp3_path.stem == "mio_file"

    def test_file_with_complex_path(self):
        """Must use only the stem, ignoring parent directories."""
        from src.reader import calc_output_path

        base_dir, _, _ = calc_output_path(Path("/home/user/documenti/relazione.md"))

        assert base_dir.name == "relazione"


# ===========================================================================
# Tests — read_with_piper
# ===========================================================================


class TestReadWithPiper:
    """Tests for the CLI reading with Piper TTS."""

    def _make_wav_bytes(self, sample_rate: int = 22050) -> bytes:
        """Helper: create a valid WAV in memory."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * 100)
        return buf.getvalue()

    def test_exits_if_piper_not_installed(self):
        """Must exit with sys.exit(1) if piper is not importable."""
        from src.reader import read_with_piper

        with (
            patch.dict("sys.modules", {"piper": None}),
            pytest.raises(SystemExit, match="1"),
        ):
            read_with_piper("Testo di prova")

    def test_exits_if_no_player_and_no_save(self):
        """Must exit if there is no audio player and nothing is saved."""
        from src.reader import read_with_piper

        mock_piper_module = MagicMock()
        with (
            patch.dict("sys.modules", {"piper": mock_piper_module}),
            patch("src.reader._has_player", return_value=False),
            pytest.raises(SystemExit, match="1"),
        ):
            read_with_piper("Testo di prova", save_path=None)

    def test_synthesizes_and_plays_paragraphs(self):
        """Must synthesize and play every paragraph."""
        from src.reader import read_with_piper

        wav = self._make_wav_bytes()
        mock_piper_module = MagicMock()
        mock_voice = MagicMock()
        mock_voice.config.sample_rate = 22050
        mock_piper_module.PiperVoice.load.return_value = mock_voice

        with (
            patch.dict("sys.modules", {"piper": mock_piper_module}),
            patch("src.reader._has_player", return_value=True),
            patch("src.reader.synthesize_piper", return_value=wav) as mock_synth,
            patch("src.reader.play_audio") as mock_play,
            patch("src.reader.show_paragraph"),
        ):
            read_with_piper("Primo paragrafo\n\nSecondo paragrafo")

        assert mock_synth.call_count == 2
        assert mock_play.call_count == 2

    def test_saves_mp3_without_playing(self, tmp_path):
        """With save_path and no player, must save without playing."""
        from src.reader import read_with_piper

        wav = self._make_wav_bytes()
        mock_piper_module = MagicMock()
        mock_voice = MagicMock()
        mock_voice.config.sample_rate = 22050
        mock_piper_module.PiperVoice.load.return_value = mock_voice

        save = tmp_path / "output.mp3"
        paragraphs_dir = tmp_path / "paragraphs"

        with (
            patch.dict("sys.modules", {"piper": mock_piper_module}),
            patch("src.reader._has_player", return_value=False),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("src.reader.synthesize_piper", return_value=wav),
            patch("src.reader.wav_to_mp3") as mock_mp3,
            patch("src.reader.concat_wav", return_value=wav),
            patch("src.reader.play_audio") as mock_play,
            patch("src.reader.show_paragraph"),
        ):
            read_with_piper("Un paragrafo", save_path=save, paragraphs_dir=paragraphs_dir)

        # Must not play
        mock_play.assert_not_called()
        # Must save: 1 single paragraph + 1 full file
        assert mock_mp3.call_count == 2


# ===========================================================================
# Tests — main
# ===========================================================================


class TestMain:
    """Tests for the CLI entry point."""

    def test_file_not_found_exits(self):
        """Must exit if the file does not exist."""
        from src.reader import main

        with (
            patch("sys.argv", ["reader.py", "/non_esiste_12345.md"]),
            patch("src.reader.check_prerequisites", return_value=[]),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_empty_file_exits(self, tmp_path):
        """Must exit if the file is empty after conversion."""
        from src.reader import main

        empty = tmp_path / "vuoto.txt"
        empty.write_text("")

        with (
            patch("sys.argv", ["reader.py", str(empty)]),
            patch("src.reader.check_prerequisites", return_value=[]),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_prerequisites_failed_exits(self, tmp_path):
        """Must exit if check_prerequisites returns errors."""
        from src.reader import main

        f = tmp_path / "test.txt"
        f.write_text("contenuto")

        with (
            patch("sys.argv", ["reader.py", str(f)]),
            patch("src.reader.check_prerequisites", return_value=["ffmpeg"]),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_voice_piper_calls_read_with_piper(self, tmp_path):
        """With --voice paola must call download_piper_voice + read_with_piper."""
        from src.reader import main

        f = tmp_path / "test.txt"
        f.write_text("Contenuto test")

        with (
            patch("sys.argv", ["reader.py", str(f), "--voice", "paola"]),
            patch("src.reader.check_prerequisites", return_value=[]),
            patch("src.reader.download_piper_voice") as mock_download,
            patch("src.reader.read_with_piper") as mock_read,
        ):
            main()

        mock_download.assert_called_once()
        mock_read.assert_called_once()


# ===========================================================================
# Tests — wav_to_mp3
# ===========================================================================


class TestWavToMp3:
    """Tests for the WAV → MP3 conversion via ffmpeg."""

    def test_calls_ffmpeg_with_correct_arguments(self, tmp_path):
        """Must call subprocess.run with the correct ffmpeg flags."""
        from src.reader import wav_to_mp3

        # Arrange
        output = tmp_path / "output.mp3"
        audio = b"\x00" * 100

        with patch("src.reader.subprocess.run") as mock_run:
            # Act
            wav_to_mp3(audio, output)

        # Assert — ffmpeg invoked with the right parameters
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "pipe:0" in cmd
        assert "libmp3lame" in cmd
        assert str(output) in cmd

    def test_passes_wav_bytes_as_stdin(self, tmp_path):
        """The WAV bytes must be passed as stdin to ffmpeg."""
        from src.reader import wav_to_mp3

        # Arrange
        output = tmp_path / "output.mp3"
        audio = b"\xde\xad\xbe\xef"

        with patch("src.reader.subprocess.run") as mock_run:
            # Act
            wav_to_mp3(audio, output)

        # Assert
        kwargs = mock_run.call_args[1]
        assert kwargs["input"] == audio
        assert kwargs["check"] is True

    def test_timeout_set_to_30(self, tmp_path):
        """Must set timeout=30 to avoid infinite blocking."""
        from src.reader import wav_to_mp3

        # Arrange
        output = tmp_path / "output.mp3"

        with patch("src.reader.subprocess.run") as mock_run:
            # Act
            wav_to_mp3(b"", output)

        # Assert
        assert mock_run.call_args[1]["timeout"] == 30


# ===========================================================================
# Tests — concat_mp3
# ===========================================================================


class TestConcatMp3:
    """Tests for the MP3 concatenation via ffmpeg."""

    def test_calls_ffmpeg_with_concat_filter(self, tmp_path):
        """Must use ffmpeg's concat filter."""
        from src.reader import concat_mp3

        # Arrange
        output = tmp_path / "completo.mp3"
        fragments = [b"\x01" * 50, b"\x02" * 50]

        with patch("src.reader.subprocess.run") as mock_run:
            # Act
            concat_mp3(fragments, output)

        # Assert
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert any("concat" in arg for arg in cmd)
        assert str(output) in cmd

    def test_joins_all_fragments_as_stdin(self, tmp_path):
        """The bytes of all fragments must be concatenated and passed as stdin."""
        from src.reader import concat_mp3

        # Arrange
        output = tmp_path / "completo.mp3"
        fragments = [b"AAA", b"BBB", b"CCC"]

        with patch("src.reader.subprocess.run") as mock_run:
            # Act
            concat_mp3(fragments, output)

        # Assert
        kwargs = mock_run.call_args[1]
        assert kwargs["input"] == b"AAABBBCCC"
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 30


# ===========================================================================
# Tests — play_audio
# ===========================================================================


class TestPlayAudio:
    """Tests for audio playback with player fallback."""

    def test_no_player_does_not_call_subprocess(self):
        """Without a player available must not call subprocess.run."""
        from src.reader import play_audio

        # Arrange
        with (
            patch("src.reader._find_player", return_value=([], False)),
            patch("src.reader.subprocess.run") as mock_run,
        ):
            # Act
            play_audio(b"\x00" * 10, "mp3")

        # Assert
        mock_run.assert_not_called()

    def test_stdin_path_passes_bytes_directly(self):
        """With a stdin-compatible player, must pass the bytes as stdin."""
        from src.reader import play_audio

        # Arrange
        audio = b"\xab" * 20
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-"]

        with (
            patch("src.reader._find_player", return_value=(cmd, True)),
            patch("src.reader.subprocess.run") as mock_run,
        ):
            # Act
            play_audio(audio, "mp3")

        # Assert
        mock_run.assert_called_once()
        assert mock_run.call_args[1]["input"] == audio
        assert mock_run.call_args[0][0] == cmd

    def test_tempfile_path_launches_player_with_file_path(self):
        """With afplay (no stdin), the command must include the temp file path."""
        from src.reader import play_audio

        # Arrange
        audio = b"\xff" * 30
        cmd = ["afplay"]

        with (
            patch("src.reader._find_player", return_value=(cmd, False)),
            patch("src.reader.subprocess.run") as mock_run,
        ):
            # Act
            play_audio(audio, "mp3")

        # Assert — command = ["afplay", "/tmp/xxx.mp3"]
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "afplay"
        assert len(called_cmd) == 2
        assert called_cmd[1].endswith(".mp3")

    def test_tempfile_removed_after_playback(self, tmp_path):
        """The temporary file must be removed after playback."""
        from src.reader import play_audio

        # Arrange — create a real temporary file to verify deletion
        fake_tmp = tmp_path / "audio_test.mp3"
        fake_tmp.write_bytes(b"\x00")
        tmp_name = str(fake_tmp)

        class FakeTmp:
            name = tmp_name

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def write(self, data):
                pass

        # tempfile is imported inline in play_audio: patch at the module level
        with (
            patch("src.reader._find_player", return_value=(["afplay"], False)),
            patch("src.reader.subprocess.run"),
            patch("tempfile.NamedTemporaryFile", return_value=FakeTmp()),
        ):
            # Act
            play_audio(b"\x00", "mp3")

        # Assert — the file must have been deleted
        assert not fake_tmp.exists()


# ===========================================================================
# Tests — read_with_piper (additional paths)
# ===========================================================================


class TestReadWithPiperExtra:
    """Tests for the paths not covered in read_with_piper."""

    def _make_wav_bytes(self, sample_rate: int = 22050) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * 100)
        return buf.getvalue()

    def test_exits_if_save_path_and_ffmpeg_not_found(self, tmp_path):
        """Must exit with sys.exit(1) if save_path is given but ffmpeg is missing."""
        from src.reader import read_with_piper

        # Arrange
        mock_piper_module = MagicMock()
        save = Path(tmp_path / "output.mp3")

        with (
            patch.dict("sys.modules", {"piper": mock_piper_module}),
            patch("src.reader._has_player", return_value=True),
            patch("src.reader.shutil.which", return_value=None),
            pytest.raises(SystemExit, match="1"),
        ):
            # Act
            read_with_piper("Un testo", save_path=save)

    def test_keyboard_interrupt_handled_gracefully(self):
        """A KeyboardInterrupt during reading must terminate without propagating."""
        from src.reader import read_with_piper

        # Arrange
        mock_piper_module = MagicMock()
        mock_voice = MagicMock()
        mock_voice.config.sample_rate = 22050
        mock_piper_module.PiperVoice.load.return_value = mock_voice

        wav = self._make_wav_bytes()

        class SideEffect:
            def __init__(self, n):
                self.n = n

            def __call__(self, *a, **k):
                if self.n > 0:
                    self.n -= 1
                    return wav
                raise KeyboardInterrupt

        with (
            patch.dict("sys.modules", {"piper": mock_piper_module}),
            patch("src.reader._has_player", return_value=True),
            patch("src.reader.synthesize_piper", side_effect=SideEffect(2)),
            patch("src.reader.play_audio"),
            patch("src.reader.show_paragraph"),
        ):
            # Act — must not raise
            read_with_piper("Paragrafo uno\n\nParagrafo due")


# ===========================================================================
# Tests — _play_async
# ===========================================================================


class TestPlayAsync:
    """Tests for the audio playback with subprocesses (async)."""

    def test_stdin_path_uses_create_subprocess_exec_with_pipe(self):
        """For stdin-compatible players it must open the process with stdin=PIPE."""
        from src.reader import _play_async

        # Arrange
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-"]
        mp3 = b"\xff\xfb" + b"\x00" * 48

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch("src.reader._find_player", return_value=(cmd, True)),
            patch(
                "src.reader.asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ) as mock_exec,
        ):
            # Act
            asyncio.run(_play_async(mp3))

        # Assert
        mock_exec.assert_called_once()
        assert mock_exec.call_args[1]["stdin"] == asyncio.subprocess.PIPE

    def test_stdin_path_passes_bytes_to_communicate(self):
        """The MP3 bytes must be passed to proc.communicate(input=...)."""
        from src.reader import _play_async

        # Arrange
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-"]
        mp3 = b"\xaa\xbb\xcc"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch("src.reader._find_player", return_value=(cmd, True)),
            patch("src.reader.asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            # Act
            asyncio.run(_play_async(mp3))

        # Assert
        mock_proc.communicate.assert_called_once_with(input=mp3)

    def test_no_player_returns_without_subprocess(self):
        """Without a player available it must return without creating processes."""
        from src.reader import _play_async

        # Arrange
        with (
            patch("src.reader._find_player", return_value=([], False)),
            patch("src.reader.asyncio.create_subprocess_exec") as mock_exec,
        ):
            # Act
            asyncio.run(_play_async(b"\x00"))

        # Assert
        mock_exec.assert_not_called()

    def test_tempfile_path_uses_proc_wait(self):
        """With afplay (no stdin) it must call proc.wait(), not proc.communicate()."""
        from src.reader import _play_async

        # Arrange
        cmd = ["afplay"]
        mp3 = b"\xff" * 20

        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with (
            patch("src.reader._find_player", return_value=(cmd, False)),
            patch(
                "src.reader.asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ) as mock_exec,
        ):
            # Act
            asyncio.run(_play_async(mp3))

        # Assert — proc.wait() is called, communicate() is not
        mock_proc.wait.assert_called_once()
        mock_proc.communicate.assert_not_called()
        # afplay + temp file path
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "afplay"
        assert call_args[-1].endswith(".mp3")

    def test_tempfile_removed_after_playback(self, tmp_path):
        """The temporary file must be removed after playback."""
        from src.reader import _play_async

        # Arrange
        cmd = ["afplay"]
        fake_tmp = tmp_path / "audio_tmp.mp3"
        fake_tmp.write_bytes(b"\x00")
        tmp_name = str(fake_tmp)

        class FakeTmp:
            name = tmp_name

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def write(self, data):
                pass

        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        # tempfile is imported inline in _play_async: patch in the global module
        with (
            patch("src.reader._find_player", return_value=(cmd, False)),
            patch("src.reader.asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("tempfile.NamedTemporaryFile", return_value=FakeTmp()),
        ):
            # Act
            asyncio.run(_play_async(b"\x00"))

        # Assert — the temp file no longer exists
        assert not fake_tmp.exists()
