# ADR 001: Architecture Foundation and Concurrency Model for E.D.I.T.H. Brain Core

## Context
E.D.I.T.H. Brain Core is an independent, reusable knowledge and memory foundation designed to power future AI systems. The operational environment is a Windows 11 host with 8 GB RAM, CPU-only hardware, and zero software budget. The system must operate locally, reliably, and with strict data privacy.

## Architectural Decisions

### 1. Modular Monolith Architecture
- **Decision:** Brain Core is designed as a single Python codebase with strict 4-layer internal separation: `API Layer` -> `Domain Service Layer` -> `Repository Layer` -> `Storage Layer`.
- **Rationale:** Avoids the operational overhead of microservices on constrained 8 GB RAM hardware while maintaining clean separation of concerns and independent testability.

### 2. Personal Memory as a First-Class Category
- **Decision:** In addition to `semantic`, `episodic`, and `procedural` memory, `personal` memory is established as a first-class domain category with 6 dedicated subcategories:
  - `profile_fact`
  - `preference`
  - `goal`
  - `skill`
  - `project_context`
  - `decision`
- **Invariant:** Unverified knowledge document assertions cannot automatically become personal facts without explicit verification.

### 3. Memory Lifecycle: Revocation vs. Permanent Purge
- **Decision:**
  - **Revocation:** Soft deactivation marking status as `revoked`. Preserved for lineage and history but excluded from active memory retrieval.
  - **Permanent Purging:** Hard physical deletion of the row from `memories` table combined with **complete redaction** of historical snapshots inside `memory_audit_log` (`previous_state_json` replaced with `'[REDACTED_PURGED]'`).
- **Rationale:** Ensures privacy compliance (GDPR right-to-be-forgotten) so that deleted personal information is never preserved inside audit backups.

### 4. SQLite Concurrency & Single-Writer Protocol
- **Decision:**
  - Database operates under SQLite's **WAL (Write-Ahead Logging)** mode.
  - Single-writer / multi-reader model: Readers never block writers, and writers never block readers.
  - Per-connection PRAGMA enforcement: `foreign_keys = ON;`, `journal_mode = WAL;`, `synchronous = NORMAL;`, `busy_timeout = 5000;`.
  - Write transactions explicitly use `BEGIN IMMEDIATE` to acquire the SQLite reserved lock upfront, eliminating lock escalation deadlocks (`SQLITE_BUSY`).

### 5. Multi-Tier Document Storage & Retrieval Provenance
- **Decision:** Storage is decoupled into:
  1. `raw_storage`: Binary/original files stored content-addressed by SHA-256 with traversal-safe path validation and file-size enforcement.
  2. `extracted_storage`: Clean UTF-8 plaintext files.
  3. `document_chunks`: Atomic search units in SQLite storing exact retrieval provenance: `document_id`, `chunk_index`, `page_number`, `section`, `source_location`, `extraction_method`, and `content_hash`.

### 6. Schema Migrations with Tamper Detection
- **Decision:** Migrations are tracked in `schema_migrations` with SHA-256 checksums. On startup, previously applied migrations are verified against disk scripts to ensure database integrity.

## Consequences & Limitations
- Vector search and embeddings are intentionally deferred to Phase B1/B2 to maintain low resource footprint and ensure solid foundations.
- No external cloud services or LLMs are involved in Phase B0.
