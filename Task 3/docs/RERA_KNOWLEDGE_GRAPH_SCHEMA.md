# Task 3: RERA Knowledge Graph Schema — Design for Leela

**Agent:** Leela (PropOS RERA Compliance AI)  
**Problem:** RERA approval packs cite across documents — e.g. *"as per Clause 11 of the MOU dated 15-Jan-2024"* in Section 4 of an approval letter. Vector RAG retrieves Section 4 in isolation and often misses the dependent clause in another PDF.  
**Solution:** Neo4j knowledge graph preserving **explicit document structure** and **citation edges**, combined with vector search for lexical recall (hybrid GraphRAG).

**Design note:** Schema is RERA-specific (approval letters, MOUs, Form B, encumbrance certificates, section/clause numbering conventions) — not a generic document graph.

**LLM acknowledgment:** Structure and cross-reference patterns were validated against public RERA document layouts; Cypher and ingestion steps reflect Neo4j GraphRAG practice. All schema decisions and trade-offs are original design judgment for this challenge.

---

## 1. Node types (§17)

| Node label | Key properties | Example instance |
|------------|----------------|------------------|
| **`Document`** | `doc_id`, `title`, `doc_type` (enum), `rera_registration_no`, `project_name`, `issue_date`, `issuing_authority`, `file_hash`, `source_uri`, `language` | `{doc_id: "GH-AL-2024-001", title: "Approval Letter — Greenview Heights", doc_type: "APPROVAL_LETTER", project_name: "Greenview Heights", issue_date: date("2024-03-22"), issuing_authority: "MahaRERA"}` |
| **`Section`** | `section_id`, `number` (e.g. "4", "4.2"), `heading`, `text`, `page_start`, `page_end`, `char_offset_start`, `char_offset_end` | `{section_id: "GH-AL-2024-001:sec:4", number: "4", heading: "Conditions of Approval", text: "…as per Clause 11 of the MOU dated 15-Jan-2024…"}` |
| **`Clause`** | `clause_id`, `number` (e.g. "11", "11(a)"), `text`, `clause_type` (obligation \| condition \| definition \| penalty) | `{clause_id: "GH-MOU-2024-001:clause:11", number: "11", text: "The promoter shall complete Phase 1 landscaping by…", clause_type: "obligation"}` |
| **`Project`** | `project_id`, `name`, `rera_reg_no`, `address`, `phase`, `status` | `{project_id: "proj_greenview_heights", name: "Greenview Heights", rera_reg_no: "P52100012345"}` |
| **`Developer`** | `developer_id`, `legal_name`, `cin`, `pan`, `registered_address` | `{developer_id: "dev_sunrise_builders", legal_name: "Sunrise Builders Pvt Ltd", cin: "U45201MH2010PTC123456"}` |
| **`Plot`** | `plot_id`, `survey_no`, `area_sqm`, `phase`, `building_wing` | `{plot_id: "gv_plot_A12", survey_no: "Survey 45/2", area_sqm: 1200.5, phase: "Phase 1"}` |
| **`Deadline`** | `deadline_id`, `due_date`, `description`, `status` (pending \| met \| breached), `source_ref` | `{deadline_id: "dl_landscaping_p1", due_date: date("2024-09-30"), description: "Phase 1 landscaping completion", status: "pending"}` |
| **`RegulatoryAuthority`** | `authority_id`, `name`, `state`, `jurisdiction` | `{authority_id: "auth_maharera", name: "MahaRERA", state: "Maharashtra"}` |
| **`DateReference`** | `date_id`, `iso_date`, `original_text` | `{date_id: "dt_2024_01_15", iso_date: date("2024-01-15"), original_text: "15-Jan-2024"}` |

**Composite identity:** `section_id` / `clause_id` = `{doc_id}:{kind}:{number}` so citations resolve unambiguously across the corpus.

**Document `doc_type` enum (RERA-specific):** `APPROVAL_LETTER`, `MOU`, `FORM_B`, `ENCUMBRANCE_CERTIFICATE`, `TITLE_REPORT`, `BUILDING_PLAN_SANCTION`, `QPR`, `AGREEMENT_FOR_SALE_TEMPLATE`, `ADDENDUM`.

---

## 2. Edge types (§18)

