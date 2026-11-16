# E.D.I.T.H. Brain Core

Independent, reusable knowledge and memory foundation for the E.D.I.T.H. personal AI intelligence system.

---

## Hardware & Operating Constraints
- **Host OS:** Windows 11 (64-bit)
- **RAM Constraint:** 8 GB RAM profile
- **Compute:** CPU-only (No GPU dependency)
- **Software Cost:** Zero budget (Open-source, local-first stack)
- **Runtime:** Python 3.13+, SQLite 3.53+ (with native FTS5)

---

## Architectural Principles
1. **Modular Monolith:** Single unified service with strict layer boundaries (`API` -> `Service` -> `Repository` -> `Storage`).
2. **First-Class Personal Memory:** Distinguishes `personal` facts (profile, preferences, goals, skills, project context, decisions) from `semantic`, `episodic`, and `procedural` memories.
3. **Privacy Sovereignty & Hard Purge:** Memory revocation deactivates memories for history; permanent purge physically deletes memory rows and redacts sensitive snapshots from all audit logs.
4. **SQLite Concurrency Resilience:** Write-Ahead Logging (WAL), busy timeouts (5000ms), per-connection foreign keys, and `BEGIN IMMEDIATE` transaction boundaries eliminate deadlocks.
5. **Decoupled Document Tiers:** Decouples original uploaded binary files, extracted plaintext, and document chunks with deep retrieval provenance (`page_number`, `section`, `source_location`, `extraction_method`, `content_hash`).
6. **Multi-Format Ingestion:** Native, isolated parser adapters for PDF, Markdown, Plain Text, and DOCX files.
7. **Hybrid Retrieval (Keyword + Semantic):** SQLite FTS5 BM25 search, local dense vector embeddings with cosine similarity, and Reciprocal Rank Fusion (RRF).
8. **No Unearned Complexity:** Zero cloud dependencies, zero external vector DBs, and zero heavy LLMs in Phases B0, B1, and B2.

---

## Quickstart & Operational Guide

### 1. Installation
Clone or navigate to `D:\edith-brain-core`:
```powershell
cd D:\edith-brain-core
python -m pip install -e .
python -m pip install pytest pytest-asyncio httpx pydantic-settings pypdf python-docx python-multipart fastembed
```

### 2. Running Automated Tests
```powershell
python -m pytest tests -v
```

### 3. Starting the Local API Server
```powershell
python -m uvicorn edith_brain.api.app:create_app --factory --host 127.0.0.1 --port 8000
```
Interactive API documentation is available locally at: `http://127.0.0.1:8000/docs`

---

## API Summary

