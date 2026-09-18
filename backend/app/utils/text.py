"""Text normalisation used before embedding and duplicate comparison.

Normalisation only ever feeds the analysis. `original_text` is stored verbatim
and is never replaced by a normalised form.
"""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")
# Leading requirement labels: "R001:", "FR-12 -", "3.2.1)", "[REQ-7]"
_LEADING_LABEL = re.compile(
    r"^\s*(?:\[)?(?:[A-Z]{1,5}[-_ ]?\d{1,4}(?:\.\d+)*|\d+(?:\.\d+)+)(?:\])?\s*[:.\-–)]\s*",
)
_BULLET = re.compile(r"^\s*[-*•●▪]\s*")

_CONTRACTIONS = {
    "shall not": "must not",
    "should not": "must not",
    "will not": "must not",
    "cannot": "must not",
    "can not": "must not",
}


def strip_requirement_label(text: str) -> str:
    """Remove a leading printed label so it does not skew similarity."""
    cleaned = _BULLET.sub("", text.strip())
    return _LEADING_LABEL.sub("", cleaned).strip()


def normalize_requirement(text: str) -> str:
    """Produce the comparison form of a requirement.

    Lowercased, label-free, whitespace-collapsed, with modal verbs unified so
    "shall"/"should"/"must" do not read as different meanings to the embedder.
    """
    cleaned = strip_requirement_label(text)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip().lower()

    for phrase, replacement in _CONTRACTIONS.items():
        cleaned = cleaned.replace(phrase, replacement)

    cleaned = re.sub(r"\b(shall|should|will|must)\b", "must", cleaned)
    cleaned = re.sub(r"\bthe system\b|\bthe application\b|\bthe platform\b", "the system", cleaned)
    cleaned = cleaned.rstrip(" .;")
    return cleaned or text.strip().lower()


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def looks_like_requirement(text: str) -> bool:
    """Cheap guard against headings and boilerplate surviving extraction."""
    stripped = strip_requirement_label(text).strip()
    if len(stripped) < 15:
        return False
    if len(stripped.split()) < 4:
        return False
    # A heading rarely ends in a verb phrase and rarely has a modal.
    return True