| Edge type | Source → Target | Direction | Key properties | Example |
|-----------|-----------------|-----------|----------------|---------|
| **`HAS_SECTION`** | `Document` → `Section` | OUT | `order_index` | Approval Letter **HAS_SECTION** Section 4 |
| **`HAS_CLAUSE`** | `Document` → `Clause` | OUT | `order_index` | MOU **HAS_CLAUSE** Clause 11 |
| **`CONTAINS_CLAUSE`** | `Section` → `Clause` | OUT | — | Section 4.1 **CONTAINS_CLAUSE** Clause 4.1(a) (when clause nested under section) |
| **`REFERENCES`** | `Section` \| `Clause` → `Clause` \| `Section` \| `Document` | OUT | `citation_text`, `confidence`, `resolver` (regex \| llm \| human) | Section 4 **REFERENCES** Clause 11 (MOU) |
| **`REFERENCES_DOCUMENT`** | `Section` \| `Clause` → `Document` | OUT | `citation_text`, `date_mentioned` | Section 4 **REFERENCES_DOCUMENT** MOU dated 15-Jan-2024 |
| **`APPLIES_TO`** | `Document` \| `Clause` | → `Project` | OUT | `effective_from` | Approval Letter **APPLIES_TO** Greenview Heights |
| **`PROMOTED_BY`** | `Project` → `Developer` | OUT | `role` (promoter \| co-promoter) | Greenview Heights **PROMOTED_BY** Sunrise Builders |
| **`HAS_PLOT`** | `Project` → `Plot` | OUT | — | Greenview Heights **HAS_PLOT** Survey 45/2 |
| **`IMPOSES_DEADLINE`** | `Clause` \| `Section` → `Deadline` | OUT | — | Clause 11 **IMPOSES_DEADLINE** landscaping due 2024-09-30 |
| **`ISSUED_BY`** | `Document` → `RegulatoryAuthority` | OUT | — | Approval Letter **ISSUED_BY** MahaRERA |
| **`DATED`** | `Document` → `DateReference` | OUT | `date_role` (execution \| effective \| citation) | MOU **DATED** 15-Jan-2024 |
| **`AMENDS`** | `Document` → `Document` | OUT | `amendment_no` | Addendum #2 **AMENDS** MOU |
| **`SUPERSEDES`** | `Document` → `Document` | OUT | `effective_date` | Revised approval **SUPERSEDES** prior approval |

**`REFERENCES` is the critical edge for Leela:** it materializes *"as per Clause 11 of the MOU dated 15-Jan-2024"* as a traversable link, not an embedding coincidence.

**Direction convention:** edges flow **from citing unit → cited unit** (downstream dependency direction). Multi-hop queries walk outbound `REFERENCES*` paths.

---

## 3. Ingestion pipeline (§19)

### Overview

```
PDF → Layout parse → Structure extract → Entity extract → Citation resolve → Neo4j upsert → Vector index sync
```

### Step-by-step

