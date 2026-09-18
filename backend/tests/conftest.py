"""Shared fixtures. Tests run offline: no network, no LLM spend."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

SAMPLES_DIR = BACKEND_DIR.parent / "samples"


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return SAMPLES_DIR


@pytest.fixture(scope="session")
def sample_txt(samples_dir: Path) -> bytes:
    return (samples_dir / "ECommerce_SRS_Hackathon_Sample.txt").read_bytes()


@pytest.fixture(scope="session")
def sample_docx(samples_dir: Path) -> bytes:
    return (samples_dir / "ECommerce_SRS_Hackathon_Sample.docx").read_bytes()


@pytest.fixture(scope="session")
def sample_pdf(samples_dir: Path) -> bytes:
    return (samples_dir / "ECommerce_SRS_Hackathon_Sample.pdf").read_bytes()


class FakeLLM:
    """Stands in for a provider. Returns canned JSON per stage marker."""

    model = "fake-model"

    def __init__(self, responses: dict[str, object] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    async def complete(self, system: str, user: str, *, temperature: float) -> str:
        self.calls.append((system, user))
        for marker, payload in self.responses.items():
            if marker in system:
                if isinstance(payload, str):
                    return payload
                return json.dumps(payload)
        return "{}"

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_llm() -> type[FakeLLM]:
    return FakeLLM


class Rec:
    """Minimal requirement stand-in for resolver tests."""

    def __init__(self, code: str, text: str, normalized: str | None = None) -> None:
        self.code = code
        self.original_text = text
        self.normalized_text = normalized or text.lower()


@pytest.fixture
def rec() -> type[Rec]:
    return Rec
