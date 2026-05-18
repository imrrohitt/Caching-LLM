# PropOS — Assessment Tasks

This repository contains two independent deliverables:

| Folder | Task | Description |
|--------|------|-------------|
| [**Task 1**](Task%201/) | Semantic Prompt Cache | Embedding-based LLM prompt cache with FastAPI demo |
| [**Task 2**](Task%202/) | Ridhi — WhatsApp Session State | Priya CP onboarding state (Monday–Thursday scenario) |
| [**Task 3**](Task%203/) | RERA Knowledge Graph Schema | Leela cross-document RAG — design only (Neo4j schema) |

## Quick start

### Task 1 — Semantic Prompt Cache

```bash
cd "Task 1"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v -m "not integration"
./scripts/run_demo.sh
```

See [Task 1/README.md](Task%201/README.md) for full documentation.

### Task 2 — WhatsApp Session State

```bash
cd "Task 2"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
./scripts/run_webhook.sh
```

See [Task 2/README.md](Task%202/README.md) and [Task 2/docs/ARCHITECTURE.md](Task%202/docs/ARCHITECTURE.md).

### Task 3 — RERA Knowledge Graph (design only)

```bash
cd "Task 3"
# Read the design document — no code to run
open docs/RERA_KNOWLEDGE_GRAPH_SCHEMA.md
```

See [Task 3/docs/RERA_KNOWLEDGE_GRAPH_SCHEMA.md](Task%203/docs/RERA_KNOWLEDGE_GRAPH_SCHEMA.md).
