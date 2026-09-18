"""Resolve a model's requirement reference back to a real requirement.

Prompts ask for the requirement code ("R001"), but models frequently answer with
the full requirement sentence, a labelled variant ("Requirement R001"), or the
document's own printed label. Dropping those answers silently would lose genuine
findings, so every reference is resolved through this helper: exact code, then an
embedded code pattern, then a text match against the known requirements.
"""

from __future__ import annotations

import re
from typing import Iterable, Protocol

_CODE_PATTERN = re.compile(r"\bR\d{1,4}\b", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


class HasCodeAndText(Protocol):
    code: str
    original_text: str
    normalized_text: str


def _key(text: str) -> str:
    return _WHITESPACE.sub(" ", text or "").strip().lower().rstrip(" .;:")


class RequirementResolver:
    """Maps whatever the model returned onto a known requirement."""

    def __init__(self, records: Iterable[HasCodeAndText]) -> None:
        self._by_code: dict[str, HasCodeAndText] = {}
        self._by_text: dict[str, HasCodeAndText] = {}
        for record in records:
            self._by_code[record.code.upper()] = record
            self._by_text[_key(record.original_text)] = record
            normalized = getattr(record, "normalized_text", "")
            if normalized:
                self._by_text.setdefault(_key(normalized), record)

    def resolve(self, reference: str | None) -> HasCodeAndText | None:
        if not reference:
            return None
        raw = reference.strip()

        # 1. Exact code, the documented contract.
        direct = self._by_code.get(raw.upper())
        if direct is not None:
            return direct

        # 2. A code embedded in a longer string ("Requirement R001", "R001: ...").
        match = _CODE_PATTERN.search(raw)
        if match:
            candidate = self._by_code.get(match.group(0).upper())
            if candidate is not None:
                return candidate

        # 3. The full requirement sentence echoed back instead of the code.
        exact_text = self._by_text.get(_key(raw))
        if exact_text is not None:
            return exact_text

        # 4. A truncated or lightly reworded quote of the requirement.
        probe = _key(raw)
        if len(probe) >= 25:
            for text, record in self._by_text.items():
                if probe in text or text in probe:
                    return record
        return None