| Method | Endpoint | Description | Phase |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Health diagnostics, SQLite WAL mode, and PRAGMA status | B0 |
| `GET` | `/api/v1/system/info` | Engine version and memory category capabilities | B0 |
| `POST` | `/api/v1/memories` | Create structured personal, semantic, episodic, or procedural memory | B0 |
| `GET` | `/api/v1/memories/{id}` | Retrieve memory with source provenance and lineage | B0 |
| `POST` | `/api/v1/memories/{id}/correct` | Correct memory (supersedes predecessor, preserves lineage) | B0 |
| `POST` | `/api/v1/memories/{id}/revoke` | Revoke/deactivate memory | B0 |
| `DELETE` | `/api/v1/memories/{id}/purge` | Permanent hard delete with audit snapshot redaction | B0 |
| `GET` | `/api/v1/memories/{id}/audit` | View immutable audit trail for a memory | B0 |
| `GET` | `/api/v1/memories` | List memories with category, subcategory, and status filtering | B0 |
| `POST` | `/api/v1/documents/upload` | Multipart binary upload (PDF, MD, TXT, DOCX) with auto-chunking & embeddings | B1/B2 |
| `POST` | `/api/v1/documents` | Ingest knowledge document from JSON payload (B0 backward compatible) | B0/B1 |
| `GET` | `/api/v1/documents` | List ingested documents with pagination & status filter | B1 |
| `GET` | `/api/v1/documents/{id}` | Retrieve document metadata | B0/B1 |
| `GET` | `/api/v1/documents/{id}/status` | Retrieve ingestion status, chunk count, and errors | B1 |
| `DELETE` | `/api/v1/documents/{id}` | Delete document, cascade chunks, and clean storage files | B1 |
| `POST` | `/api/v1/documents/{id}/chunks` | Store atomic document chunk with deep retrieval provenance | B0/B1 |
| `GET` | `/api/v1/documents/{id}/chunks` | Retrieve all chunks and provenance for a document | B0/B1 |
| `POST` | `/api/v1/retrieval/search` | Search knowledge chunks (`mode`: `hybrid`, `keyword`, `semantic`) | **B2** |
| `GET` | `/api/v1/retrieval/search` | Convenience GET search query endpoint with query parameters | **B2** |
| `POST` | `/api/v1/retrieval/index-embeddings` | On-demand batch embedding generation for document chunks | **B2** |
| `GET` | `/api/v1/retrieval/stats` | Inspect index statistics (document, chunk, FTS5, embedding counts) | **B2** |
| `POST` | `/api/v1/memories/search` | Search personal memories (keyword, semantic, hybrid RRF with fallback) | **B3** |
| `POST` | `/api/v1/memories/check-conflicts` | Pre-flight duplicate, contradiction, and conflict detection | **B3** |
| `POST` | `/api/v1/memories/{id}/verify` | State-machine governed verification status transitions | **B3** |
| `GET` | `/api/v1/memories/{id}/verifications` | Append-only verification audit history trail | **B3** |
| `POST` | `/api/v1/memories/{id}/citations` | Link memory to document/chunk provenance with parentage check | **B3** |
| `GET` | `/api/v1/memories/{id}/citations` | Retrieve provenance citations with source-removal tracking | **B3** |
| `POST` | `/api/v1/memories/{id}/associations` | Create directed relation edge with acyclic cycle check | **B3** |
| `GET` | `/api/v1/memories/{id}/associations` | Retrieve incoming and outgoing graph associations | **B3** |
| `DELETE` | `/api/v1/memories/{id}/associations/{id}` | Delete memory association edge | **B3** |
| `POST` | `/api/v1/memories/reindex-embeddings` | Staged batch re-indexing for target model version | **B3** |
| `POST` | `/api/v1/memories/cutover-active-model` | Atomic cutover with anti-join completeness verification | **B3** |
| `GET` | `/api/v1/memories/active-model` | Get active memory embedding model configuration | **B3** |
| `POST` | `/api/v1/episodes` | Record discrete episodic event (conversation, task, incident) | **B4** |
| `POST` | `/api/v1/episodes/timeline` | Query chronological timeline with significance & FTS filters | **B4** |
| `GET` | `/api/v1/episodes/sessions` | List aggregated conversational & task sessions | **B4** |
| `GET` | `/api/v1/episodes/{id}` | Retrieve episodic event details | **B4** |
| `DELETE` | `/api/v1/episodes/{id}` | Delete episodic event with cascade cleanup | **B4** |
| `POST` | `/api/v1/episodes/{id}/links` | Create cross-domain link to procedure or personal memory | **B4** |
| `GET` | `/api/v1/episodes/{id}/links` | Retrieve all cross-domain links for an episode | **B4** |
| `POST` | `/api/v1/procedures` | Register operational playbook with sequential steps | **B4** |
| `GET` | `/api/v1/procedures` | List procedures with status filtering & pagination | **B4** |
| `GET` | `/api/v1/procedures/search` | Search procedures via FTS5 trigger condition & content | **B4** |
| `GET` | `/api/v1/procedures/{id}` | Retrieve procedure steps, conditions, and telemetry | **B4** |
| `PATCH` | `/api/v1/procedures/{id}/status` | Update procedure lifecycle status (`draft`, `active`, `deprecated`) | **B4** |
| `POST` | `/api/v1/procedures/{id}/execute` | Log execution telemetry, updating live success rates | **B4** |
| `GET` | `/api/v1/procedures/{id}/executions` | Retrieve execution telemetry log history for a procedure | **B4** |
| `DELETE` | `/api/v1/procedures/{id}` | Physically delete procedure | **B4** |
| `POST` | `/api/v1/intelligence/touch` | Touch memories to update access telemetry without mutating content | **B5** |
| `GET` | `/api/v1/intelligence/decay/{id}` | Evaluate recency decay and combined relevance score for a memory | **B5** |
| `POST` | `/api/v1/intelligence/consolidations/session` | Distill prospective semantic facts from an episodic session | **B5** |
| `POST` | `/api/v1/intelligence/consolidations` | Manually propose an episodic consolidation candidate | **B5** |
| `GET` | `/api/v1/intelligence/consolidations` | List consolidation candidates with status and session filters | **B5** |
| `POST` | `/api/v1/intelligence/consolidations/{id}/review` | Approve or reject a candidate, linking derived memory on approval | **B5** |
| `GET` | `/api/v1/intelligence/compaction/plan` | Generate advisory compaction plan identifying redundant clusters | **B5** |
| `POST` | `/api/v1/intelligence/compaction/execute` | Execute or dry-run a compaction plan with confirmation safeguard | **B5** |
| `POST` | `/api/v1/evaluation/benchmark` | Execute benchmark suite measuring P@K, R@K, MRR, NDCG, latency | **B5** |

