"""
FastAPI demo: semantic cache wrapped around an LLM call.

Run:
    uvicorn demo.app:app --reload

Environment (optional):
    OPENAI_API_KEY — use real OpenAI chat; otherwise a local mock LLM is used.
    SEMANTIC_CACHE_THRESHOLD — default 0.92
    SEMANTIC_CACHE_TTL — default 3600 (seconds)
"""

from __future__ import annotations

import os
import time
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from semantic_cache import MockEmbeddingProvider, SemanticCache, SentenceTransformerProvider

load_dotenv()

app = FastAPI(title="PropOS Semantic Prompt Cache Demo")

_cache: SemanticCache | None = None


def _build_embedder():
    if os.getenv("SEMANTIC_CACHE_EMBEDDER", "").lower() == "mock":
        return MockEmbeddingProvider()
    return SentenceTransformerProvider(
        model_name=os.getenv("SEMANTIC_CACHE_MODEL", "all-MiniLM-L6-v2")
    )


def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache(
            _build_embedder(),
            default_threshold=float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.92")),
            ttl_seconds=float(os.getenv("SEMANTIC_CACHE_TTL", "3600")),
        )
    return _cache


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, examples=["What is the capital of France?"])
    threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Cosine similarity threshold for cache lookup",
    )


class ChatResponse(BaseModel):
    prompt: str
    response: str
    source: Literal["cache", "llm"]
    latency_ms: float
    cache_stats: dict


def _mock_llm(prompt: str) -> str:
    """Deterministic stand-in when OPENAI_API_KEY is not set."""
    return f"[mock-llm] Answer for: {prompt.strip()}"


def _openai_llm(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    completion = client.chat.completions.create(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
    )
    return completion.choices[0].message.content or ""


def _call_llm(prompt: str) -> str:
    if os.getenv("OPENAI_API_KEY"):
        return _openai_llm(prompt)
    return _mock_llm(prompt)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/cache/stats")
def cache_stats() -> dict:
    return get_cache().cache_stats()


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    started = time.perf_counter()

    cache = get_cache()
    cached = cache.cache_get(request.prompt, threshold=request.threshold)
    if cached is not None:
        latency_ms = (time.perf_counter() - started) * 1000
        return ChatResponse(
            prompt=request.prompt,
            response=cached,
            source="cache",
            latency_ms=round(latency_ms, 3),
            cache_stats=cache.cache_stats(),
        )

    llm_response = _call_llm(request.prompt)
    cache.cache_set(request.prompt, llm_response)

    latency_ms = (time.perf_counter() - started) * 1000
    return ChatResponse(
        prompt=request.prompt,
        response=llm_response,
        source="llm",
        latency_ms=round(latency_ms, 3),
        cache_stats=cache.cache_stats(),
    )
