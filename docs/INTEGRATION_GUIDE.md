# E.D.I.T.H. Brain Core — Integration & Developer Guide

This guide describes how external autonomous agents, client applications, and background workers integrate with the **E.D.I.T.H. Brain Core** service on Windows 11.

---

## 1. System Overview & Trust Boundary

E.D.I.T.H. Brain Core is a high-performance, local-first cognitive memory and knowledge engine. It provides:
- **Knowledge Documents (B1/B2)**: Multi-format parsing (PDF, MD, TXT, DOCX), structure-aware chunking, FTS5 BM25 search, and dense vector embeddings.
- **Personal Memory (B3)**: First-class verifiable facts, preferences, goals, and skills with provenance citations and acyclic association graphs.
- **Episodic & Procedural Memory (B4)**: Chronological event timeline ledger and repeatable operational playbooks with live success-rate telemetry.
- **Memory Intelligence (B5)**: Exponential half-life decay, episodic fact consolidation, near-duplicate compaction, and empirical evaluation benchmarks.

### Local Trust Boundary
- By default, the Brain Core binds exclusively to the loopback interface (`127.0.0.1:8000`).
- When authentication is enabled (`AUTH_ENABLED=true`), all requests must supply a Bearer token matching `data/.edith_token`.
- Health diagnostics (`/api/v1/health`, `/health`) and OpenAPI docs (`/docs`) are exempted from authentication for local health monitors.

---

## 2. Quickstart: Using the Python Client SDK

Install the local package into your Python environment:
```powershell
cd D:\edith-brain-core
python -m pip install -e .
```

### Initializing the Client
```python
from edith_brain.client import EdithBrainClient

# Connect to local Brain Core instance
client = EdithBrainClient(base_url="http://127.0.0.1:8000")

# Check system status
health = client.get_health()
print(f"Status: {health.status}, WAL Mode: {health.wal_mode}")
```

---

## 3. Core Integration Patterns

### Pattern A: Document Ingestion & Hybrid RAG Retrieval
```python
from edith_brain.core.contracts import RetrievalQuery, RetrievalMode

# 1. Ingest a knowledge document
doc = client.upload_document(
    file_path="docs/architecture_spec.md",
    title="Core Architecture Spec",
    tags=["architecture", "documentation"]
)
print(f"Ingested document: {doc.id} with status: {doc.status}")

# 2. Retrieve relevant chunks using hybrid search (FTS5 BM25 + Cosine Similarity)
results = client.search_knowledge(
    RetrievalQuery(
        query="SQLite WAL mode concurrency",
        mode=RetrievalMode.HYBRID,
        top_k=5
    )
)

for item in results.results:
    print(f"Score: {item.score:.4f} | Chunk: {item.chunk_text[:100]}...")
```

---

### Pattern B: Personal Memory with Grounded Citations & Verification
```python
from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCategory,
    PersonalSubcategory,
    MemoryCitationCreate,
    MemoryVerifyRequest,
    VerificationStatus,
    VerificationMethod,
    MemoryConflictCheckRequest,
)

# 1. Pre-flight advisory conflict analysis before creating memory
conflict_report = client.check_conflicts(
    MemoryConflictCheckRequest(
        category=MemoryCategory.PERSONAL,
        subcategory=PersonalSubcategory.PREFERENCE,
        content="User prefers light theme for coding.",
    )
)
if conflict_report.has_conflicts:
    print(f"Warning: {conflict_report.highest_severity_conflict.value}")

# 2. Create personal memory
mem = client.create_memory(
    MemoryCreate(
        category=MemoryCategory.PERSONAL,
        subcategory=PersonalSubcategory.PREFERENCE,
        content="User prefers dark theme with high contrast accents.",
    )
)

# 3. Attach provenance citation linking memory to source document chunk
client.add_citation(
    memory_id=mem.id,
    citation=MemoryCitationCreate(
        document_id=doc.id,
        chunk_id=item.chunk_id,
        quote_text="User prefers dark theme with high contrast accents."
    )
)

# 4. Confirm verification status
verified_mem = client.verify_memory(
    memory_id=mem.id,
    verify_req=MemoryVerifyRequest(
        status=VerificationStatus.VERIFIED,
        method=VerificationMethod.USER_CONFIRMED,
        notes="Explicitly confirmed during setup interview",
    )
)
```

---

### Pattern C: Episodic Interaction Logging & Playbook Execution
```python
from edith_brain.core.contracts import (
    EpisodeCreate,
    EpisodeTimelineRequest,
    EventType,
    ProcedureCreate,
    ProcedureStep,
    ProcedureExecutionLogCreate,
    EpisodeLinkCreate,
)

# 1. Log an interaction episode
episode = client.create_episode(
    EpisodeCreate(
        session_id="session-user-101",
        title="Diagnostic Conversation",
        event_type=EventType.TASK_EXECUTION,
        summary="User instructed agent to verify system diagnostics.",
        significance_score=0.85,
    )
)

# 2. Register an operational procedure playbook
playbook = client.create_procedure(
    ProcedureCreate(
        title="Disk Space Remediation Routine",
        description="Verify free disk space and clean temporary files.",
        trigger_conditions=["Free disk space < 5GB"],
        steps=[
            ProcedureStep(step_number=1, action="Check free disk space with PRAGMA"),
            ProcedureStep(step_number=2, action="Purge orphaned temporary files"),
        ],
        version="1.0.0",
    )
)

# 3. Log playbook execution telemetry
client.log_execution(
    procedure_id=playbook.id,
    log=ProcedureExecutionLogCreate(
        execution_status="success",
        duration_seconds=0.15,
        notes="All cleanup steps succeeded.",
    )
)

# 4. Link episode to the executed procedure
client.link_episode(
    episode_id=episode.id,
    link=EpisodeLinkCreate(
        procedure_id=playbook.id,
        link_type="executed_procedure",
    )
)
```

---

### Pattern D: Memory Intelligence & Compaction
```python
from edith_brain.core.contracts import CompactionExecuteRequest

# 1. Touch memories on access to update recency telemetry
client.touch_memories([mem.id])

# 2. Inspect recency decay score
decay_info = client.get_decay_score(mem.id)
print(f"Decayed Score: {decay_info.decay_score}, Access Count: {decay_info.access_count}")

# 3. Preview compaction opportunities
plan = client.get_compaction_plan(subcategory="preference", threshold=0.65)
print(f"Identified {plan.redundant_memories_identified} redundant memories.")

# 4. Execute confirmed compaction
if plan.clusters:
    result = client.execute_compaction(
        CompactionExecuteRequest(dry_run=False, confirmed=True, plan=plan)
    )
    print(result.message)
```

---

## 4. Running the Service in Production on Windows 11

### Option 1: PowerShell Script
```powershell
.\scripts\start_server.ps1 -Port 8000
```

### Option 2: Batch Launcher
```cmd
scripts\start_server.bat
```

### Option 3: Python Module Execution
```powershell
python -m uvicorn edith_brain.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

---

## 5. OpenAPI Specification Export

To export or refresh the static OpenAPI 3.1 specification:
```powershell
python scripts\export_openapi.py
```
The resulting specification is stored in [docs/openapi.json](file:///D:/edith-brain-core/docs/openapi.json).
Interactive Swagger UI is accessible at `http://127.0.0.1:8000/docs` and ReDoc at `http://127.0.0.1:8000/redoc`.
