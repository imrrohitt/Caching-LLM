"""Test suite for semantic prompt cache (10 cases)."""

from __future__ import annotations

import time

import numpy as np
import pytest

from semantic_cache import MockEmbeddingProvider, SemanticCache
from semantic_cache.embeddings import cosine_similarity


@pytest.fixture
def embedder() -> MockEmbeddingProvider:
    return MockEmbeddingProvider()


@pytest.fixture
def cache(embedder: MockEmbeddingProvider) -> SemanticCache:
    return SemanticCache(embedder, ttl_seconds=3600.0, default_threshold=0.85)


# 1. Exact match hit
def test_exact_match_hit(cache: SemanticCache) -> None:
    cache.cache_set("billing What is our monthly LLM spend?", "₹1.8L")
    result = cache.cache_get("billing What is our monthly LLM spend?")
    assert result == "₹1.8L"
    stats = cache.cache_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 0


# 2. Semantically similar hit (different wording, same meaning)
def test_semantically_similar_hit(cache: SemanticCache) -> None:
    cache.cache_set(
        "billing How much do we spend on LLM APIs per month?",
        "₹1.8L per month",
    )
    result = cache.cache_get(
        "billing What's our monthly LLM API cost?",
        threshold=0.85,
    )
    assert result == "₹1.8L per month"


# 3. Semantically different miss
def test_semantically_different_miss(cache: SemanticCache) -> None:
    cache.cache_set("billing What is our monthly LLM spend?", "₹1.8L")
    result = cache.cache_get("deploy How do I roll back production?")
    assert result is None
    assert cache.cache_stats()["misses"] == 1


# 4. TTL expiry
def test_ttl_expiry(embedder: MockEmbeddingProvider) -> None:
    short_ttl_cache = SemanticCache(embedder, ttl_seconds=0.05, default_threshold=0.85)
    short_ttl_cache.cache_set("billing monthly spend", "₹1.8L")
    assert short_ttl_cache.cache_get("billing monthly spend") == "₹1.8L"
    time.sleep(0.08)
    assert short_ttl_cache.cache_get("billing monthly spend") is None


# 5. Empty cache behaviour
def test_empty_cache_returns_none(cache: SemanticCache) -> None:
    assert cache.cache_get("anything") is None
    stats = cache.cache_stats()
    assert stats["total_queries"] == 1
    assert stats["hit_rate"] == 0.0
    assert stats["miss_rate"] == 1.0


# 6. cache_stats reflects hit rate after multiple hits
def test_cache_stats_hit_rate(cache: SemanticCache) -> None:
    cache.cache_set("billing monthly LLM cost", "₹1.8L")
    cache.cache_get("billing monthly LLM cost")
    cache.cache_get("billing What's our LLM spend?")
    cache.cache_get("deploy rollback steps")
    stats = cache.cache_stats()
    assert stats["total_queries"] == 3
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hit_rate"] == pytest.approx(2 / 3, rel=1e-3)
    assert stats["miss_rate"] == pytest.approx(1 / 3, rel=1e-3)


# 7. Configurable threshold: strict value misses, loose value hits paraphrase
def test_threshold_controls_match(cache: SemanticCache) -> None:
    cache.cache_set("billing monthly LLM spend", "₹1.8L")
    paraphrase = "billing paraphrased monthly spend question"
    assert cache.cache_get(paraphrase, threshold=0.85) == "₹1.8L"
    assert cache.cache_get(paraphrase, threshold=1.0) is None


# 8. Best match wins when multiple entries exist
def test_best_match_among_multiple_entries(cache: SemanticCache) -> None:
    cache.cache_set("billing monthly spend", "answer-billing")
    cache.cache_set("deploy rollback production", "answer-deploy")
    result = cache.cache_get("billing What did we spend this month?")
    assert result == "answer-billing"


# 9. cache_set stores multiple entries; clear resets state
def test_clear_resets_entries_and_stats(cache: SemanticCache) -> None:
    cache.cache_set("billing spend", "₹1.8L")
    cache.cache_get("billing spend")
    cache.clear()
    assert cache.cache_get("billing spend") is None
    stats = cache.cache_stats()
    assert stats["entries"] == 0
    assert stats["total_queries"] == 1


# 10. cosine_similarity for normalized vectors
def test_cosine_similarity_normalized_vectors() -> None:
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(1.0)
    assert cosine_similarity(a, c) == pytest.approx(0.0)
