# ADR 006: Phase B5 — Memory Intelligence, Decay Dynamics, Episodic Consolidation, and Evaluation Benchmarks

## Status
Accepted and Implemented

## Context
Following the completion of the core personal, episodic, and procedural storage layers in Phases B0 through B4, autonomous personal AI requires active cognitive memory intelligence:
1. **Decay Dynamics**: Stale, untouched memories must not perpetually overpower recent, frequently-accessed context in retrieval ranking.
2. **Episodic Consolidation**: High-significance conversational and task execution milestones must be distillable into long-term personal semantic facts and preferences.
3. **Memory Compaction**: Overlapping, redundant, or near-duplicate memories must be safely identified and merged under explicit human/system confirmation safeguards.
4. **Quantitative Evaluation Benchmarks**: Empirical performance verification measuring Precision@K, Recall@K, MRR, NDCG, query latency, and architectural integrity audits.

## Decisions

### 1. Recency Decay & Access Telemetry
- Migration `006_memory_intelligence_and_decay.sql` adds `access_count` (`INTEGER DEFAULT 0`) and `last_accessed_at` (`TEXT NULL`) to the `memories` table, indexed by `idx_memories_access`.
- Implemented `MemoryDecayEngine` computing half-life exponential decay:
  $$\text{DecayScore}(t) = \text{base\_confidence} \times e^{-\frac{\ln(2) \cdot \Delta t}{T_{\text{half-life}}}}$$
- Defined subcategory-specific retention profiles (e.g. `preference`: 180 days, `project_context`: 30 days).
- Provided dynamic multi-factor scoring combining retrieval similarity, recency decay factor, and logarithmic access frequency bonuses.
- Implemented endpoint `POST /api/v1/intelligence/touch` to update access telemetry without mutating content or triggering vector re-indexing.

### 2. Episodic-to-Semantic Consolidation Pipeline
- Created `memory_consolidations` review table to queue candidate facts distilled from episodic clusters.
- `MemoryConsolidationService` extracts candidate facts from high-significance episodes ($s \ge 0.5$).
- Human-in-the-loop review workflow (`POST /api/v1/intelligence/consolidations/{id}/review`):
  - **Approve**: Spawns an unverified personal memory via `MemoryService` and creates `episodic_procedural_links` (`link_type="derived_memory"`) connecting the new memory to its source episodes.
  - **Reject**: Archives candidate with status `'rejected'` without mutating persistent semantic memories.

### 3. Memory Compaction & Safe Deduplication
- `MemoryCompactionService` groups memories by subcategory and computes pairwise Jaccard token overlap.
- Generates an advisory `CompactionPlan` detailing candidate clusters and space savings without mutating data.
- Execution safeguard: requires `confirmed=True` and supports `dry_run=True` previews.
- Compaction creates a unified consolidated memory while recording supersession lineage across constituent memories.

### 4. Quantitative Evaluation Benchmark Suite
- `EvaluationBenchmarkService` executes synthetic retrieval runs measuring:
  - **Precision@K**, **Recall@K**, **MRR**, and **NDCG@K** ($K \in \{1, 3, 5\}$).
  - P50, P95, and mean query latency profiling (confirming CPU latency < 50ms).
  - Database and architectural integrity audits (acyclic association verification, citation parentage checks, verification state machine compliance).
- Results persisted in `memory_evaluation_runs`.

## Consequences
- **Positive**: Realistic cognitive memory dynamics with recency decay, non-destructive episodic consolidation, safe compaction safeguards, and reproducible empirical benchmark verification.
- **Constraints**: Decay scoring operates dynamically during ranking without destructive automatic row deletion. Compaction execution strictly requires affirmative confirmation.
