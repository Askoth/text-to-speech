"""
converters.py
Converters from files of various formats to plain text for TTS.

Supported formats: .md, .txt, .epub, .docx, .html, .htm, .pdf
Each converter returns clean text ready for speech synthesis.
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".md", ".txt", ".epub", ".docx", ".html", ".htm", ".pdf"}


def file_to_text(path: Path) -> str:
    """Convert a file to plain text based on its extension.

    Parameters
    ----------
    path : Path
        Path to the file to convert.

    Returns
    -------
    str
        Plain text extracted from the file.

    Raises
    ------
    ValueError
        If the file extension is not supported.
    """
    ext = path.suffix.lower()
    converters = {
        ".md": _convert_markdown,
        ".txt": _convert_text,
        ".epub": _convert_epub,
        ".docx": _convert_docx,
        ".html": _convert_html,
        ".htm": _convert_html,
        ".pdf": _convert_pdf,
    }
    converter = converters.get(ext)
    if not converter:
        valid = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Format '{ext}' not supported. Valid formats: {valid}")
    return converter(path)


# ─── Plain text ──────────────────────────────────────────────────────────────


def _convert_text(path: Path) -> str:
    """Read a plain-text file. No conversion required."""
    return path.read_text(encoding="utf-8").strip()


# ─── Markdown ─────────────────────────────────────────────────────────────────


def _convert_markdown(path: Path) -> str:
    """Convert Markdown to plain text via pandoc or regex fallback.

    Uses pandoc if available in PATH, otherwise a regex fallback
    that strips the most common Markdown syntax.
    """
    if shutil.which("pandoc"):
        result = subprocess.run(
            ["pandoc", str(path), "-t", "plain", "--wrap=none"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
        log.warning("pandoc returned an error, using the regex fallback.")

    text = path.read_text(encoding="utf-8")
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`{1,3}.*?`{1,3}", "", text, flags=re.DOTALL)
    text = re.sub(r"!\[.*?\]\(.+?\)", "", text)  # images (BEFORE links)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)  # links → text only
    text = re.sub(r"[-*_]{3,}", "", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\|.*\|$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─── EPUB ─────────────────────────────────────────────────────────────────────


def _convert_epub(path: Path) -> str:
    """Extract text from an EPUB, chapter by chapter."""
    import warnings

    import ebooklib  # type: ignore[import-untyped]
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    from ebooklib import epub

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    texts = []

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "lxml")
        for tag in soup(["script", "style", "nav"]):
            tag.decompose()
        text = soup.get_text(separator="\n\n").strip()
        if text:
            texts.append(text)

    result = "\n\n".join(texts)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ─── DOCX ─────────────────────────────────────────────────────────────────────


def _convert_docx(path: Path) -> str:
    """Extract text from a Word file (.docx) paragraph by paragraph."""
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


# ─── HTML ─────────────────────────────────────────────────────────────────────


def _convert_html(path: Path) -> str:
    """Extract text from an HTML page, removing navigation and scripts."""
    from bs4 import BeautifulSoup

    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find("body") or soup
    text = main.get_text(separator="\n\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─── PDF ──────────────────────────────────────────────────────────────────────


def _convert_pdf(path: Path) -> str:
    """Extract text from a PDF page by page.

    Removes isolated page numbers and normalizes spacing.
    Does not handle image-based PDFs (requires OCR).
    """
    import pymupdf

    doc = pymupdf.open(str(path))
    texts = []

    for i in range(doc.page_count):
        text = doc[i].get_text("text").strip()
        if text:
            texts.append(text)
    doc.close()

    result = "\n\n".join(texts)
    # Remove isolated page numbers (lines with only 1-4 digits)
    result = re.sub(r"^\s*\d{1,4}\s*$", "", result, flags=re.MULTILINE)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
