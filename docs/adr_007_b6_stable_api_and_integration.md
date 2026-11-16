# ADR 007: Phase B6 — Stable API, Client SDK, and Integration Readiness

## Status
Accepted and Implemented

## Context
With all core cognitive subsystems complete—document ingestion (B1), hybrid retrieval (B2), personal memory with provenance and verification (B3), episodic timelines and procedural telemetry (B4), and memory intelligence decay and benchmarking (B5)—Phase B6 establishes the external integration layer:
1. Providing a clean, idiomatic, strongly-typed Python SDK for client applications, autonomous agents, and CLI tools.
2. Freezing the API specification via static OpenAPI 3.1 export.
3. Providing end-to-end multi-domain workflow integration test validation.
4. Hardening local service execution on Windows 11 with standardized launcher scripts.

## Decisions

### 1. Unified Python Client SDK (`EdithBrainClient`)
Authored [src/edith_brain/client.py](file:///D:/edith-brain-core/src/edith_brain/client.py):
- Built on top of `httpx`, supporting both standard HTTP endpoints and direct in-memory ASGI dispatch (`httpx.ASGITransport(app=app)`) for zero-overhead test execution.
- Typed interface returning validated Pydantic models from `edith_brain.core.contracts`.
- Comprehensive coverage across all subsystems:
  - System diagnostics (`get_health`, `get_system_info`).
  - Document management (`upload_document`, `get_document_chunks`, `delete_document`).
  - Hybrid RAG search (`search_knowledge`).
  - Personal memory (`create_memory`, `correct_memory`, `revoke_memory`, `purge_memory`, `verify_memory`, `add_citation`, `add_association`, `check_conflicts`, `search_memories`).
  - Episodic memory (`create_episode`, `get_timeline`, `list_sessions`, `link_episode`).
  - Procedural memory (`create_procedure`, `search_procedures`, `log_execution`, `update_procedure_status`).
  - Memory intelligence (`touch_memories`, `get_decay_score`, `consolidate_session`, `review_consolidation`, `get_compaction_plan`, `execute_compaction`).
  - Benchmark evaluation (`run_benchmark`).

### 2. Static OpenAPI Specification
Authored [scripts/export_openapi.py](file:///D:/edith-brain-core/scripts/export_openapi.py):
- Generates a 211 KB, complete OpenAPI 3.1 schema saved at [docs/openapi.json](file:///D:/edith-brain-core/docs/openapi.json).
- Serves as the authoritative API contract for client SDK generation and integration review.

### 3. Production Windows 11 Launchers
Authored standard local service execution scripts:
- [scripts/start_server.ps1](file:///D:/edith-brain-core/scripts/start_server.ps1): PowerShell script with parameter binding (`HostAddress`, `Port`, `Reload`), Python runtime verification, and PYTHONPATH resolution.
- [scripts/start_server.bat](file:///D:/edith-brain-core/scripts/start_server.bat): Command prompt batch launcher.

### 4. End-to-End System Verification
- Created [tests/integration/test_client_sdk.py](file:///D:/edith-brain-core/tests/integration/test_client_sdk.py) validating SDK functionality across all domains.
- Created [tests/integration/test_e2e_workflow.py](file:///D:/edith-brain-core/tests/integration/test_e2e_workflow.py) executing a unified multi-domain user workflow (document ingestion -> hybrid search -> personal memory creation citing chunk -> verification -> procedural playbook registration -> episodic logging -> cross-domain linking -> decay telemetry -> compaction -> benchmark execution).

## Consequences
- **Positive**: External callers and autonomous agents can consume E.D.I.T.H. Brain Core without writing raw HTTP requests or inspecting SQLite databases directly; 100% of API endpoints are covered by typed contracts; and service lifecycle is reproducible on Windows 11.
- **Constraints**: Local trust boundary requires client processes to run on the local machine (`127.0.0.1`) and supply the local bearer token when authentication is active.
