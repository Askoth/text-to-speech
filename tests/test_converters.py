"""
tests/test_converters.py
Tests for the converters module: dispatcher and format converters.

Every converter is tested with real files created in tmp_path.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.converters import SUPPORTED_EXTENSIONS, file_to_text

# ===========================================================================
# Tests — Dispatcher file_to_text
# ===========================================================================


class TestFileToText:
    """Tests for the main dispatcher."""

    def test_unsupported_extension_raises_error(self, tmp_path):
        """A file with an unsupported extension must raise ValueError."""
        # Arrange
        file_csv = tmp_path / "dati.csv"
        file_csv.write_text("a,b,c")

        # Act & Assert
        with pytest.raises(ValueError, match="not supported"):
            file_to_text(file_csv)

    def test_supported_extensions_contains_all_formats(self):
        """SUPPORTED_EXTENSIONS must contain all the declared formats."""
        # Assert
        expected = {".md", ".txt", ".epub", ".docx", ".html", ".htm", ".pdf"}
        assert expected == SUPPORTED_EXTENSIONS

    def test_dispatcher_case_insensitive(self, tmp_path):
        """The extension must be case-insensitive."""
        # Arrange
        file_txt = tmp_path / "test.TXT"
        file_txt.write_text("Contenuto del file.")

        # Act
        result = file_to_text(file_txt)

        # Assert
        assert result == "Contenuto del file."


# ===========================================================================
# Tests — .txt converter
# ===========================================================================


class TestConvertText:
    """Tests for the plain-text file converter."""

    def test_reads_simple_text(self, tmp_path):
        """A .txt file must be read and returned unchanged."""
        # Arrange
        txt = tmp_path / "nota.txt"
        txt.write_text("Questa è una nota semplice.")

        # Act
        result = file_to_text(txt)

        # Assert
        assert result == "Questa è una nota semplice."

    def test_strip_whitespace(self, tmp_path):
        """Leading and trailing spaces must be removed."""
        # Arrange
        txt = tmp_path / "spazi.txt"
        txt.write_text("  \n\nContenuto con spazi.\n\n  ")

        # Act
        result = file_to_text(txt)

        # Assert
        assert result == "Contenuto con spazi."

    def test_empty_file(self, tmp_path):
        """An empty file must return an empty string."""
        # Arrange
        txt = tmp_path / "vuoto.txt"
        txt.write_text("")

        # Act
        result = file_to_text(txt)

        # Assert
        assert result == ""

    def test_unicode_preserved(self, tmp_path):
        """Unicode characters (accents, emoji) must be preserved."""
        # Arrange
        txt = tmp_path / "unicode.txt"
        txt.write_text("Caffè, più, naïve, 日本語")

        # Act
        result = file_to_text(txt)

        # Assert
        assert "Caffè" in result
        assert "日本語" in result

    def test_multiple_paragraphs(self, tmp_path):
        """Multiple paragraphs separated by blank lines must be preserved."""
        # Arrange
        txt = tmp_path / "multi.txt"
        txt.write_text("Primo paragrafo.\n\nSecondo paragrafo.\n\nTerzo.")

        # Act
        result = file_to_text(txt)

        # Assert
        assert "Primo paragrafo." in result
        assert "Secondo paragrafo." in result
        assert "Terzo." in result


# ===========================================================================
# Tests — .md converter (delegates to reader)
# ===========================================================================


class TestConvertMarkdown:
    """Tests for the Markdown converter (delegates to markdown_to_text)."""

    def test_removes_markdown_headers(self, tmp_path):
        """Markdown titles # must be removed from the text."""
        # Arrange
        md = tmp_path / "doc.md"
        md.write_text("# Titolo\n\nContenuto del documento.")

        # Act — force regex fallback (no pandoc)
        with patch("src.converters.shutil.which", return_value=None):
            result = file_to_text(md)

        # Assert
        assert "#" not in result
        assert "Titolo" in result
        assert "Contenuto del documento." in result


# ===========================================================================
# Tests — .docx converter
# ===========================================================================


