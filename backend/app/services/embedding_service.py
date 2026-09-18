"""EmbeddingService — BAAI/bge-small-en-v1.5 via sentence-transformers.

The model is loaded once at application startup, never per request. Candidate
pair selection happens here: embeddings narrow the field so the LLM only sees
pairs worth reasoning about, instead of all N*(N-1)/2 combinations.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from app.core.config import Settings, get_settings
from app.core.errors import EmbeddingModelError

logger = logging.getLogger("reqguard.embeddings")


@dataclass(slots=True)
class CandidatePair:
    index_a: int
    index_b: int
    similarity: float


class EmbeddingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model = None
        self._lock = threading.Lock()
        self._load_error: str | None = None

    # -- lifecycle ----------------------------------------------------------
    def load(self) -> None:
        """Load the model. Called once on startup; safe to call again."""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("loading embedding model %s", self._settings.embedding_model_name)
                self._model = SentenceTransformer(self._settings.embedding_model_name)
                # Renamed in sentence-transformers 6.x; keep the old name as a fallback.
                get_dim = getattr(
                    self._model,
                    "get_embedding_dimension",
                    getattr(self._model, "get_sentence_embedding_dimension", None),
                )
                if get_dim is None:
                    raise EmbeddingModelError("Could not determine the embedding dimension.")
                dim = int(get_dim())
                if dim != self._settings.embedding_dimensions:
                    raise EmbeddingModelError(
                        f"Embedding model returned {dim} dimensions but the database column "
                        f"expects {self._settings.embedding_dimensions}."
                    )
                logger.info("embedding model ready (%s dimensions)", dim)
            except EmbeddingModelError:
                raise
            except Exception as exc:
                self._load_error = str(exc)
                logger.exception("embedding model failed to load")
                raise EmbeddingModelError(
                    "The embedding model could not be loaded. Analysis is unavailable until it is.",
                    detail=str(exc),
                ) from exc

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def _require_model(self):
        if self._model is None:
            raise EmbeddingModelError(
                "The embedding model is not loaded.", detail=self._load_error
            )
        return self._model

    # -- embedding ----------------------------------------------------------
    def embed_text(self, text: str) -> list[float]:
        return self.embed_requirements([text])[0]

    def embed_requirements(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts, L2-normalised so a dot product is cosine similarity."""
        model = self._require_model()
        if not texts:
            return []
        try:
            vectors = model.encode(
                list(texts),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
                batch_size=32,
            )
        except Exception as exc:
            logger.exception("embedding generation failed")
            raise EmbeddingModelError(
                "Embedding generation failed.", detail=str(exc)
            ) from exc
        return [vector.astype(float).tolist() for vector in vectors]

    # -- similarity ---------------------------------------------------------
    @staticmethod
    def calculate_similarity(a: Sequence[float], b: Sequence[float]) -> float:
        """Cosine similarity between two vectors."""
        from sklearn.metrics.pairwise import cosine_similarity

        va = np.asarray(a, dtype=np.float32).reshape(1, -1)
        vb = np.asarray(b, dtype=np.float32).reshape(1, -1)
        return float(cosine_similarity(va, vb)[0][0])

    @staticmethod
    def similarity_matrix(vectors: Sequence[Sequence[float]]) -> np.ndarray:
        from sklearn.metrics.pairwise import cosine_similarity

        if not vectors:
            return np.zeros((0, 0), dtype=np.float32)
        matrix = np.asarray(vectors, dtype=np.float32)
        return cosine_similarity(matrix)

    @classmethod
    def candidate_pairs(
        cls,
        vectors: Sequence[Sequence[float]],
        *,
        threshold: float,
        max_pairs: int,
        upper: float = 1.01,
    ) -> list[CandidatePair]:
        """Pairs whose similarity falls in [threshold, upper), strongest first.

        This is the step that keeps LLM usage sub-quadratic: 100 requirements
        have 4,950 possible pairs, but only those above the threshold are sent
        to the model.
        """
        count = len(vectors)
        if count < 2:
            return []

        matrix = cls.similarity_matrix(vectors)
        pairs: list[CandidatePair] = []
        for i in range(count):
            for j in range(i + 1, count):
                score = float(matrix[i][j])
                if threshold <= score < upper:
                    pairs.append(CandidatePair(index_a=i, index_b=j, similarity=score))

        pairs.sort(key=lambda pair: pair.similarity, reverse=True)
        return pairs[:max_pairs]


_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
