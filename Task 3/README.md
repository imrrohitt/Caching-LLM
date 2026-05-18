# Task 3: RERA Knowledge Graph Schema — Design Only

Written design for **Leela** (PropOS RERA Compliance AI): Neo4j schema, ingestion pipeline, Cypher examples, and GraphRAG vs vector RAG analysis.

**No code** — documentation only (per task brief).

## Document

| File | Contents |
|------|----------|
| [docs/RERA_KNOWLEDGE_GRAPH_SCHEMA.md](docs/RERA_KNOWLEDGE_GRAPH_SCHEMA.md) | Full schema design (§17–§22) |

## Quick navigation

- **Nodes:** Document, Section, Clause, Project, Developer, Plot, Deadline, RegulatoryAuthority, DateReference
- **Edges:** `REFERENCES`, `REFERENCES_DOCUMENT`, `HAS_SECTION`, `IMPOSES_DEADLINE`, `AMENDS`, …
- **Cypher:** Section 4 Greenview Heights → all referenced docs/clauses
- **KG wins:** cross-doc citations, multi-hop deadlines, superseded MOUs
- **Limits:** OCR quality, state-wise format drift

## Evaluation alignment (15% — RERA KG depth)

- Node/edge types are **RERA-specific** (approval letter, MOU, Form B, MahaRERA, plot survey numbers)
- Cypher traverses `REFERENCES` / `REFERENCES_DOCUMENT` from a named section
- Three vector-RAG failure cases are **concrete** to Indian RERA packs, not generic FAQ examples
