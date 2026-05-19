# RERA Knowledge Graph Schema

Design for **Leela** (RERA compliance): Neo4j schema, ingestion pipeline, Cypher examples, and when graph RAG outperforms vector-only RAG on cross-document citations.

Documentation only — no application code in this module.

## Main document

[docs/RERA_KNOWLEDGE_GRAPH_SCHEMA.md](docs/RERA_KNOWLEDGE_GRAPH_SCHEMA.md)

## Contents

- **Nodes:** Document, Section, Clause, Project, Developer, Plot, Deadline, RegulatoryAuthority, DateReference  
- **Edges:** `REFERENCES`, `REFERENCES_DOCUMENT`, `HAS_SECTION`, `IMPOSES_DEADLINE`, `AMENDS`, …  
- **Cypher:** e.g. all documents/clauses referenced by Section 4 of an approval letter  
- **Graph vs vector:** citation chains, multi-hop deadlines, superseded MOUs  
- **Limits:** OCR quality, state-wise format differences  
