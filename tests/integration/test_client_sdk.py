"""Integration tests for EdithBrainClient Python SDK."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from edith_brain.client import EdithBrainClient
from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCategory,
    PersonalSubcategory,
    MemoryCorrection,
    MemoryConflictCheckRequest,
    MemorySearchRequest,
    RetrievalQuery,
    EpisodeCreate,
    EpisodeTimelineRequest,
    EventType,
    ProcedureCreate,
    ProcedureStep,
    ProcedureExecutionLogCreate,
    BenchmarkRunRequest,
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
def sdk_client(
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
    """Instantiate EdithBrainClient wired directly to in-process FastAPI app."""
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


def test_sdk_health_and_system(sdk_client: EdithBrainClient):
    """Test health and system info methods via SDK."""
    health = sdk_client.get_health()
    assert health.status == "healthy"
    assert health.wal_mode is True

    sys_info = sdk_client.get_system_info()
    assert "personal" in sys_info.supported_memory_categories
    assert sys_info.fts5_supported is True


def test_sdk_memory_lifecycle_and_conflicts(sdk_client: EdithBrainClient):
    """Test full memory lifecycle via SDK."""
    # 1. Create memory
    mem = sdk_client.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="User prefers Python for data engineering pipelines.",
        )
    )
    assert mem.id is not None
    assert mem.content == "User prefers Python for data engineering pipelines."

    # 2. Pre-flight conflict check
    conflict_report = sdk_client.check_conflicts(
        MemoryConflictCheckRequest(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="User prefers Python for data engineering pipelines.",
        )
    )
    assert conflict_report.has_conflicts is True
    assert conflict_report.highest_severity_conflict.value == "potential_duplicate"

    # 3. Correct memory
    corrected = sdk_client.correct_memory(
        memory_id=mem.id,
        correction=MemoryCorrection(
            new_content="User prefers Python and SQL for data engineering pipelines.",
            reason="User clarified dual language preference",
        ),
    )
    assert corrected.id != mem.id
    assert corrected.parent_memory_id == mem.id

    # 4. Search memories
    search_res = sdk_client.search_memories(
        MemorySearchRequest(query="data engineering")
    )
    assert search_res.total_results >= 1


def test_sdk_episodic_and_procedural_flows(sdk_client: EdithBrainClient):
    """Test episodic and procedural flows via SDK."""
    # 1. Create episodic event
    episode = sdk_client.create_episode(
        EpisodeCreate(
            session_id="sdk-session-1",
            title="SDK Test Session",
            event_type=EventType.TASK_EXECUTION,
            summary="Tested SDK client methods.",
            significance_score=0.75,
        )
    )
    assert episode.id is not None

    # 2. Query timeline
    timeline = sdk_client.get_timeline(
        EpisodeTimelineRequest(session_id="sdk-session-1")
    )
    assert len(timeline) == 1

    # 3. Create procedure
    proc = sdk_client.create_procedure(
        ProcedureCreate(
            title="SDK Playbook",
            description="Playbook created via SDK",
            trigger_conditions=["SDK test triggered"],
            steps=[ProcedureStep(step_number=1, action="Verify SDK initialization")],
        )
    )
    assert proc.id is not None

    # 4. Log procedure execution
    log = sdk_client.log_execution(
        procedure_id=proc.id,
        log=ProcedureExecutionLogCreate(
            execution_status="success",
            duration_seconds=0.08,
            notes="SDK execution test passed",
        ),
    )
    assert log.id is not None
    assert log.execution_status == "success"


def test_sdk_intelligence_and_evaluation(sdk_client: EdithBrainClient):
    """Test intelligence decay, touch, and benchmark execution via SDK."""
    # 1. Create a memory
    mem = sdk_client.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.GOAL,
            content="Complete Phase B6 integration readiness testing.",
        )
    )

    # 2. Touch memory
    touch_res = sdk_client.touch_memories([mem.id])
    assert touch_res["touched_count"] == 1

    # 3. Check decay score
    decay_score = sdk_client.get_decay_score(mem.id)
    assert decay_score.access_count >= 1
    assert decay_score.effective_score > 0.0

    # 4. Run evaluation benchmark
    benchmark_report = sdk_client.run_benchmark(
        BenchmarkRunRequest(run_type="full", k_values=[1, 3])
    )
    assert benchmark_report.run_id is not None
    assert benchmark_report.retrieval_metrics.mrr > 0.0
    assert benchmark_report.integrity_metrics.citation_parentage_accuracy == 1.0
