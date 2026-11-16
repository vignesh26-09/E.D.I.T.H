# ADR 005: Phase B4 — Episodic and Procedural Memory Systems, Operational Telemetry, and Cross-Memory Links

## Status
Accepted and Implemented

## Context
With personal semantic memory established in Phase B3, autonomous systems require two additional temporal and operational cognitive memory systems:
1. **Episodic Memory**: A chronological ledger of discrete interaction events, tool executions, task milestones, system alerts, and multi-turn conversational sessions. It provides grounded temporal context and session-level clustering.
2. **Procedural Memory**: A structured repository of executable workflows, operational playbooks, and standardized multi-step routines. In addition to storing action steps, it tracks execution telemetry (success rates, durations, failure modes) to assess playbook reliability over time.
3. **Cross-Memory Links**: Associative relationships connecting episodic events (e.g. an incident or troubleshooting session) to the procedures executed during that session, and to the semantic memories or preferences derived from those experiences.

## Decisions

### 1. Episodic Event Storage & FTS5 Indexing
Authored schema `episodes` and external-content FTS5 virtual table `episodes_fts`:
- Captures `session_id`, `title`, `event_type` (`conversation`, `task_execution`, `observation`, `system_event`, `incident`), `occurred_at` (ISO 8601 timestamp), `duration_seconds`, `summary`, `narrative_detail`, `actors_json`, `context_tags_json`, `significance_score` (bounded $0.0 \le s \le 1.0$), and `metadata_json`.
- Synchronized FTS5 triggers (`trg_episodes_ai`, `trg_episodes_ad`, `trg_episodes_au`) index `title`, `summary`, and `narrative_detail`.
- Supports chronological filtering, significance cutoffs, session partitioning, and keyword search via `EpisodeTimelineRequest`.

### 2. Procedural Knowledge & Step Validation
Authored schema `procedures` and external-content FTS5 virtual table `procedures_fts`:
- Stores operational routines with `title`, `description`, `version` (semantic regex), `status` (`draft`, `active`, `deprecated`), `trigger_conditions_json`, `prerequisites_json`, `steps_json`, and telemetry aggregates (`execution_count`, `success_count`, `last_executed_at`).
- Enforces strict sequential step ordering starting at 1 (`step_number = 1, 2, ... N`) at both domain contract and service levels.
- Synchronized FTS5 triggers (`trg_procedures_ai`, `trg_procedures_ad`, `trg_procedures_au`) index `title`, `description`, and `trigger_conditions_json` for discovery when conditions or keywords match.

### 3. Execution Telemetry Tracking
Authored relational schema `procedure_execution_logs`:
- Logs discrete executions with `executed_at`, `execution_status` (`success`, `failure`, `aborted`, `partial`), `duration_seconds`, `execution_actor`, `step_results_json`, `error_message`, and `notes`.
- Atomic update triggers / transaction updates increment `execution_count` and `success_count`, computing live `success_rate` and recording `last_executed_at`.

### 4. Cross-Domain Memory Links
Authored relational schema `episodic_procedural_links`:
- Connects pairs of cognitive entities across domains (`episode_id`, `procedure_id`, `memory_id`).
- Supports canonical `link_type` enums (`executed_procedure`, `derived_memory`, `exemplar_episode`, `troubleshooting_context`).
- Enforces referential integrity with foreign key cascading deletes (`ON DELETE CASCADE`), ensuring links are automatically cleaned up when parent episodes, procedures, or memories are deleted.
- Enforces uniqueness via index `idx_epl_unique_link` on `(episode_id, procedure_id, memory_id, link_type)`.

### 5. Architectural Alignment & REST Endpoints
Preserved the 4-tier modular monolith architecture:
- Layer 1 (API): `/api/v1/episodes`, `/api/v1/episodes/timeline`, `/api/v1/episodes/sessions`, `/api/v1/episodes/{id}/links`, `/api/v1/procedures`, `/api/v1/procedures/search`, `/api/v1/procedures/{id}/execute`, `/api/v1/procedures/{id}/executions`, `/api/v1/procedures/{id}/status`.
- Layer 2 (Domain Services): `EpisodicService`, `ProceduralService`.
- Layer 3 (Repositories): `EpisodicRepository`, `ProceduralRepository`, `CrossMemoryLinkRepository`.
- Layer 4 (Storage Engine): SQLite with WAL, busy timeout, and native FTS5.

## Consequences
- **Positive**: Complete timeline observability of agent sessions and conversations; structured playbook execution with reliability tracking; transparent provenance between episodes, procedures, and personal memories.
- **Constraints**: Procedures must follow strict semantic step sequencing; cross-memory links require at least two entity references.
