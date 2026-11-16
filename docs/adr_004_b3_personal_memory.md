# ADR 004: Phase B3 — Personal Memory Intelligence, Provenance, Verification, and Multi-Model Coexistence

## Status
Accepted and Implemented

## Context
In Phases B0 through B2, E.D.I.T.H. Brain Core established foundational document ingestion, keyword BM25 retrieval, and dense vector chunk search. Phase B3 elevates personal memory into a first-class, verifiable, associative knowledge foundation. To ensure that future personal AI systems do not hallucinate, conflate unverified statements with ground facts, or compromise data privacy, the personal memory engine requires:
1. Grounded document-to-memory citation provenance.
2. A strict verification authority state machine.
3. Multi-model embedding coexistence and atomic transactional cutover.
4. Advisory duplicate and contradiction conflict analysis.
5. Cycle-safe directed associations and canonical undirected links.
6. Local trust boundary protection.

## Decisions

### 1. Document Provenance Citations
Replaced unstructured string identifiers with a dedicated relational table `memory_citations`.
- Enforces parentage validation ensuring cited chunks belong to the cited document.
- Stores immutable `historical_document_id` and `historical_chunk_id` alongside foreign keys with `ON DELETE SET NULL`.
- Automatic SQLite triggers transition `citation_status` to `'source_removed'` when source documents are deleted without violating check constraints or blocking document deletions.

### 2. State-Governed Verification Machine
Defined explicit states: `UNVERIFIED`, `NEEDS_REVIEW`, `VERIFIED`, `REJECTED`, and methods: `USER_CONFIRMED`, `DOCUMENT_SUPPORTED`, `EXTERNALLY_VERIFIED`, `SYSTEM_INFERRED`.
- Prohibited direct jumps (such as `REJECTED -> VERIFIED` without passing through `NEEDS_REVIEW`).
- Trigger-enforced append-only immutability on `memory_verifications`.
- Corrected memories receive fresh `UNVERIFIED` status; never inherit verification status from predecessors.

### 3. Multi-Model Embedding Coexistence & Cutover
Vectors in `memory_embeddings` are keyed by composite primary key `(memory_id, model_name, model_version)`.
- Prevents mixing vectors from incompatible models.
- Staged batch re-indexing validates 100% of active memories via an anti-join completeness check before cutover.
- In-place content updates trigger automatic stale vector eviction (`trg_memories_content_stale_emb`).
- The active model registry starts empty, defaulting gracefully to keyword retrieval when no neural model is active.

### 4. Advisory Conflict Engine
Classifies memory overlaps with strict precedence:
1. `POTENTIAL_DUPLICATE` (identical slots / high Jaccard / high semantic similarity).
2. `POTENTIAL_CONTRADICTION` (antonym clashes, negation inversion, conflicting slot values).
3. `RELATED_ACTIVE` (topical overlap without contradiction).
4. `NO_CONFLICT_DETECTED` (absence of heuristic matches; disclaimed from safety or truth guarantees).
- Strictly advisory: never executes automatic overwrites, merges, or supersessions.

### 5. Association Graph Integrity
- Enforced canonical sorting for symmetric `relates_to` edges (`source_memory_id < target_memory_id`).
- Cycle detection on `supersedes` relations via recursive CTE with `UNION`.

### 6. Local Trust Boundary
- Bound to `127.0.0.1`.
- Protected endpoints require bearer tokens verified against local permission-restricted `data/.edith_token`.
- Health check endpoints explicitly exempted.

## Consequences
- **Positive**: Absolute traceability from memory statements to supporting documents, strict privacy guarantees during hard purge, zero cross-model vector contamination, and verified acyclic association graphs.
- **Constraints**: Semantic similarity requires explicit neural model cutover; otherwise, search and conflict checks operate deterministically in keyword and lexical-slot mode.
