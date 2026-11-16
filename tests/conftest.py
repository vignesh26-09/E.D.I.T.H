"""Pytest test configuration and fixtures."""

import os
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient

from edith_brain.core.config import Settings
from edith_brain.storage.db import SQLiteEngine
from edith_brain.storage.migrations import MigrationRunner
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.document_service import DocumentService
from edith_brain.services.retrieval.retrieval_service import RetrievalService
from edith_brain.services.episodic_service import EpisodicService
from edith_brain.services.procedural_service import ProceduralService
from edith_brain.services.memory_decay_engine import MemoryDecayEngine
from edith_brain.services.memory_consolidation_service import MemoryConsolidationService
from edith_brain.services.memory_compaction_service import MemoryCompactionService
from edith_brain.services.evaluation_benchmark_service import EvaluationBenchmarkService
from edith_brain.services.retrieval.embeddings import BaseEmbeddingProvider, DeterministicEmbeddingProvider
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


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Generate isolated Settings pointing to temporary directories."""
    settings = Settings(
        app_name="E.D.I.T.H. Brain Core [Test]",
        environment="test",
        base_dir=tmp_path,
        database_path=tmp_path / "test_brain.db",
        storage_raw_dir=tmp_path / "raw",
        storage_extracted_dir=tmp_path / "extracted",
        max_file_size_bytes=1024 * 1024,  # 1 MB for testing
        sqlite_busy_timeout_ms=3000,
        embedding_provider="deterministic",
        embedding_dimensions=384,
        auth_enabled=False,
    )
    settings.ensure_directories()
    return settings


@pytest.fixture
def test_engine(test_settings: Settings) -> SQLiteEngine:
    """Provide initialized SQLite engine with all baseline migrations applied."""
    engine = SQLiteEngine(
        db_path=test_settings.database_path,
        busy_timeout_ms=test_settings.sqlite_busy_timeout_ms,
    )
    runner = MigrationRunner(engine=engine)
    runner.run_migrations()
    return engine


@pytest.fixture
def test_embedding_provider() -> BaseEmbeddingProvider:
    """Provide deterministic, local embedding provider for tests."""
    return DeterministicEmbeddingProvider(dimensions=384)


@pytest.fixture
def memory_service(test_engine: SQLiteEngine) -> MemoryService:
    """Provide isolated MemoryService."""
    return MemoryService(engine=test_engine)


@pytest.fixture
def document_service(
    test_engine: SQLiteEngine,
    test_settings: Settings,
    test_embedding_provider: BaseEmbeddingProvider,
) -> DocumentService:
    """Provide isolated DocumentService."""
    return DocumentService(
        engine=test_engine,
        settings=test_settings,
        embedding_provider=test_embedding_provider,
    )


@pytest.fixture
def retrieval_service(
    test_engine: SQLiteEngine,
    test_settings: Settings,
    test_embedding_provider: BaseEmbeddingProvider,
) -> RetrievalService:
    """Provide isolated RetrievalService."""
    return RetrievalService(
        engine=test_engine,
        settings=test_settings,
        embedding_provider=test_embedding_provider,
    )


@pytest.fixture
def episodic_service(test_engine: SQLiteEngine) -> EpisodicService:
    """Provide isolated EpisodicService."""
    return EpisodicService(engine=test_engine)


@pytest.fixture
def procedural_service(test_engine: SQLiteEngine) -> ProceduralService:
    """Provide isolated ProceduralService."""
    return ProceduralService(engine=test_engine)


@pytest.fixture
def decay_engine(test_engine: SQLiteEngine) -> MemoryDecayEngine:
    """Provide isolated MemoryDecayEngine."""
    return MemoryDecayEngine(engine=test_engine)


@pytest.fixture
def consolidation_service(test_engine: SQLiteEngine, memory_service: MemoryService) -> MemoryConsolidationService:
    """Provide isolated MemoryConsolidationService."""
    return MemoryConsolidationService(engine=test_engine, memory_service=memory_service)


@pytest.fixture
def compaction_service(test_engine: SQLiteEngine, memory_service: MemoryService) -> MemoryCompactionService:
    """Provide isolated MemoryCompactionService."""
    return MemoryCompactionService(engine=test_engine, memory_service=memory_service)


@pytest.fixture
def evaluation_benchmark_service(test_engine: SQLiteEngine, memory_service: MemoryService) -> EvaluationBenchmarkService:
    """Provide isolated EvaluationBenchmarkService."""
    return EvaluationBenchmarkService(engine=test_engine, memory_service=memory_service)


@pytest.fixture
def client(
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
) -> Generator[TestClient, None, None]:
    """Provide FastAPI test client with dependency overrides pointing to test fixtures."""
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
        yield test_client

    app.dependency_overrides.clear()
