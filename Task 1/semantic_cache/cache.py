"""Semantic prompt cache with embedding similarity and TTL expiry."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from semantic_cache.embeddings import EmbeddingProvider, cosine_similarity


@dataclass
class _CacheEntry:
    prompt: str
    response: str
    embedding: np.ndarray
    created_at: float


class SemanticCache:
    """
    In-memory semantic cache keyed by embedding similarity (not exact strings).

    Default similarity threshold: 0.92
        With all-MiniLM-L6-v2, paraphrases of the same intent typically score
        0.88–0.98 while unrelated prompts stay below ~0.75. 0.92 is a conservative
        default: high enough to avoid serving wrong answers on loosely related
        queries, low enough to catch common rephrasings in production agent traffic.

    Default TTL: 3600 seconds (1 hour)
        LLM answers for operational prompts (status, configs, runbooks) stay valid
        long enough to amortize repeated agent calls within a session, but should
        not live indefinitely—upstream data and policies change. One hour balances
        hit rate vs freshness for PropOS-style agent workloads without unbounded
        staleness.
    """

    DEFAULT_THRESHOLD = 0.92
    DEFAULT_TTL_SECONDS = 3600.0

    def __init__(
        self,
        embedder: EmbeddingProvider,
        *,
        default_threshold: float = DEFAULT_THRESHOLD,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._embedder = embedder
        self._default_threshold = default_threshold
        self._ttl_seconds = ttl_seconds
        self._entries: list[_CacheEntry] = []

        self._hits = 0
        self._misses = 0
        self._total_queries = 0

    def cache_set(self, prompt: str, response: str) -> None:
        """Store a prompt–response pair with its embedding and creation time."""
        embedding = self._embedder.embed(prompt)
        self._entries.append(
            _CacheEntry(
                prompt=prompt,
                response=response,
                embedding=embedding,
                created_at=time.monotonic(),
            )
        )

    def cache_get(
        self,
        prompt: str,
        threshold: float | None = None,
    ) -> str | None:
        """
        Return the cached response for the best semantically similar prompt, or None.

        Args:
            prompt: Incoming user/agent prompt.
            threshold: Minimum cosine similarity (0–1). Uses instance default when omitted.
        """
        similarity_threshold = (
            self._default_threshold if threshold is None else threshold
        )
        self._total_queries += 1
        self._purge_expired()

        if not self._entries:
            self._misses += 1
            return None

        query_embedding = self._embedder.embed(prompt)
        best_similarity = -1.0
        best_entry: _CacheEntry | None = None

        for entry in self._entries:
            similarity = cosine_similarity(query_embedding, entry.embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_entry = entry

        if best_entry is not None and best_similarity >= similarity_threshold:
            self._hits += 1
            return best_entry.response

        self._misses += 1
        return None

    def cache_stats(self) -> dict[str, Any]:
        """Return hit rate, miss rate, and query counts."""
        if self._total_queries == 0:
            return {
                "hit_rate": 0.0,
                "miss_rate": 0.0,
                "hits": self._hits,
                "misses": self._misses,
                "total_queries": 0,
                "entries": len(self._entries),
            }

        hit_rate = self._hits / self._total_queries
        miss_rate = self._misses / self._total_queries
        return {
            "hit_rate": round(hit_rate, 4),
            "miss_rate": round(miss_rate, 4),
            "hits": self._hits,
            "misses": self._misses,
            "total_queries": self._total_queries,
            "entries": len(self._entries),
        }

    def clear(self) -> None:
        """Remove all entries and reset statistics."""
        self._entries.clear()
        self._hits = 0
        self._misses = 0
        self._total_queries = 0

    def _purge_expired(self) -> None:
        if self._ttl_seconds <= 0:
            return
        now = time.monotonic()
        self._entries = [
            entry
            for entry in self._entries
            if (now - entry.created_at) < self._ttl_seconds
        ]
