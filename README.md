# Caching-LLM

Tools for reducing LLM cost and latency: semantic prompt caching, WhatsApp conversation state, and RERA compliance knowledge graph design.

| Module | Description |
|--------|-------------|
| [**Task 1**](Task%201/) | Embedding-based semantic prompt cache with FastAPI demo |
| [**Task 2**](Task%202/) | WhatsApp session state for channel-partner onboarding (24-hour window) |
| [**Task 3**](Task%203/) | RERA knowledge graph schema (Neo4j / GraphRAG design) |

## Quick start

### Semantic prompt cache

```bash
cd "Task 1"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v -m "not integration"
./scripts/run_demo.sh
```

Docs: [Task 1/README.md](Task%201/README.md)

### WhatsApp session state

```bash
cd "Task 2"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
./scripts/run_webhook.sh
```

Docs: [Task 2/README.md](Task%202/README.md) · [Architecture](Task%202/docs/ARCHITECTURE.md)

### RERA knowledge graph

Design documentation only (no runtime code):

[Task 3/docs/RERA_KNOWLEDGE_GRAPH_SCHEMA.md](Task%203/docs/RERA_KNOWLEDGE_GRAPH_SCHEMA.md)

## Repository layout

```
Caching-LLM/
├── Task 1/    # semantic_cache + FastAPI /chat demo
├── Task 2/    # ridhi WhatsApp webhook + state manager
└── Task 3/    # RERA KG schema (markdown)
```
