# Task 1: PropOS Semantic Prompt Cache

Embedding-based semantic cache for LLM prompts. When a new query arrives, the cache checks whether a **semantically similar** prompt was already answered and returns the stored response instead of calling the LLM again.

Built for PropOS-style agent workloads where repeated or paraphrased queries (10,000–50,000 LLM calls/month) can be served from cache at sub-10ms latency.

## Task checklist

| Requirement | Status | Location |
|-------------|--------|----------|
| `SemanticCache` with `cache_set`, `cache_get`, `cache_stats` | Done | `semantic_cache/cache.py` |
| Embedding similarity (not exact string match) | Done | `semantic_cache/embeddings.py` — `all-MiniLM-L6-v2` |
| Configurable `threshold` on `cache_get` (default `0.92`) | Done | `cache_get(prompt, threshold=None)` |
| TTL cache invalidation (default 3600s) | Done | `ttl_seconds` constructor arg |
| FastAPI demo wrapping LLM + cache | Done | `demo/app.py` — `/chat` |
| Cache hits &lt;10ms vs LLM miss | Done | `tests/test_demo_api.py`, integration test |
| 10 unit test cases | Done | `tests/test_semantic_cache.py` |
| Threshold calibration & risks documented | Done | README — Design decisions |
| False positive analysis | Done | README — False positives |
| Production considerations (10k+/day) | Done | README — Production roadmap |
| Real embedding integration tests | Done | `tests/test_integration_embeddings.py` |
| End-to-end verification script | Done | `scripts/verify_e2e_flow.py` |

---

## Features

