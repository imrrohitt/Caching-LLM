"""
Integration tests with real sentence-transformers embeddings.

Validates true semantic similarity (not mock topic-token matching).
Skip with: pytest -v -m "not integration"
"""

from __future__ import annotations

import time

import pytest

from semantic_cache import SemanticCache, SentenceTransformerProvider

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def real_cache() -> SemanticCache:
    try:
        embedder = SentenceTransformerProvider()
    except ImportError as exc:
        pytest.skip(f"sentence-transformers not installed: {exc}")
    return SemanticCache(embedder, default_threshold=0.92, ttl_seconds=3600.0)


def test_real_semantic_paraphrase_hit(real_cache: SemanticCache) -> None:
    """Different wording, same meaning — must hit at default threshold 0.92."""
    real_cache.clear()
    real_cache.cache_set("What is our monthly LLM API spend?", "₹1.8L")
    result = real_cache.cache_get(
        "How much do we spend on large language models each month?"
    )
    assert result == "₹1.8L"


def test_real_semantic_unrelated_miss(real_cache: SemanticCache) -> None:
    real_cache.clear()
    real_cache.cache_set("What is our monthly LLM API spend?", "₹1.8L")
    result = real_cache.cache_get("How do I roll back a Kubernetes deployment?")
    assert result is None


def test_real_cache_lookup_under_10ms(real_cache: SemanticCache) -> None:
    real_cache.clear()
    real_cache.cache_set("What is the capital of France?", "Paris")
    # Warm embedding model
    real_cache.cache_get("What is the capital of France?")

    start = time.perf_counter()
    result = real_cache.cache_get("Which city is the capital of France?")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert result == "Paris"
    assert elapsed_ms < 10.0, f"cache lookup took {elapsed_ms:.2f}ms"