class TestConvertDocx:
    """Tests for the Word DOCX converter."""

    def test_extracts_paragraphs(self, tmp_path):
        """A DOCX with paragraphs must return the separated text."""
        from docx import Document

        # Arrange
        docx_path = tmp_path / "documento.docx"
        doc = Document()
        doc.add_paragraph("Primo paragrafo del documento.")
        doc.add_paragraph("Secondo paragrafo con contenuto.")
        doc.save(str(docx_path))

        # Act
        result = file_to_text(docx_path)

        # Assert
        assert "Primo paragrafo del documento." in result
        assert "Secondo paragrafo con contenuto." in result

    def test_ignores_empty_paragraphs(self, tmp_path):
        """Empty paragraphs in the DOCX must be ignored."""
        from docx import Document

        # Arrange
        docx_path = tmp_path / "vuoti.docx"
        doc = Document()
        doc.add_paragraph("Testo valido.")
        doc.add_paragraph("")  # empty
        doc.add_paragraph("   ")  # whitespace only
        doc.add_paragraph("Altro testo.")
        doc.save(str(docx_path))

        # Act
        result = file_to_text(docx_path)
        paragraphs = [p for p in result.split("\n\n") if p.strip()]

        # Assert
        assert len(paragraphs) == 2

    def test_empty_docx(self, tmp_path):
        """A DOCX without content must return an empty string."""
        from docx import Document

        # Arrange
        docx_path = tmp_path / "empty.docx"
        doc = Document()
        doc.save(str(docx_path))

        # Act
        result = file_to_text(docx_path)

        # Assert
        assert result == ""


# ===========================================================================
# Tests — .html converter
# ===========================================================================


class TestConvertHtml:
    """Tests for the HTML converter."""

    def test_extracts_body_text(self, tmp_path):
        """The body text must be extracted."""
        # Arrange
        html = tmp_path / "pagina.html"
        html.write_text("""<!DOCTYPE html>
<html><head><title>Test</title></head>
<body><h1>Titolo</h1><p>Contenuto della pagina.</p></body>
</html>""")

        # Act
        result = file_to_text(html)

        # Assert
        assert "Titolo" in result
        assert "Contenuto della pagina." in result

    def test_removes_script_and_style(self, tmp_path):
        """Script and style tags must be removed."""
        # Arrange
        html = tmp_path / "scripts.html"
        html.write_text("""<html><body>
<script>alert('xss')</script>
<style>body { color: red; }</style>
<p>Testo visibile.</p>
</body></html>""")

        # Act
        result = file_to_text(html)

        # Assert
        assert "alert" not in result
        assert "color: red" not in result
        assert "Testo visibile." in result

    def test_removes_nav_header_footer(self, tmp_path):
        """Navigation elements must be removed."""
        # Arrange
        html = tmp_path / "layout.html"
        html.write_text("""<html><body>
<nav><a href="/">Home</a><a href="/about">About</a></nav>
<header><h1>Header del sito</h1></header>
<main><p>Contenuto principale.</p></main>
<footer><p>Copyright 2025</p></footer>
</body></html>""")

        # Act
        result = file_to_text(html)

        # Assert
        assert "Contenuto principale." in result
        assert "Home" not in result
        assert "About" not in result
        assert "Header del sito" not in result
        assert "Copyright" not in result

    def test_prefers_main_content(self, tmp_path):
        """If present, it must extract from <main> or <article>."""
        # Arrange
        html = tmp_path / "article.html"
        html.write_text("""<html><body>
<div class="sidebar">Menu laterale con molto testo.</div>
<main><p>Articolo importante.</p></main>
</body></html>""")

        # Act
        result = file_to_text(html)

        # Assert
        assert "Articolo importante." in result

    def test_html_extension_htm(self, tmp_path):
        """Also .htm must work like .html."""
        # Arrange
        htm = tmp_path / "pagina.htm"
        htm.write_text("<html><body><p>Testo HTM.</p></body></html>")

        # Act
        result = file_to_text(htm)

        # Assert
        assert "Testo HTM." in result


# ===========================================================================
# Tests — .pdf converter
# ===========================================================================


