"""End-to-end multi-domain workflow integration test across Phases B0-B6."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from edith_brain.client import EdithBrainClient
from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCategory,
    PersonalSubcategory,
    MemoryCitationCreate,
    MemoryVerifyRequest,
    VerificationStatus,
    VerificationMethod,
    EpisodeCreate,
    EpisodeLinkCreate,
    EventType,
    ProcedureCreate,
    ProcedureStep,
    ProcedureExecutionLogCreate,
    CompactionExecuteRequest,
    BenchmarkRunRequest,
    RetrievalQuery,
)
from edith_brain.core.config import Settings
from edith_brain.storage.db import SQLiteEngine
from edith_brain.api.app import create_app
from edith_brain.api.deps import (
    get_settings,
    get_engine,
    get_memory_service,
    get_document_service,
    get_retrieval_service,
    get_episodic_service,
    get_procedural_service,
    get_decay_engine,
    get_consolidation_service,
    get_compaction_service,
    get_evaluation_benchmark_service,
    get_embedding_provider_dep,
)
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.document_service import DocumentService
from edith_brain.services.retrieval.retrieval_service import RetrievalService
from edith_brain.services.episodic_service import EpisodicService
from edith_brain.services.procedural_service import ProceduralService
from edith_brain.services.memory_decay_engine import MemoryDecayEngine
from edith_brain.services.memory_consolidation_service import MemoryConsolidationService
from edith_brain.services.memory_compaction_service import MemoryCompactionService
from edith_brain.services.evaluation_benchmark_service import EvaluationBenchmarkService
from edith_brain.services.retrieval.embeddings import BaseEmbeddingProvider


@pytest.fixture
def e2e_client(
    test_settings: Settings,
    test_engine: SQLiteEngine,
    memory_service: MemoryService,
    document_service: DocumentService,
    retrieval_service: RetrievalService,
    episodic_service: EpisodicService,
    procedural_service: ProceduralService,
    decay_engine: MemoryDecayEngine,
    consolidation_service: MemoryConsolidationService,
    compaction_service: MemoryCompactionService,
    evaluation_benchmark_service: EvaluationBenchmarkService,
    test_embedding_provider: BaseEmbeddingProvider,
) -> EdithBrainClient:
    app = create_app()

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_engine] = lambda: test_engine
    app.dependency_overrides[get_memory_service] = lambda: memory_service
    app.dependency_overrides[get_document_service] = lambda: document_service
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval_service
    app.dependency_overrides[get_episodic_service] = lambda: episodic_service
    app.dependency_overrides[get_procedural_service] = lambda: procedural_service
    app.dependency_overrides[get_decay_engine] = lambda: decay_engine
    app.dependency_overrides[get_consolidation_service] = lambda: consolidation_service
    app.dependency_overrides[get_compaction_service] = lambda: compaction_service
    app.dependency_overrides[get_evaluation_benchmark_service] = lambda: evaluation_benchmark_service
    app.dependency_overrides[get_embedding_provider_dep] = lambda: test_embedding_provider

    with TestClient(app) as test_client:
        client = EdithBrainClient(http_client=test_client)
        yield client
    app.dependency_overrides.clear()


def test_full_system_lifecycle_e2e(e2e_client: EdithBrainClient, tmp_path: Path):
    """Execute complete end-to-end multi-domain workflow."""
    # -------------------------------------------------------------
    # Step 1: Ingest Knowledge Document
    # -------------------------------------------------------------
    doc_file = tmp_path / "system_architecture.md"
    doc_file.write_text(
        "# EDITH System Architecture\n\n"
        "The cognitive core is built as a local modular monolith using SQLite WAL mode.\n"
        "All procedures enforce sequential steps and personal preferences decay gracefully.\n",
        encoding="utf-8",
    )
    doc_res = e2e_client.upload_document(
        file_path=doc_file,
        title="EDITH Architecture Spec",
        tags=["architecture", "spec"],
    )
    assert doc_res.id is not None
    chunks = e2e_client.get_document_chunks(doc_res.id)
    assert len(chunks) >= 1
    cited_chunk = chunks[0]

    # -------------------------------------------------------------
    # Step 2: Hybrid Retrieval Search
    # -------------------------------------------------------------
    search_res = e2e_client.search_knowledge(
        RetrievalQuery(query="modular monolith SQLite", top_k=3)
    )
    assert search_res.total_results >= 1

    # -------------------------------------------------------------
    # Step 3: Create Personal Memory & Link Provenance Citation
    # -------------------------------------------------------------
    mem_res = e2e_client.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="User prefers modular monolith architectures over distributed microservices.",
        )
    )
    citation = e2e_client.add_citation(
        memory_id=mem_res.id,
        citation=MemoryCitationCreate(
            document_id=doc_res.id,
            chunk_id=cited_chunk.id,
            quote_text="The cognitive core is built as a local modular monolith using SQLite WAL mode.",
        ),
    )
    assert citation.id is not None
    assert citation.citation_status.value == "valid"

    # Transition verification status: unverified -> verified
    verified_mem = e2e_client.verify_memory(
        memory_id=mem_res.id,
        verify_req=MemoryVerifyRequest(
            status=VerificationStatus.VERIFIED,
            method=VerificationMethod.USER_CONFIRMED,
            notes="Confirmed user preference from architecture design review",
        ),
    )
    assert verified_mem.verification_status.value == "verified"

    # -------------------------------------------------------------
    # Step 4: Register Operational Procedural Playbook
    # -------------------------------------------------------------
    proc_res = e2e_client.create_procedure(
        ProcedureCreate(
            title="Database Backup Routine",
            description="Run SQLite VACUUM backup and verify checksums.",
            trigger_conditions=["Daily schedule", "Manual maintenance trigger"],
            steps=[
                ProcedureStep(step_number=1, action="PRAGMA integrity_check;"),
                ProcedureStep(step_number=2, action="VACUUM INTO 'backup.db';"),
            ],
            version="1.0.0",
        )
    )
    assert proc_res.id is not None

    # Log successful execution
    exec_log = e2e_client.log_execution(
        procedure_id=proc_res.id,
        log=ProcedureExecutionLogCreate(
            execution_status="success",
            duration_seconds=0.25,
            notes="Integrity check passed; backup written.",
        ),
    )
    assert exec_log.execution_status == "success"

    # -------------------------------------------------------------
    # Step 5: Log Episodic Event & Create Cross-Domain Links
    # -------------------------------------------------------------
    ep_res = e2e_client.create_episode(
        EpisodeCreate(
            session_id="e2e-session-100",
            title="Nightly Maintenance Run",
            event_type=EventType.TASK_EXECUTION,
            summary="Successfully ran Database Backup Routine and verified storage.",
            significance_score=0.8,
        )
    )
    assert ep_res.id is not None

    # Link Episode -> Procedure
    link_proc = e2e_client.link_episode(
        episode_id=ep_res.id,
        link=EpisodeLinkCreate(
            procedure_id=proc_res.id,
            link_type="executed_procedure",
        ),
    )
    assert link_proc.id is not None

    # Link Episode -> Semantic Memory
    link_mem = e2e_client.link_episode(
        episode_id=ep_res.id,
        link=EpisodeLinkCreate(
            memory_id=mem_res.id,
            link_type="derived_memory",
        ),
    )
    assert link_mem.id is not None

    # -------------------------------------------------------------
    # Step 6: Memory Intelligence (Touch, Decay, Compaction)
    # -------------------------------------------------------------
    e2e_client.touch_memories([mem_res.id])
    decay = e2e_client.get_decay_score(mem_res.id)
    assert decay.access_count == 1
    assert decay.effective_score > 0.0

    # Compaction dry run preview
    compaction_res = e2e_client.execute_compaction(
        CompactionExecuteRequest(dry_run=True, confirmed=False)
    )
    assert compaction_res.dry_run is True

    # -------------------------------------------------------------
    # Step 7: Empirical Benchmark Execution
    # -------------------------------------------------------------
    benchmark = e2e_client.run_benchmark(
        BenchmarkRunRequest(run_type="full", k_values=[1, 3])
    )
    assert benchmark.run_id is not None
    assert benchmark.retrieval_metrics.mrr > 0.0
    assert benchmark.integrity_metrics.citation_parentage_accuracy == 1.0