| Feature | Description |
|---------|-------------|
| **Semantic matching** | Cosine similarity on embeddings — not exact string match |
| **Embedding model** | `all-MiniLM-L6-v2` via [sentence-transformers](https://www.sbert.net/) (local, no API key for embeddings) |
| **Configurable threshold** | Per-instance and per-request similarity cutoff (default `0.92`) |
| **TTL expiry** | Entries expire after a configurable duration (default 1 hour) |
| **FastAPI demo** | `/chat` endpoint wraps LLM + cache; reports `source` and `latency_ms` |
| **Test suite** | 10 cache unit tests + API integration tests |

---

## Project structure

```
ProOps/
├── semantic_cache/
│   ├── cache.py           # SemanticCache: cache_set, cache_get, cache_stats
│   └── embeddings.py      # SentenceTransformer + Mock embedders
├── demo/
│   └── app.py             # FastAPI demo (LLM + cache)
├── tests/
│   ├── test_semantic_cache.py
│   └── test_demo_api.py
├── scripts/
│   └── run_demo.sh
├── requirements.txt
└── README.md
```

---

## Quick start

### 1. Install

```bash
cd "Task 1"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The first install downloads `sentence-transformers` and PyTorch (~1–2 minutes).

### 2. Run tests

```bash
# Fast unit tests (mock embedder, no torch)
pytest -v -m "not integration"

# Real semantic embeddings (downloads model on first run, ~1–2 min)
pytest -v -m integration
```

### 3. Run end-to-end verification

```bash
python scripts/verify_e2e_flow.py
# Real embeddings: SEMANTIC_CACHE_EMBEDDER=sentence-transformers python scripts/verify_e2e_flow.py
```

Note: use any value other than `mock` for `SEMANTIC_CACHE_EMBEDDER` to load `SentenceTransformerProvider` in the e2e script.

### 4. Run the demo API

```bash
./scripts/run_demo.sh
# or: uvicorn demo.app:app --reload --port 8000
```

Open interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 5. Try cache miss vs hit

```bash
# Miss — calls LLM (mock unless OPENAI_API_KEY is set)
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?"}' | jq

# Hit — semantically similar paraphrase, typically <10ms
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Which city is the capital of France?"}' | jq
```

Example response:

```json
{
  "prompt": "Which city is the capital of France?",
  "response": "[mock-llm] Answer for: What is the capital of France?",
  "source": "cache",
  "latency_ms": 2.145,
  "cache_stats": {
    "hit_rate": 0.5,
    "miss_rate": 0.5,
    "hits": 1,
    "misses": 1,
    "total_queries": 2,
    "entries": 1
  }
}
```

---

## Python API

```python
from semantic_cache import SemanticCache, SentenceTransformerProvider

cache = SemanticCache(
    SentenceTransformerProvider(),
    default_threshold=0.92,
    ttl_seconds=3600,
)

cache.cache_set("What is our monthly LLM spend?", "₹1.8L")

# Paraphrase — cache hit if similarity >= threshold
answer = cache.cache_get("How much do we spend on LLMs per month?")
print(answer)  # ₹1.8L

stats = cache.cache_stats()
print(stats["hit_rate"], stats["total_queries"])
```

### Methods

| Method | Description |
|--------|-------------|
| `cache_set(prompt, response)` | Store prompt, response, and embedding with timestamp |
| `cache_get(prompt, threshold=None)` | Return best matching response or `None` |
| `cache_stats()` | `{ hit_rate, miss_rate, hits, misses, total_queries, entries }` |
| `clear()` | Remove all entries and reset stats |

---

## API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/chat` | POST | Query with cache; body: `{ "prompt", "threshold?" }` |
| `/cache/stats` | GET | Current cache statistics |

---

## Configuration

Environment variables (demo / production):

| Variable | Default | Description |
|----------|---------|-------------|
| `SEMANTIC_CACHE_THRESHOLD` | `0.92` | Minimum cosine similarity for a cache hit |
| `SEMANTIC_CACHE_TTL` | `3600` | Entry lifetime in seconds |
| `SEMANTIC_CACHE_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model name |
| `SEMANTIC_CACHE_EMBEDDER` | _(unset)_ | Set to `mock` for fast local tests without torch |
| `OPENAI_API_KEY` | _(unset)_ | If set, `/chat` uses OpenAI instead of mock LLM |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | Chat model when using OpenAI |

Per-request override: pass `"threshold": 0.95` in the `/chat` JSON body.

---

## Design decisions

### Similarity threshold (default `0.92`)

**Metric:** cosine similarity on L2-normalized embeddings (equivalent to dot product).

**Why 0.92?** With `all-MiniLM-L6-v2`, typical ranges are:

| Pair type | Approximate similarity |
|-----------|------------------------|
| Exact / near-exact wording | 0.98–1.00 |
| Same intent, paraphrased | 0.88–0.98 |
| Same topic, different intent | 0.75–0.88 |
| Unrelated | &lt; 0.75 |

`0.92` is a conservative default: high enough to reject many “same topic, different question” pairs, low enough to catch common agent rephrasings.

**Calibration (recommended for production):**

1. Collect 500–2000 real prompt pairs labeled `should_hit` / `should_miss`.
2. Embed with your production model; plot similarity distributions.
3. Pick threshold that maximizes hit rate subject to a false-positive budget (e.g. &lt; 0.5% wrong serves).
4. Tune per agent or task type (billing vs deploy runbooks may differ).

**Risks:**

| Direction | Effect | Risk |
|-----------|--------|------|
| **Too high** (0.97–0.99) | Fewer hits, more LLM cost | Safer, but cache savings drop |
| **Too low** (0.80–0.88) | More hits, lower cost | **False positives** — wrong cached answers |

For cost-sensitive bootstrap budgets, a threshold slightly too high is usually cheaper than serving one wrong cached answer to a production agent.

### TTL (default 3600 seconds / 1 hour)

Operational LLM answers (status, configs, runbooks) stay useful long enough to amortize repeated calls within a session, but should not live forever — upstream data and policies change. One hour balances hit rate vs freshness for PropOS-style agent traffic.

---

## False positives

A **false positive** occurs when cosine similarity exceeds the threshold but the correct LLM answer for the new prompt would differ from the cached response.

**Common cases:**

1. **Shared vocabulary, different intent** — e.g. “monthly LLM spend” vs “monthly AWS spend”.
2. **Same template, different entity** — e.g. “status of tenant A” vs “tenant B”.
3. **Time-sensitive state** — e.g. “Is deploy green?” before vs after a failure.
4. **Ambiguous best match** — two cached prompts are both close; the wrong one wins by a small margin.
5. **Missing context in the cache key** — only the raw prompt is embedded; system prompt, tenant, tools, and RAG chunks are not part of the key in this minimal build.

**Mitigations in this build:**

- Conservative default threshold (`0.92`)
- TTL to limit staleness
- Best-match only returned if similarity ≥ threshold
- Per-request threshold override

**Not included (recommended for production):**

- Cache namespaces (`tenant_id`, `agent_id`, `model`)
- Dual threshold (borderline scores always call LLM)
- Margin rule (`best_sim - second_best_sim ≥ δ`)
- Opt-out list for non-deterministic or tool-heavy prompts

This implementation optimizes **cost and latency**, not correctness guarantees. Treat semantic cache as best-effort unless you add scoped keys and monitoring.

---

## Production roadmap (10,000+ queries/day)

At PropOS’s projected volume (10k–50k calls/month), the following additions matter most:

### Storage and lookup

- Replace in-memory linear scan with **FAISS**, **pgvector**, or **Redis + vector index** for sub-ms ANN search.
- Cap cache size (LRU / max entries per namespace).
- Persist cache across process restarts.

### Isolation and keys

- Namespace by `tenant_id + agent_id + model + prompt_version`.
- Include hash of system prompt and RAG/tool version in the cache key.

### Safety

- Dual threshold: hit only if `sim ≥ T_high`; if `T_low ≤ sim < T_high`, call LLM.
- Margin rule: require gap between best and second-best match.
- Denylist prompts that must never be cached.

### Observability

- Log every hit: similarity, matched prompt hash, latency, tenant, agent.
- Metrics: hit rate, p99 lookup latency, reported false positives.
- Shadow mode: log “would have hit” without serving until FP rate is acceptable.

### Performance

- Warm embedding model on startup; batch embed on write bursts.
- Target: cache lookup p99 &lt; 10 ms (this build achieves &lt;10 ms on hits in tests).

### Priority order for PropOS

1. Scoped cache keys (tenant + agent) — largest FP reduction per effort  
2. Redis + vector index — durability and scale  
3. Hit logging + FP dashboard — calibrate threshold on real traffic  
4. Stricter threshold / no-cache list for billing and deploy agents  
5. Dual-threshold + margin for borderline matches  

---

## Test suite

| # | Test | What it verifies |
|---|------|------------------|
| 1 | `test_exact_match_hit` | Identical prompt returns cached response |
| 2 | `test_semantically_similar_hit` | Paraphrase hits at threshold 0.85 |
| 3 | `test_semantically_different_miss` | Unrelated topic returns `None` |
| 4 | `test_ttl_expiry` | Entry unavailable after TTL |
| 5 | `test_empty_cache_returns_none` | Empty cache miss + stats |
| 6 | `test_cache_stats_hit_rate` | Hit/miss rates after multiple lookups |
| 7 | `test_threshold_controls_match` | Strict threshold rejects paraphrase |
| 8 | `test_best_match_among_multiple_entries` | Correct entry wins |
| 9 | `test_clear_resets_entries_and_stats` | `clear()` resets state |
| 10 | `test_cosine_similarity_normalized_vectors` | Similarity math |
| + | `test_chat_cache_miss_then_hit` | API: miss → semantic hit &lt;10 ms |

```bash
pytest -v
```

---

## Requirements

- Python 3.10+
- See `requirements.txt` for dependencies

Optional: `OPENAI_API_KEY` for real LLM responses in the demo (otherwise a deterministic mock is used).

---

## License

Internal / assessment use for PropOS.