---

## Phase B5 Status & Verified Deliverables
- [x] Checksum-verified migration `006_memory_intelligence_and_decay.sql` applied cleanly.
- [x] Memory telemetry tracking (`access_count`, `last_accessed_at`) with non-mutating touch endpoint.
- [x] Exponential half-life recency decay engine (`MemoryDecayEngine`) with subcategory-specific half-life defaults and dynamic relevance scoring.
- [x] Episodic-to-semantic consolidation service (`MemoryConsolidationService`) extracting candidate facts with human-in-the-loop approval workflow and derived provenance links.
- [x] Near-duplicate compaction service (`MemoryCompactionService`) detecting overlapping memories with advisory planning, dry-run preview, and confirmed execution.
- [x] Quantitative evaluation benchmark suite (`EvaluationBenchmarkService`) computing P@K, R@K, MRR, NDCG, and latency profiling persisted in `memory_evaluation_runs`.
- [x] Architectural integrity audits verifying citation parentage, cycle prevention, and verification state transitions.

---

## Phase B6 Status & Verified Deliverables (Full Roadmap Complete)
- [x] Strongly-typed, synchronous Python client SDK (`EdithBrainClient`) covering 100% of Brain Core API endpoints with both HTTP and in-process ASGI test transport support.
- [x] Authoritative static OpenAPI 3.1 specification exported to `docs/openapi.json` (211 KB).
- [x] Production service execution scripts for Windows 11: PowerShell launcher (`scripts/start_server.ps1`) and Command Prompt batch script (`scripts/start_server.bat`).
- [x] Comprehensive developer and integration guide authored in `docs/INTEGRATION_GUIDE.md`.
- [x] End-to-end multi-domain workflow integration test (`test_e2e_workflow.py`) validating unified interaction across document ingestion, hybrid search, personal memory verification, procedural execution, episodic logging, decay scoring, and benchmarking.
- [x] 132/132 automated unit and integration tests passing in ~12s.

---

## Architectural Decision Records (ADRs)
- [ADR 001: B0 Foundation & Modular Monolith](docs/adr_001_b0_foundation.md)
- [ADR 002: B1 Document Ingestion & Provenance](docs/adr_002_b1_document_ingestion.md)
- [ADR 003: B2 Hybrid Retrieval & Embedding Provider](docs/adr_003_b2_retrieval_foundation.md)
- [ADR 004: B3 Personal Memory Intelligence & Verification](docs/adr_004_b3_personal_memory.md)
- [ADR 005: B4 Episodic & Procedural Memory Systems](docs/adr_005_b4_episodic_procedural_memory.md)
- [ADR 006: B5 Memory Intelligence, Decay & Benchmarking](docs/adr_006_b5_memory_intelligence_and_evaluation.md)
- [ADR 007: B6 Stable API, Client SDK & Integration Readiness](docs/adr_007_b6_stable_api_and_integration.md)
