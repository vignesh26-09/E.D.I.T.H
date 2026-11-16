"""API router for personal, semantic, episodic, and procedural memory lifecycle and intelligence."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCorrection,
    MemoryRevoke,
    MemoryPurge,
    MemoryResponse,
    MemoryAuditRecordResponse,
    MemoryCategory,
    PersonalSubcategory,
    MemoryStatus,
    VerificationStatus,
    ActorRole,
    MemoryVerifyRequest,
    MemoryVerificationResponse,
    MemoryCitationCreate,
    MemoryCitationResponse,
    MemoryAssociationCreate,
    MemoryAssociationResponse,
    MemoryConflictCheckRequest,
    MemoryConflictCheckResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    EmbeddingReindexRequest,
    EmbeddingReindexResponse,
    EmbeddingCutoverRequest,
    EmbeddingCutoverResponse,
)
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.memory_conflict_engine import MemoryConflictEngine
from edith_brain.services.retrieval.memory_search_service import MemorySearchService
from edith_brain.services.retrieval.memory_embedding_service import MemoryEmbeddingService
from edith_brain.api.deps import (
    get_memory_service,
    get_memory_conflict_engine,
    get_memory_search_service,
    get_memory_embedding_service,
    get_current_actor,
)

router = APIRouter(prefix="/memories", tags=["Memories"])


# ==========================================
# STATIC SEARCH, CONFLICT, & RE-INDEXING ROUTES
# (Must precede /{memory_id} routes)
# ==========================================

@router.post("/search", response_model=MemorySearchResponse)
def search_memories(
    payload: MemorySearchRequest,
    search_service: MemorySearchService = Depends(get_memory_search_service),
    actor: ActorRole = Depends(get_current_actor),
) -> MemorySearchResponse:
    """Search personal memories using Keyword, Semantic, or Hybrid RRF retrieval."""
    return search_service.search(payload)


@router.post("/check-conflicts", response_model=MemoryConflictCheckResponse)
def check_conflicts(
    payload: MemoryConflictCheckRequest,
    conflict_engine: MemoryConflictEngine = Depends(get_memory_conflict_engine),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryConflictCheckResponse:
    """Pre-flight conflict, duplicate, and contradiction inspection against active memories."""
    return conflict_engine.check_conflicts(payload)


@router.post("/reindex-embeddings", response_model=EmbeddingReindexResponse)
def reindex_embeddings(
    payload: EmbeddingReindexRequest,
    embedding_service: MemoryEmbeddingService = Depends(get_memory_embedding_service),
    actor: ActorRole = Depends(get_current_actor),
) -> EmbeddingReindexResponse:
    """Process a batch of unindexed active memories for a target embedding model."""
    return embedding_service.reindex_batch(payload)


@router.post("/cutover-active-model", response_model=EmbeddingCutoverResponse)
def cutover_active_model(
    payload: EmbeddingCutoverRequest,
    embedding_service: MemoryEmbeddingService = Depends(get_memory_embedding_service),
    actor: ActorRole = Depends(get_current_actor),
) -> EmbeddingCutoverResponse:
    """Perform atomic cutover to a target model after anti-join completeness verification."""
    return embedding_service.cutover_active_model(payload)


@router.get("/active-model", response_model=dict)
def get_active_model(
    embedding_service: MemoryEmbeddingService = Depends(get_memory_embedding_service),
    actor: ActorRole = Depends(get_current_actor),
) -> dict:
    """Retrieve active memory embedding model configuration."""
    return embedding_service.get_active_model_info()


# ==========================================
# CORE CRUD & LIFECYCLE ROUTES
# ==========================================

@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryResponse:
    """Store a structured memory (personal, semantic, episodic, procedural)."""
    return service.create_memory(payload)


@router.get("/{memory_id}", response_model=MemoryResponse)
def get_memory(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryResponse:
    """Retrieve memory by unique ID."""
    return service.get_memory(memory_id)


@router.post("/{memory_id}/correct", response_model=MemoryResponse)
def correct_memory(
    memory_id: str,
    payload: MemoryCorrection,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryResponse:
    """Correct a memory, preserving lineage and marking previous memory superseded."""
    return service.correct_memory(memory_id, payload)


@router.post("/{memory_id}/revoke", response_model=MemoryResponse)
def revoke_memory(
    memory_id: str,
    payload: MemoryRevoke,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryResponse:
    """Revoke/deactivate a memory while preserving non-sensitive audit history."""
    return service.revoke_memory(memory_id, payload)


@router.delete("/{memory_id}/purge", status_code=status.HTTP_200_OK)
def purge_memory(
    memory_id: str,
    payload: MemoryPurge,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> dict:
    """Permanently delete a memory and purge sensitive content from all audit snapshots."""
    return service.purge_memory(memory_id, payload)


@router.get("/{memory_id}/audit", response_model=list[MemoryAuditRecordResponse])
def get_memory_audit(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[MemoryAuditRecordResponse]:
    """Retrieve the audit log trail for a given memory."""
    return service.get_audit_trail(memory_id)


@router.get("", response_model=list[MemoryResponse])
def list_memories(
    category: Optional[MemoryCategory] = None,
    subcategory: Optional[str] = None,
    status_filter: Optional[MemoryStatus] = Query(default=MemoryStatus.ACTIVE, alias="status"),
    verification_status: Optional[VerificationStatus] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[MemoryResponse]:
    """List memories with category, subcategory, status, and verification filtering."""
    return service.list_memories(
        category=category,
        subcategory=subcategory,
        status=status_filter,
        verification_status=verification_status,
        limit=limit,
        offset=offset,
    )


# ==========================================
# VERIFICATION ROUTES
# ==========================================

@router.post("/{memory_id}/verify", response_model=MemoryResponse)
def verify_memory(
    memory_id: str,
    payload: MemoryVerifyRequest,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryResponse:
    """Transition memory verification status with state-machine validation and audit record."""
    return service.verify_memory(memory_id, payload, actor=actor)


@router.get("/{memory_id}/verifications", response_model=list[MemoryVerificationResponse])
def get_verification_history(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[MemoryVerificationResponse]:
    """Fetch immutable verification audit trail for a memory."""
    return service.get_verification_history(memory_id)


# ==========================================
# PROVENANCE CITATION ROUTES
# ==========================================

@router.post("/{memory_id}/citations", response_model=MemoryCitationResponse, status_code=status.HTTP_201_CREATED)
def add_citation(
    memory_id: str,
    payload: MemoryCitationCreate,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryCitationResponse:
    """Link memory to document or chunk provenance."""
    return service.add_citation(memory_id, payload)


@router.get("/{memory_id}/citations", response_model=list[MemoryCitationResponse])
def get_citations(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[MemoryCitationResponse]:
    """Retrieve all provenance citations for a memory."""
    return service.get_citations(memory_id)


# ==========================================
# ASSOCIATION GRAPH ROUTES
# ==========================================

@router.post("/{memory_id}/associations", response_model=MemoryAssociationResponse, status_code=status.HTTP_201_CREATED)
def add_association(
    memory_id: str,
    payload: MemoryAssociationCreate,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryAssociationResponse:
    """Create a directed or canonical relation edge between memories."""
    return service.add_association(memory_id, payload)


@router.get("/{memory_id}/associations", response_model=list[MemoryAssociationResponse])
def get_associations(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[MemoryAssociationResponse]:
    """Retrieve all incoming and outgoing associations for a memory."""
    return service.get_associations(memory_id)


@router.delete("/{memory_id}/associations/{assoc_id}", response_model=dict)
def delete_association(
    memory_id: str,
    assoc_id: str,
    service: MemoryService = Depends(get_memory_service),
    actor: ActorRole = Depends(get_current_actor),
) -> dict:
    """Remove a memory association edge."""
    return service.delete_association(assoc_id)
