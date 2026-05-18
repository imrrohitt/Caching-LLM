"""API tests for FastAPI demo (uses mock LLM, no OpenAI key)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Fast tests: mock embedder + mock LLM (no torch / OpenAI download)
os.environ["SEMANTIC_CACHE_EMBEDDER"] = "mock"
os.environ.pop("OPENAI_API_KEY", None)


@pytest.fixture(scope="module")
def client() -> TestClient:
    from demo.app import app, get_cache

    get_cache().clear()
    return TestClient(app)


def test_chat_cache_miss_then_hit(client: TestClient) -> None:
    miss = client.post(
        "/chat",
        json={"prompt": "billing integration test What is our monthly LLM spend?"},
    )
    assert miss.status_code == 200
    miss_body = miss.json()
    assert miss_body["source"] == "llm"

    # Paraphrase — same topic prefix, semantically similar for mock/real embedder
    hit = client.post(
        "/chat",
        json={"prompt": "billing integration test How much do we spend on LLMs monthly?"},
    )
    assert hit.status_code == 200
    hit_body = hit.json()
    assert hit_body["source"] == "cache"
    assert hit_body["response"] == miss_body["response"]
    assert hit_body["latency_ms"] < 10.0


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
