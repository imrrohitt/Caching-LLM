#!/usr/bin/env python3
"""
End-to-end verification: semantic cache + FastAPI demo timing.

Usage:
    source .venv/bin/activate
    python scripts/verify_e2e_flow.py
"""

from __future__ import annotations

import os
import sys
import time

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient


def main() -> int:
    os.environ["SEMANTIC_CACHE_EMBEDDER"] = os.getenv("SEMANTIC_CACHE_EMBEDDER", "mock")
    os.environ.pop("OPENAI_API_KEY", None)

    from demo.app import app, get_cache
    from semantic_cache import SemanticCache, SentenceTransformerProvider

    print("=== PropOS Semantic Cache E2E Verification ===\n")

    # --- Core cache (library) ---
    embedder_name = os.environ.get("SEMANTIC_CACHE_EMBEDDER", "mock")
    if embedder_name.lower() == "mock":
        from semantic_cache import MockEmbeddingProvider

        embedder = MockEmbeddingProvider()
        print("[1] Core cache: MockEmbeddingProvider (fast)")
    else:
        embedder = SentenceTransformerProvider()
        print("[1] Core cache: SentenceTransformerProvider (real embeddings)")

    cache: SemanticCache = SemanticCache(embedder, default_threshold=0.92, ttl_seconds=3600)
    cache.clear()

    if embedder_name.lower() == "mock":
        cache.cache_set("billing What is our monthly LLM spend?", "₹1.8L per month")
        miss_prompt = "deploy What is our total cloud infrastructure bill?"
        hit_prompt = "billing How much do we spend on LLMs each month?"
    else:
        cache.cache_set("What is our monthly LLM spend?", "₹1.8L per month")
        miss_prompt = "How do I roll back a Kubernetes deployment?"
        hit_prompt = "How much do we spend on large language models each month?"

    t0 = time.perf_counter()
    miss = cache.cache_get(miss_prompt)
    miss_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    hit = cache.cache_get(hit_prompt)
    hit_ms = (time.perf_counter() - t1) * 1000

    print(f"    Unrelated query (miss): {miss_ms:.2f}ms -> {miss!r}")
    print(f"    Paraphrase (hit):       {hit_ms:.2f}ms -> {hit!r}")
    print(f"    Stats: {cache.cache_stats()}")

    if hit is None:
        print("    WARN: paraphrase did not hit (try SEMANTIC_CACHE_EMBEDDER=sentence for real model)")
    elif hit_ms >= 10.0 and embedder_name.lower() != "mock":
        print(f"    WARN: hit latency {hit_ms:.2f}ms >= 10ms target")
    else:
        print("    OK: core cache flow")

    # --- FastAPI demo ---
    print("\n[2] FastAPI /chat endpoint")
    get_cache().clear()
    client = TestClient(app)

    r1 = client.post(
        "/chat",
        json={"prompt": "e2e What is our monthly LLM spend?"},
    )
    r2 = client.post(
        "/chat",
        json={"prompt": "e2e How much do we spend on LLMs monthly?"},
    )

    b1, b2 = r1.json(), r2.json()
    print(f"    First call:  source={b1['source']}, latency={b1['latency_ms']}ms")
    print(f"    Second call: source={b2['source']}, latency={b2['latency_ms']}ms")
    print(f"    Stats: {b2['cache_stats']}")

    ok = (
        r1.status_code == 200
        and r2.status_code == 200
        and b1["source"] == "llm"
        and b2["source"] == "cache"
        and b2["latency_ms"] < 10.0
    )
    if ok:
        print("    OK: API miss -> semantic hit <10ms")
    else:
        print("    FAIL: API flow did not meet expectations")
        return 1

    print("\n=== All checks passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
