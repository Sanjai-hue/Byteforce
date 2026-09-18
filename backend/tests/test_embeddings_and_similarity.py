"""Embedding generation, similarity, candidate-pair selection and normalisation."""

from __future__ import annotations

import pytest

from app.services.embedding_service import EmbeddingService
from app.utils.text import looks_like_requirement, normalize_requirement, strip_requirement_label


@pytest.fixture(scope="module")
def service() -> EmbeddingService:
    svc = EmbeddingService()
    svc.load()
    return svc


# --- normalisation ---------------------------------------------------------
def test_strips_requirement_labels() -> None:
    assert strip_requirement_label("R001: The system shall log in.") == "The system shall log in."
    assert strip_requirement_label("FR-12 - The system shall log in.") == "The system shall log in."
    assert strip_requirement_label("3.2.1) The system shall log in.") == "The system shall log in."


def test_normalisation_unifies_modal_verbs() -> None:
    a = normalize_requirement("The system shall allow login.")
    b = normalize_requirement("The system must allow login.")
    assert a == b


def test_normalisation_never_returns_empty() -> None:
    assert normalize_requirement("R001:") != ""


def test_looks_like_requirement_filters_headings() -> None:
    assert not looks_like_requirement("4. Security")
    assert looks_like_requirement("The system shall encrypt all stored customer passwords.")


# --- embeddings ------------------------------------------------------------
def test_model_reports_expected_dimensions(service: EmbeddingService) -> None:
    vector = service.embed_text("The system shall allow users to log in.")
    assert len(vector) == 384


def test_embeddings_are_normalised(service: EmbeddingService) -> None:
    vector = service.embed_text("The system shall allow users to log in.")
    magnitude = sum(value * value for value in vector) ** 0.5
    assert magnitude == pytest.approx(1.0, abs=1e-3)


def test_batch_embedding_matches_count(service: EmbeddingService) -> None:
    vectors = service.embed_requirements(["one requirement", "another requirement", "a third"])
    assert len(vectors) == 3


def test_empty_input_returns_empty(service: EmbeddingService) -> None:
    assert service.embed_requirements([]) == []


# --- similarity ------------------------------------------------------------
def test_identical_text_is_maximally_similar(service: EmbeddingService) -> None:
    text = "The system shall allow users to reset their password."
    a, b = service.embed_requirements([text, text])
    assert service.calculate_similarity(a, b) == pytest.approx(1.0, abs=1e-3)


def test_paraphrase_scores_above_unrelated(service: EmbeddingService) -> None:
    vectors = service.embed_requirements(
        [
            "the system must allow new users to create an account",
            "the system must allow customers to register for an account",
            "the platform must generate a daily sales summary report",
        ]
    )
    paraphrase = service.calculate_similarity(vectors[0], vectors[1])
    unrelated = service.calculate_similarity(vectors[0], vectors[2])
    assert paraphrase > unrelated
    assert paraphrase > 0.8


# --- candidate pairs -------------------------------------------------------
def test_candidate_pairs_respect_threshold(service: EmbeddingService) -> None:
    vectors = service.embed_requirements(
        [
            "the system must allow new users to create an account",
            "the system must allow customers to register for an account",
            "the platform must generate a daily sales summary report",
        ]
    )
    pairs = service.candidate_pairs(vectors, threshold=0.8, max_pairs=10)
    assert {0, 1} == {pairs[0].index_a, pairs[0].index_b}
    assert all(pair.similarity >= 0.8 for pair in pairs)


def test_candidate_pairs_are_capped_and_sorted(service: EmbeddingService) -> None:
    vectors = service.embed_requirements([f"the system must support feature number {i}" for i in range(12)])
    pairs = service.candidate_pairs(vectors, threshold=0.0, max_pairs=5)
    assert len(pairs) == 5
    scores = [pair.similarity for pair in pairs]
    assert scores == sorted(scores, reverse=True)


def test_candidate_pairs_needs_two_items(service: EmbeddingService) -> None:
    assert service.candidate_pairs([[0.1] * 384], threshold=0.5, max_pairs=10) == []


def test_pair_selection_is_subquadratic(service: EmbeddingService) -> None:
    """The whole point of stage 1: far fewer pairs than N*(N-1)/2 reach the LLM."""
    texts = [f"the system must handle scenario {i} in the ordering workflow" for i in range(20)]
    texts += [f"the platform must render report type {i} for administrators" for i in range(20)]
    vectors = service.embed_requirements(texts)
    total_possible = len(texts) * (len(texts) - 1) // 2
    selected = service.candidate_pairs(vectors, threshold=0.9, max_pairs=10_000)
    assert len(selected) < total_possible