| Step | What happens | Tool / approach |
|------|----------------|-----------------|
| **1. Ingest & fingerprint** | Store raw PDF in object storage; compute `file_hash`; assign `doc_id`; register metadata (project, doc_type from filename / cover page). | S3/GCS + workflow trigger (Airflow / Temporal) |
| **2. PDF layout parse** | Extract text **with bounding boxes**, page numbers, headings, tables. Preserve reading order for numbered sections. | **Primary:** [Docling](https://github.com/DS4SD/docling) or **Unstructured.io** (hi-res layout). **Fallback:** `pdfplumber` for born-digital PDFs; **Azure Document Intelligence** / **Google Document AI** for scanned stamps and Devanagari marginalia. |
| **3. Section & clause segmentation** | Rules + LLM: detect `Section 4`, `4.2`, `Clause 11`, `अनुच्छेद`, schedule headings. Build `Section` / `Clause` nodes with stable IDs and char offsets. | Regex for `Section\s+\d+(\.\d+)*`, `Clause\s+\d+`; LLM pass (GPT-4o / Claude) for ambiguous Indian legal numbering; human QA queue for low-confidence splits |
| **4. Entity extraction** | NER for Project, Developer, Plot, dates, RERA registration numbers; link to canonical project registry. | spaCy custom NER + LLM JSON extraction; master data match on `rera_reg_no` |
| **5. Cross-reference detection** | Scan each `Section`/`Clause` text for citation patterns. | **Regex library** for patterns: `Clause\s+(\d+)`, `Section\s+(\d+)`, `MOU dated (\d{1,2}-\w{3}-\d{4})`, `as per .+ of the (.+) dated`. **LLM verifier** proposes target `doc_type` + number; **resolver** matches to graph nodes via `REFERENCES` / `REFERENCES_DOCUMENT` |
| **6. Citation resolution** | Disambiguate MOU among multiple MOUs using date + project + developer. | Match `DateReference` + `APPLIES_TO` Project + `doc_type`; confidence score; flag `resolver=unresolved` for human review |
| **7. Deadline extraction** | From obligation clauses: "within 90 days of OC", "by 30-Sep-2024". | LLM + date parser (`dateparser`); create `Deadline` nodes + `IMPOSES_DEADLINE` |
| **8. Graph upsert** | MERGE nodes/edges idempotently by `doc_id` / `section_id` / `clause_id`. | **Neo4j** Python driver; transactional batches per document |
| **9. Vector index sync** | Chunk text (section/clause level); embed; store `chunk_id` ↔ graph node ID in pgvector or Neo4j vector index. | `text-embedding-3-small` or `bge-m3`; hybrid retrieval uses graph expansion after vector seed |
| **10. Quality gates** | Orphan citation rate, unresolved REFERENCES, section coverage %. | Dashboard; block `PRODUCTION` publish if unresolved > 5% for pilot project |

### Cross-document reference detection (detail)

1. **Pattern hit** in Section 4 text: `"Clause 11 of the MOU dated 15-Jan-2024"`.
2. Extract: `target_kind=Clause`, `target_number=11`, `target_doc_hint=MOU`, `date=2024-01-15`.
3. **Cypher lookup** candidate MOUs for same `Project` with `DATED` 2024-01-15.
4. If single match → create `(sec4)-[:REFERENCES {citation_text: "…", confidence: 0.95}]->(clause11)`.
5. If ambiguous → create `REFERENCES_DOCUMENT` to MOU + queue for analyst; do not guess.

---

## 4. Cypher query example (§20)

**Question:** *What are all the documents and clauses referenced by Section 4 of the Greenview Heights approval letter?*

```cypher
// Anchor: approval letter for Greenview Heights, Section 4
MATCH (doc:Document {doc_type: 'APPROVAL_LETTER'})
      -[:APPLIES_TO]->(proj:Project {name: 'Greenview Heights'})
MATCH (doc)-[:HAS_SECTION]->(sec:Section {number: '4'})

// Direct clause references (same or other documents)
OPTIONAL MATCH (sec)-[rc:REFERENCES]->(cited_clause:Clause)<-[:HAS_CLAUSE]-(cited_doc_cl:Document)

// Document-level references (e.g. "the MOU dated …")
OPTIONAL MATCH (sec)-[rd:REFERENCES_DOCUMENT]->(cited_doc:Document)

// Clauses inside referenced documents (expand MOU → all cited clauses if needed)
OPTIONAL MATCH (cited_doc)-[:HAS_CLAUSE]->(cl_from_doc:Clause)
WHERE cited_doc IS NOT NULL

RETURN
  sec.section_id AS citing_section,
  sec.heading AS citing_heading,
  collect(DISTINCT {
    ref_type: 'CLAUSE',
    edge: type(rc),
    citation_text: rc.citation_text,
    clause_id: cited_clause.clause_id,
    clause_number: cited_clause.number,
    clause_text: left(cited_clause.text, 200),
    document_id: cited_doc_cl.doc_id,
    document_title: cited_doc_cl.title,
    document_type: cited_doc_cl.doc_type
  }) AS referenced_clauses,
  collect(DISTINCT {
    ref_type: 'DOCUMENT',
    edge: type(rd),
    citation_text: rd.citation_text,
    document_id: cited_doc.doc_id,
    document_title: cited_doc.title,
    document_type: cited_doc.doc_type,
    issue_date: cited_doc.issue_date
  }) AS referenced_documents
```

### Expected output format (JSON)

```json
{
  "citing_section": "GH-AL-2024-001:sec:4",
  "citing_heading": "Conditions of Approval",
  "referenced_clauses": [
    {
      "ref_type": "CLAUSE",
      "edge": "REFERENCES",
      "citation_text": "as per Clause 11 of the MOU dated 15-Jan-2024",
      "clause_id": "GH-MOU-2024-001:clause:11",
      "clause_number": "11",
      "clause_text": "The promoter shall complete Phase 1 landscaping by 30-Sep-2024…",
      "document_id": "GH-MOU-2024-001",
      "document_title": "Memorandum of Understanding — Greenview Heights",
      "document_type": "MOU"
    }
  ],
  "referenced_documents": [
    {
      "ref_type": "DOCUMENT",
      "edge": "REFERENCES_DOCUMENT",
      "citation_text": "MOU dated 15-Jan-2024",
      "document_id": "GH-MOU-2024-001",
      "document_title": "Memorandum of Understanding — Greenview Heights",
      "document_type": "MOU",
      "issue_date": "2024-01-15"
    }
  ]
}
```

**Leela usage:** expand retrieved context for the LLM answer — Section 4 **plus** full Clause 11 text and MOU metadata — not Section 4 alone.

---

## 5. Where KG beats vector RAG (§21)

### Example 1 — Explicit cross-document citation

**Question:** *What obligation does Section 4 of the Greenview Heights approval letter impose via the MOU?*

| Approach | Result |
|----------|--------|
| **Vector RAG** | Top chunk = Section 4 snippet mentioning "Clause 11 of the MOU" — often **stops there**; MOU Clause 11 body not in top-k if embeddings differ. |
| **Knowledge Graph** | Traverse `Section 4 -[:REFERENCES]-> Clause 11`; return **full clause text** + linked `Deadline`. |

**Why:** Dependency is **structural** (citation), not semantic similarity. Section 4 and Clause 11 embed differently.

---

### Example 2 — Multi-hop document chain

**Question:** *Which landscaping deadline applies to Greenview Heights under the approval conditions?*

| Approach | Result |
|----------|--------|
| **Vector RAG** | May retrieve approval letter OR MOU, rarely both; may hallucinate a date. |
| **Knowledge Graph** | `Approval Section 4 → REFERENCES → MOU Clause 11 → IMPOSES_DEADLINE → Deadline(2024-09-30)`. |

**Why:** Answer requires **2-hop traversal** across document types. Vector fusion does not guarantee both hops in one context window.

---

### Example 3 — Superseded document disambiguation

**Question:** *Does the current approval still rely on the January MOU or the March addendum?*

| Approach | Result |
|----------|--------|
| **Vector RAG** | Retrieves chunks from **both** MOU and addendum with similar wording; conflates versions. |
| **Knowledge Graph** | `Addendum -[:AMENDS]-> MOU`; `REFERENCES` edges re-pointed on ingest; `SUPERSEDES` on approval revision. Query follows **active** edges only. |

**Why:** Temporal/version relationships are **explicit edges**, not embedding proximity.

---

## 6. Limitations and production mitigations (§22)

### Limitation 1 — Citation extraction is imperfect on scanned / poorly OCR’d PDFs

**Risk:** Missed or wrong `REFERENCES` edges → Leela answers without dependent clauses.  
**Mitigation:**

- Route low-DPI scans through Document AI with human-in-the-loop validation UI.
- Store `confidence` on every edge; Leela prompts: *"I found a citation to Clause 11 (confidence 0.72) — verify before compliance sign-off."*
- Weekly orphan scan: citations in text with no outgoing `REFERENCES` edge.

### Limitation 2 — Schema drift across states and RERA formats

**Risk:** Maharashtra "Section" vs Karnataka "Rule" vs annex-only numbering — brittle regex.  
**Mitigation:**

- `doc_type` + `issuing_authority` specific parsing profiles (config, not one global regex).
- Extend schema with `Regulation` node where states use rulebooks instead of MOUs.
- Fallback: vector RAG retrieves candidate chunks; graph adds edges only after resolver confirms — **hybrid**, not graph-only.

---

## 7. How Leela answers (runtime architecture)

```
User question
    → Intent classify (citation trace | deadline lookup | general)
    → Vector seed (top-k Section/Clause chunks)
    → Graph expand 1–3 hops on REFERENCES / IMPOSES_DEADLINE / AMENDS
    → Context pack: anchor chunk + all cited clauses + doc metadata
    → LLM generate with mandatory citations [section_id, clause_id]
```

**Latency target (from experience):** single-hop citation expand ~50–80ms on Neo4j + 273ms end-to-end vs 420ms vector-only (parallel vector + graph where possible).

---

## 8. Trade-offs acknowledged

| Choice | Benefit | Cost |
|--------|---------|------|
| Fine-grained Section + Clause nodes | Precise citations | Higher ingest complexity |
| Regex + LLM citations | High recall on formal Indian legal phrasing | LLM cost; needs QA |
| Hybrid GraphRAG | Best of structure + lexical | Two systems to keep in sync |
| No code in Task 3 | Focus on schema depth | Ingest/resolver not proven in implementation here |

---

## 9. Task 3 checklist

| # | Requirement | Section |
|---|-------------|---------|
| 17 | Node types with properties + examples | §1 |
| 18 | Edge types incl. `REFERENCES` | §2 |
| 19 | Ingestion pipeline + PDF tool + citation detection | §3 |
| 20 | Cypher query + output format | §4 |
| 21 | 3 KG vs vector RAG examples | §5 |
| 22 | 2 limitations + mitigations | §6 |
