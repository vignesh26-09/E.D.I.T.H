"""FastAPI dependency injection providers and security actor enforcement."""

from functools import lru_cache
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request, status

from edith_brain.core.config import Settings, get_settings
from edith_brain.core.contracts import ActorRole
from edith_brain.core.security import get_or_create_local_token, verify_local_token
from edith_brain.storage.db import SQLiteEngine
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.document_service import DocumentService
from edith_brain.services.episodic_service import EpisodicService
from edith_brain.services.procedural_service import ProceduralService
from edith_brain.services.memory_decay_engine import MemoryDecayEngine
from edith_brain.services.memory_consolidation_service import MemoryConsolidationService
from edith_brain.services.memory_compaction_service import MemoryCompactionService
from edith_brain.services.evaluation_benchmark_service import EvaluationBenchmarkService
from edith_brain.services.memory_conflict_engine import MemoryConflictEngine
from edith_brain.services.retrieval.retrieval_service import RetrievalService
from edith_brain.services.retrieval.memory_search_service import MemorySearchService
from edith_brain.services.retrieval.memory_embedding_service import MemoryEmbeddingService
from edith_brain.services.retrieval.embeddings import BaseEmbeddingProvider, get_embedding_provider


@lru_cache()
def get_engine() -> SQLiteEngine:
    """Provide a singleton SQLiteEngine instance."""
    settings = get_settings()
    return SQLiteEngine(db_path=settings.database_path, busy_timeout_ms=settings.sqlite_busy_timeout_ms)


@lru_cache()
def get_embedding_provider_dep() -> BaseEmbeddingProvider:
    """Provide a singleton EmbeddingProvider instance."""
    return get_embedding_provider()


def get_current_actor(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_edith_actor: Optional[str] = Header(None),
    settings: Settings = Depends(get_settings),
) -> ActorRole:
    """Validate bearer token and resolve caller trust boundary actor role."""
    # Exempt endpoints
    exempt_paths = {"/health", "/api/v1/health", "/docs", "/openapi.json"}
    if request.url.path in exempt_paths:
        return ActorRole.LOCAL_USER

    # When authentication is explicitly enabled
    if settings.auth_enabled:
        expected_token = get_or_create_local_token(
            token_path=settings.local_token_path,
            configured_secret=settings.local_auth_secret,
        )

        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: valid bearer token required in Authorization header.",
            )

        provided_token = authorization.split("Bearer ", 1)[1].strip()
        if not verify_local_token(provided_token, expected_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: invalid authentication token.",
            )

    # Actor role checks
    if x_edith_actor:
        actor_str = x_edith_actor.strip().upper()
        if actor_str == ActorRole.SYSTEM_PIPELINE.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="SYSTEM_PIPELINE actor role is restricted to internal service invocations and cannot be claimed via HTTP headers.",
            )
        if actor_str == ActorRole.TEST_HARNESS.value:
            if settings.environment != "test":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="TEST_HARNESS actor role is strictly prohibited outside test environment.",
                )
            return ActorRole.TEST_HARNESS

    return ActorRole.LOCAL_USER


def get_memory_service(
    engine: SQLiteEngine = Depends(get_engine),
) -> MemoryService:
    """Inject MemoryService instance."""
    return MemoryService(engine=engine)


def get_memory_conflict_engine(
    engine: SQLiteEngine = Depends(get_engine),
    embedding_provider: BaseEmbeddingProvider = Depends(get_embedding_provider_dep),
) -> MemoryConflictEngine:
    """Inject MemoryConflictEngine instance."""
    return MemoryConflictEngine(engine=engine, embedding_provider=embedding_provider)


def get_memory_search_service(
    engine: SQLiteEngine = Depends(get_engine),
    embedding_provider: BaseEmbeddingProvider = Depends(get_embedding_provider_dep),
) -> MemorySearchService:
    """Inject MemorySearchService instance."""
    return MemorySearchService(engine=engine, embedding_provider=embedding_provider)


def get_memory_embedding_service(
    engine: SQLiteEngine = Depends(get_engine),
    embedding_provider: BaseEmbeddingProvider = Depends(get_embedding_provider_dep),
) -> MemoryEmbeddingService:
    """Inject MemoryEmbeddingService instance."""
    return MemoryEmbeddingService(engine=engine, embedding_provider=embedding_provider)


def get_document_service(
    engine: SQLiteEngine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
    embedding_provider: BaseEmbeddingProvider = Depends(get_embedding_provider_dep),
) -> DocumentService:
    """Inject DocumentService instance."""
    return DocumentService(engine=engine, settings=settings, embedding_provider=embedding_provider)


def get_retrieval_service(
    engine: SQLiteEngine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
    embedding_provider: BaseEmbeddingProvider = Depends(get_embedding_provider_dep),
) -> RetrievalService:
    """Inject RetrievalService instance."""
    return RetrievalService(engine=engine, settings=settings, embedding_provider=embedding_provider)


def get_episodic_service(
    engine: SQLiteEngine = Depends(get_engine),
) -> EpisodicService:
    """Inject EpisodicService instance."""
    return EpisodicService(engine=engine)


def get_procedural_service(
    engine: SQLiteEngine = Depends(get_engine),
) -> ProceduralService:
    """Inject ProceduralService instance."""
    return ProceduralService(engine=engine)


def get_decay_engine(
    engine: SQLiteEngine = Depends(get_engine),
) -> MemoryDecayEngine:
    """Inject MemoryDecayEngine instance."""
    return MemoryDecayEngine(engine=engine)


def get_consolidation_service(
    engine: SQLiteEngine = Depends(get_engine),
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryConsolidationService:
    """Inject MemoryConsolidationService instance."""
    return MemoryConsolidationService(engine=engine, memory_service=memory_service)


def get_compaction_service(
    engine: SQLiteEngine = Depends(get_engine),
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryCompactionService:
    """Inject MemoryCompactionService instance."""
    return MemoryCompactionService(engine=engine, memory_service=memory_service)


def get_evaluation_benchmark_service(
    engine: SQLiteEngine = Depends(get_engine),
    memory_service: MemoryService = Depends(get_memory_service),
    search_service: MemorySearchService = Depends(get_memory_search_service),
) -> EvaluationBenchmarkService:
    """Inject EvaluationBenchmarkService instance."""
    return EvaluationBenchmarkService(engine=engine, memory_service=memory_service, search_service=search_service)
