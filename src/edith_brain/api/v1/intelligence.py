"""API router for memory intelligence: decay dynamics, episodic consolidation, and compaction."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from edith_brain.core.contracts import (
    MemoryTouchRequest,
    MemoryDecayScore,
    ConsolidationCandidateCreate,
    ConsolidationCandidateResponse,
    ConsolidationReviewAction,
    ConsolidationStatus,
    SessionConsolidationRequest,
    CompactionPlan,
    CompactionExecuteRequest,
    CompactionResult,
    PersonalSubcategory,
    ActorRole,
)
from edith_brain.services.memory_decay_engine import MemoryDecayEngine
from edith_brain.services.memory_consolidation_service import MemoryConsolidationService
from edith_brain.services.memory_compaction_service import MemoryCompactionService
from edith_brain.api.deps import (
    get_decay_engine,
    get_consolidation_service,
    get_compaction_service,
    get_current_actor,
)

router = APIRouter(prefix="/intelligence", tags=["Memory Intelligence"])


# ==========================================
# DECAY & TELEMETRY ENDPOINTS
# ==========================================

@router.post("/touch", response_model=dict)
def touch_memories(
    payload: MemoryTouchRequest,
    decay_engine: MemoryDecayEngine = Depends(get_decay_engine),
    actor: ActorRole = Depends(get_current_actor),
) -> dict:
    """Record access/retrieval touch on a set of memories, updating telemetry without mutating content."""
    count = decay_engine.touch_memories(payload.memory_ids)
    return {"touched_count": count, "memory_ids": payload.memory_ids}


@router.get("/decay/{memory_id}", response_model=MemoryDecayScore)
def get_memory_decay_score(
    memory_id: str,
    decay_engine: MemoryDecayEngine = Depends(get_decay_engine),
    actor: ActorRole = Depends(get_current_actor),
) -> MemoryDecayScore:
    """Evaluate recency decay and combined relevance score for a memory."""
    score = decay_engine.get_decay_evaluation(memory_id)
    if not score:
        from edith_brain.core.exceptions import NotFoundError
        raise NotFoundError(f"Memory with ID '{memory_id}' not found.")
    return score


# ==========================================
# CONSOLIDATION ENDPOINTS
# ==========================================

@router.post("/consolidations/session", response_model=list[ConsolidationCandidateResponse])
def consolidate_session(
    payload: SessionConsolidationRequest,
    service: MemoryConsolidationService = Depends(get_consolidation_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[ConsolidationCandidateResponse]:
    """Scan an episodic session, extracting candidate personal facts and preferences."""
    return service.consolidate_session_episodes(
        session_id=payload.session_id,
        min_significance=payload.min_significance,
    )


@router.post("/consolidations", response_model=ConsolidationCandidateResponse, status_code=status.HTTP_201_CREATED)
def create_consolidation_candidate(
    payload: ConsolidationCandidateCreate,
    service: MemoryConsolidationService = Depends(get_consolidation_service),
    actor: ActorRole = Depends(get_current_actor),
) -> ConsolidationCandidateResponse:
    """Propose a new prospective fact candidate distilled from episodic interaction."""
    return service.create_candidate(payload)


@router.get("/consolidations", response_model=list[ConsolidationCandidateResponse])
def list_consolidation_candidates(
    session_id: Optional[str] = Query(None),
    status_filter: Optional[ConsolidationStatus] = Query(None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    service: MemoryConsolidationService = Depends(get_consolidation_service),
    actor: ActorRole = Depends(get_current_actor),
) -> list[ConsolidationCandidateResponse]:
    """List consolidation candidates with session or review status filtering."""
    return service.list_candidates(session_id=session_id, status=status_filter, limit=limit)


@router.post("/consolidations/{candidate_id}/review", response_model=ConsolidationCandidateResponse)
def review_consolidation_candidate(
    candidate_id: str,
    payload: ConsolidationReviewAction,
    service: MemoryConsolidationService = Depends(get_consolidation_service),
    actor: ActorRole = Depends(get_current_actor),
) -> ConsolidationCandidateResponse:
    """Approve or reject a candidate. If approved, creates active personal memory with derived link."""
    return service.review_candidate(candidate_id=candidate_id, action=payload, reviewer=actor.value)


# ==========================================
# COMPACTION ENDPOINTS
# ==========================================

@router.get("/compaction/plan", response_model=CompactionPlan)
def generate_compaction_plan(
    subcategory: Optional[PersonalSubcategory] = Query(None),
    similarity_threshold: float = Query(default=0.65, ge=0.1, le=1.0),
    service: MemoryCompactionService = Depends(get_compaction_service),
    actor: ActorRole = Depends(get_current_actor),
) -> CompactionPlan:
    """Inspect active memories and generate an advisory deduplication/compaction plan."""
    return service.analyze_compaction_opportunities(
        subcategory=subcategory,
        similarity_threshold=similarity_threshold,
    )


@router.post("/compaction/execute", response_model=CompactionResult)
def execute_compaction(
    payload: CompactionExecuteRequest,
    service: MemoryCompactionService = Depends(get_compaction_service),
    actor: ActorRole = Depends(get_current_actor),
) -> CompactionResult:
    """Execute or dry-run a compaction plan with explicit confirmation safeguard."""
    effective_plan = payload.plan or service.analyze_compaction_opportunities()
    return service.execute_compaction(plan=effective_plan, request=payload)