class TestConvertPdf:
    """Tests for the PDF converter."""

    def test_extracts_text_from_pdf(self, tmp_path):
        """A PDF with text must be extracted correctly."""
        import pymupdf

        # Arrange — create a test PDF with pymupdf
        pdf_path = tmp_path / "documento.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Primo paragrafo del documento PDF.")
        page.insert_text((72, 120), "Secondo paragrafo con contenuto.")
        doc.save(str(pdf_path))
        doc.close()

        # Act
        result = file_to_text(pdf_path)

        # Assert
        assert "Primo paragrafo del documento PDF." in result
        assert "Secondo paragrafo con contenuto." in result

    def test_multipage_pdf(self, tmp_path):
        """A PDF with multiple pages must extract text from all."""
        import pymupdf

        # Arrange
        pdf_path = tmp_path / "multi.pdf"
        doc = pymupdf.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text((72, 72), f"Contenuto pagina {i + 1}.")
        doc.save(str(pdf_path))
        doc.close()

        # Act
        result = file_to_text(pdf_path)

        # Assert
        assert "Contenuto pagina 1." in result
        assert "Contenuto pagina 2." in result
        assert "Contenuto pagina 3." in result

    def test_removes_isolated_page_numbers(self, tmp_path):
        """Isolated page numbers on a line must be removed."""
        import pymupdf

        # Arrange
        pdf_path = tmp_path / "paginato.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Testo del documento.")
        page.insert_text((300, 780), "1")  # page number at the bottom
        doc.save(str(pdf_path))
        doc.close()

        # Act
        result = file_to_text(pdf_path)

        # Assert
        assert "Testo del documento." in result
        # The isolated number "1" must be removed
        lines = [line.strip() for line in result.split("\n") if line.strip()]
        assert "1" not in lines


# ===========================================================================
# Tests — .epub converter
# ===========================================================================


class TestConvertEpub:
    """Tests for the EPUB converter."""

    def _make_epub(self, tmp_path: Path, chapters: list[str]) -> Path:
        """Helper: creates a minimal EPUB with the given chapters."""
        from ebooklib import epub  # type: ignore[import-untyped]

        book = epub.EpubBook()
        book.set_identifier("test-id-123")
        book.set_title("Test Book")
        book.set_language("it")

        items = []
        for i, text in enumerate(chapters):
            ch = epub.EpubHtml(
                title=f"Capitolo {i + 1}",
                file_name=f"chap_{i}.xhtml",
                lang="it",
            )
            ch.content = f"<html><body><p>{text}</p></body></html>".encode()
            book.add_item(ch)
            items.append(ch)

        book.toc = items
        book.spine = ["nav", *items]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub_path = tmp_path / "libro.epub"
        epub.write_epub(str(epub_path), book)
        return epub_path

    def test_extracts_chapter_text(self, tmp_path):
        """An EPUB with chapters must extract the text of each."""
        # Arrange
        epub_path = self._make_epub(
            tmp_path,
            ["Contenuto del primo capitolo.", "Contenuto del secondo capitolo."],
        )

        # Act
        result = file_to_text(epub_path)

        # Assert
        assert "Contenuto del primo capitolo." in result
        assert "Contenuto del secondo capitolo." in result

    def test_single_chapter_epub(self, tmp_path):
        """An EPUB with a single chapter must work."""
        # Arrange
        epub_path = self._make_epub(tmp_path, ["Unico capitolo del libro."])

        # Act
        result = file_to_text(epub_path)

        # Assert
        assert "Unico capitolo del libro." in result

    def test_epub_removes_script(self, tmp_path):
        """Any script tags in the EPUB must be removed."""
        from ebooklib import epub  # type: ignore[import-untyped]

        # Arrange
        book = epub.EpubBook()
        book.set_identifier("test-script")
        book.set_title("Script Test")
        book.set_language("it")

        ch = epub.EpubHtml(title="Cap", file_name="ch.xhtml", lang="it")
        ch.content = b"""<html><body>
<script>alert('evil')</script>
<p>Testo sicuro.</p>
</body></html>"""
        book.add_item(ch)
        book.spine = ["nav", ch]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub_path = tmp_path / "script.epub"
        epub.write_epub(str(epub_path), book)

        # Act
        result = file_to_text(epub_path)

        # Assert
        assert "alert" not in result
        assert "Testo sicuro." in result
