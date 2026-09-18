"""Upload validation: type, size, emptiness, and filename sanitisation."""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePath

from app.core.config import Settings
from app.core.errors import FileTooLarge, UnsupportedFileType, ValidationFailure

# Magic bytes, checked so a renamed file cannot smuggle in another format.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
    "docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str) -> str:
    """Strip any path component and reduce the name to safe characters."""
    base = PurePath(filename or "").name or "document"
    normalised = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    cleaned = _SAFE_NAME.sub("_", normalised).strip("._-")
    if not cleaned:
        cleaned = "document"
    return cleaned[:120]


def resolve_file_type(filename: str, settings: Settings) -> str:
    suffix = PurePath(filename or "").suffix.lower().lstrip(".")
    if not suffix:
        raise UnsupportedFileType("The file has no extension. Upload a PDF, DOCX or TXT.")
    if suffix not in settings.allowed_extension_set:
        allowed = ", ".join(sorted(settings.allowed_extension_set)).upper()
        raise UnsupportedFileType(f"'{suffix}' files are not supported. Allowed formats: {allowed}.")
    return suffix


def validate_upload(data: bytes, filename: str, settings: Settings) -> tuple[str, str]:
    """Validate an upload and return (safe_filename, file_type)."""
    if not filename or not filename.strip():
        raise ValidationFailure("No filename was provided with the upload.")

    file_type = resolve_file_type(filename, settings)

    if not data:
        raise ValidationFailure("The uploaded file is empty.")

    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        raise FileTooLarge(f"The file is larger than the {limit_mb:.0f} MB limit.")

    expected = _SIGNATURES.get(file_type)
    if expected and not data.startswith(expected):
        raise ValidationFailure(
            f"The file content does not look like a valid {file_type.upper()} file."
        )

    return sanitize_filename(filename), file_type
