"""Embedding providers for semantic similarity."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> np.ndarray:
        """Return a normalized embedding vector for the given text."""

    @abstractmethod
    def embed_batch(self, texts: Sequence[str]) -> np.ndarray:
        """Return normalized embedding vectors for multiple texts."""


class SentenceTransformerProvider(EmbeddingProvider):
    """Production embedder using sentence-transformers (runs locally, no API key)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> np.ndarray:
        vector = self._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(vector, dtype=np.float32)

    def embed_batch(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(
            list(texts), convert_to_numpy=True, normalize_embeddings=True
        )
        return np.asarray(vectors, dtype=np.float32)


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic embedder for fast unit tests.

    Texts that share the same 'topic token' (first word after normalization)
    receive nearly-identical vectors; unrelated texts are orthogonal-ish.
    """

    _DIM = 32

    def embed(self, text: str) -> np.ndarray:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> np.ndarray:
        vectors = []
        for text in texts:
            topic = _topic_key(text)
            seed = int(hashlib.sha256(topic.encode()).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            base = rng.standard_normal(self._DIM).astype(np.float32)
            # Small noise so exact strings still score ~1.0 but aren't identical arrays.
            noise = np.random.default_rng(hash(text) % (2**32)).standard_normal(self._DIM) * 0.02
            vec = base + noise.astype(np.float32)
            vectors.append(_normalize(vec))
        return np.stack(vectors, axis=0)


def _topic_key(text: str) -> str:
    normalized = " ".join(text.lower().split())
    if not normalized:
        return "__empty__"
    return normalized.split()[0]


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm < 1e-12:
        return vector
    return (vector / norm).astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for L2-normalized vectors (dot product)."""
    return float(np.dot(a, b))
