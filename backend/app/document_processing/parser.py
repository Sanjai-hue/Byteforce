"""Parse PDF, DOCX and TXT into page-aware text blocks.

Page and section information is captured here because it is what makes every
later finding traceable back to a place in the source document.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass

from app.core.errors import DocumentParseError, EmptyDocumentError, UnsupportedFileType

logger = logging.getLogger("reqguard.parser")

# "3.2 Account Management", "4. Security", "Section 5 - Performance"
_HEADING = re.compile(
    r"^\s*(?:section\s+)?(\d+(?:\.\d+)*)[.)]?\s+([A-Z][^\n]{2,80})$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class TextBlock:
    """A contiguous run of text with the page and section it came from."""

    text: str
    page_number: int | None
    section: str | None


@dataclass(slots=True)
class ParsedDocument:
    blocks: list[TextBlock]
    page_count: int

    @property
    def full_text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    @property
    def char_count(self) -> int:
        return sum(len(block.text) for block in self.blocks)


def parse_document(data: bytes, file_type: str, filename: str) -> ParsedDocument:
    file_type = file_type.lower().lstrip(".")
    if file_type == "pdf":
        parsed = _parse_pdf(data, filename)
    elif file_type == "docx":
        parsed = _parse_docx(data, filename)
    elif file_type == "txt":
        parsed = _parse_txt(data, filename)
    else:
        raise UnsupportedFileType(f"'{file_type}' files are not supported. Upload a PDF, DOCX or TXT.")

    if not parsed.blocks or parsed.char_count < 40:
        raise EmptyDocumentError(
            "No readable text was found in this document. If it is a scanned PDF it needs OCR first."
        )
    return parsed


def _current_section(line: str, fallback: str | None) -> str | None:
    match = _HEADING.match(line.strip())
    if match:
        return f"{match.group(1)} {match.group(2).strip()}"
    return fallback


def _blocks_from_lines(lines: list[str], page_number: int | None, section: str | None) -> tuple[list[TextBlock], str | None]:
    """Group lines into paragraph blocks, tracking the active section heading."""
    blocks: list[TextBlock] = []
    buffer: list[str] = []
    active = section

    def flush() -> None:
        if buffer:
            text = " ".join(part.strip() for part in buffer if part.strip()).strip()
            if text:
                blocks.append(TextBlock(text=text, page_number=page_number, section=active))
            buffer.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            flush()
            continue
        heading = _current_section(line, None)
        if heading:
            flush()
            active = heading
            blocks.append(TextBlock(text=line.strip(), page_number=page_number, section=active))
            continue
        buffer.append(line)

    flush()
    return blocks, active


def _parse_pdf(data: bytes, filename: str) -> ParsedDocument:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # malformed / encrypted container
        logger.warning("pdf open failed for %s: %s", filename, exc)
        raise DocumentParseError(
            "This PDF could not be opened. It may be corrupted or password protected."
        ) from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise DocumentParseError("This PDF is password protected. Remove the password and retry.") from exc

    blocks: list[TextBlock] = []
    section: str | None = None
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("pdf page %s of %s failed: %s", index, filename, exc)
            continue
        if not text.strip():
            continue
        page_blocks, section = _blocks_from_lines(text.splitlines(), index, section)
        blocks.extend(page_blocks)

    if not blocks:
        raise EmptyDocumentError(
            "No selectable text was found in this PDF. Scanned documents need OCR before upload."
        )
    return ParsedDocument(blocks=blocks, page_count=len(reader.pages))


def _parse_docx(data: bytes, filename: str) -> ParsedDocument:
    try:
        import docx

        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        logger.warning("docx open failed for %s: %s", filename, exc)
        raise DocumentParseError(
            "This DOCX could not be opened. It may be corrupted, or saved in the older .doc format."
        ) from exc

    lines: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        style = (paragraph.style.name or "").lower() if paragraph.style else ""
        if not text:
            lines.append("")
            continue
        # Word headings become section markers even without a numeric prefix.
        if style.startswith("heading") and not _HEADING.match(text):
            lines.append("")
            lines.append(f"0 {text}" if not text[0].isdigit() else text)
        else:
            lines.append(text)

    # Tables frequently hold requirement rows in real SRS documents.
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                lines.append(" | ".join(cells))

    blocks, _ = _blocks_from_lines(lines, None, None)
    if not blocks:
        raise EmptyDocumentError("This DOCX contains no readable text.")
    return ParsedDocument(blocks=blocks, page_count=0)


def _parse_txt(data: bytes, filename: str) -> ParsedDocument:
    text = ""
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if not text:
        raise DocumentParseError("This text file could not be decoded. Save it as UTF-8 and retry.")

    blocks, _ = _blocks_from_lines(text.splitlines(), None, None)
    if not blocks:
        raise EmptyDocumentError("This text file is empty.")
    return ParsedDocument(blocks=blocks, page_count=0)


def chunk_blocks(blocks: list[TextBlock], max_chars: int) -> list[tuple[str, str, int | None]]:
    """Group blocks into extraction chunks.

    Returns (chunk_text, section_hint, first_page). Blocks are kept whole so a
    requirement is never split across two chunks.
    """
    chunks: list[tuple[str, str, int | None]] = []
    buffer: list[str] = []
    size = 0
    section_hint: str | None = None
    first_page: int | None = None

    def flush() -> None:
        nonlocal buffer, size, section_hint, first_page
        if buffer:
            chunks.append(("\n".join(buffer), section_hint or "unknown", first_page))
        buffer = []
        size = 0
        section_hint = None
        first_page = None

    for block in blocks:
        block_len = len(block.text) + 1
        if size + block_len > max_chars and buffer:
            flush()
        if section_hint is None:
            section_hint = block.section
        if first_page is None:
            first_page = block.page_number
        buffer.append(block.text)
        size += block_len

    flush()
    return chunks
