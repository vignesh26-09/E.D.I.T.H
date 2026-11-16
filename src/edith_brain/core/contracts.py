"""Domain data contracts and Pydantic v2 validation models."""

from enum import Enum
from typing import Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator


class SearchMode(str, Enum):
    """Retrieval search mode."""
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class MemoryCategory(str, Enum):
    """Primary categorization of memories."""
    PERSONAL = "personal"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


class PersonalSubcategory(str, Enum):
    """Subcategories specifically for personal memory."""
    PROFILE_FACT = "profile_fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    SKILL = "skill"
    PROJECT_CONTEXT = "project_context"
    DECISION = "decision"


class MemoryStatus(str, Enum):
    """Lifecycle state of a memory."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class VerificationStatus(str, Enum):
    """Explicit verification state of a memory."""
    UNVERIFIED = "unverified"
    NEEDS_REVIEW = "needs_review"
    VERIFIED = "verified"
    REJECTED = "rejected"


class VerificationMethod(str, Enum):
    """Authority/method under which a memory was verified."""
    USER_CONFIRMED = "user_confirmed"
    DOCUMENT_SUPPORTED = "document_supported"
    EXTERNALLY_VERIFIED = "externally_verified"
    SYSTEM_INFERRED = "system_inferred"


class ActorRole(str, Enum):
    """Trust boundary actor role."""
    LOCAL_USER = "LOCAL_USER"
    SYSTEM_PIPELINE = "SYSTEM_PIPELINE"
    TEST_HARNESS = "TEST_HARNESS"


class RelationType(str, Enum):
    """Directional or canonical relations between memories."""
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    RELATES_TO = "relates_to"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"


class CitationStatus(str, Enum):
    """Availability status of cited knowledge source."""
    VALID = "valid"
    SOURCE_REMOVED = "source_removed"


class ConflictType(str, Enum):
    """Classification of potential memory overlap/conflict."""
    POTENTIAL_DUPLICATE = "potential_duplicate"
    POTENTIAL_CONTRADICTION = "potential_contradiction"
    RELATED_ACTIVE = "related_active"
    NO_CONFLICT_DETECTED = "no_conflict_detected"


class SourceType(str, Enum):
    """Origin/provenance of a memory."""
    USER_EXPLICIT = "user_explicit"
    INFERRED = "inferred"
    DOCUMENT_EXTRACT = "document_extract"
    SYSTEM = "system"


class DocumentSourceType(str, Enum):
    """Origin of a knowledge document."""
    FILE = "file"
    MANUAL_TEXT = "manual_text"
    WEB = "web"
    API = "api"


class IngestionStatus(str, Enum):
    """Lifecycle status of a document ingestion pipeline."""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class ChunkingStrategy(str, Enum):
    """Supported chunking algorithms."""
    STRUCTURE_AWARE = "structure_aware"
    FIXED_SIZE = "fixed_size"
    SLIDING_WINDOW = "sliding_window"


class ChunkOptions(BaseModel):
    """Configurable options for chunking engine."""
    strategy: ChunkingStrategy = ChunkingStrategy.STRUCTURE_AWARE
    chunk_size: int = Field(default=500, ge=50, le=5000, description="Target size in estimated tokens/chars")
    chunk_overlap: int = Field(default=50, ge=0, le=1000, description="Overlap between consecutive chunks")


# ==========================================
# MEMORY CONTRACTS
# ==========================================

class MemoryCreate(BaseModel):
    """Request payload to create a new memory."""
    category: MemoryCategory
    subcategory: Optional[PersonalSubcategory] = None
    content: str = Field(..., min_length=1, max_length=10000, description="Memory text content")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    source_type: SourceType = SourceType.USER_EXPLICIT
    source_reference_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_category_subcategory_coupling(self) -> "MemoryCreate":
        if self.category == MemoryCategory.PERSONAL and self.subcategory is None:
            raise ValueError("Subcategory is required when memory category is 'personal'.")
        if self.category != MemoryCategory.PERSONAL and self.subcategory is not None:
            raise ValueError(f"Subcategory '{self.subcategory}' is only permitted for 'personal' memories.")
        return self


class MemoryCorrection(BaseModel):
    """Request payload to correct an existing memory, creating a superseding entry."""
    new_content: str = Field(..., min_length=1, max_length=10000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = Field(..., min_length=1, max_length=1000, description="Audit reason for the correction")
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


class MemoryRevoke(BaseModel):
    """Request payload to deactivate/revoke a memory without permanent destruction."""
    reason: str = Field(..., min_length=1, max_length=1000, description="Audit reason for revocation")


class MemoryPurge(BaseModel):
    """Request payload to permanently purge a memory and scrub all sensitive audit snapshots."""
    reason: str = Field(..., min_length=1, max_length=1000, description="Audit reason for hard purge")
    confirm_permanent_loss: bool = Field(
        ...,
        description="Explicit user confirmation flag required to execute permanent destruction."
    )

    @model_validator(mode="after")
    def validate_confirmation(self) -> "MemoryPurge":
        if not self.confirm_permanent_loss:
            raise ValueError("confirm_permanent_loss must be set to True to execute permanent purge.")
        return self


class MemoryResponse(BaseModel):
    """Representation of a memory returned by the API."""
    id: str
    category: MemoryCategory
    subcategory: Optional[PersonalSubcategory] = None
    content: str
    confidence: float
    source_type: SourceType
    source_reference_id: Optional[str] = None
    status: MemoryStatus
    parent_memory_id: Optional[str] = None
    tags: list[str]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    verified_at: Optional[str] = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    verification_method: VerificationMethod = VerificationMethod.SYSTEM_INFERRED
    content_hash: Optional[str] = None


class MemoryAuditRecordResponse(BaseModel):
    """Inspection model for memory audit trail entries."""
    id: int
    memory_id: str
    action: str
    change_reason: str
    previous_state_json: Optional[str] = None
    timestamp: str


# ==========================================
# B3 VERIFICATION & PROVENANCE CONTRACTS
# ==========================================

class MemoryVerifyRequest(BaseModel):
    """Payload to transition memory verification status."""
    status: VerificationStatus
    method: VerificationMethod
    notes: Optional[str] = Field(None, max_length=1000)


class MemoryVerificationResponse(BaseModel):
    """Immutable audit record of verification transition."""
    id: int
    memory_id: str
    previous_status: Optional[VerificationStatus]
    new_status: VerificationStatus
    verification_method: VerificationMethod
    verifier_actor: ActorRole
    notes: Optional[str]
    created_at: str


class MemoryCitationCreate(BaseModel):
    """Create citation to knowledge document or chunk."""
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    quote_text: Optional[str] = Field(None, max_length=2000)
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_reference(self) -> "MemoryCitationCreate":
        if not self.document_id and not self.chunk_id:
            raise ValueError("Citation must reference at least a document_id or a chunk_id.")
        return self


class MemoryCitationResponse(BaseModel):
    """Representation of provenance citation with source status."""
    id: str
    memory_id: str
    document_id: Optional[str]
    chunk_id: Optional[str]
    historical_document_id: Optional[str]
    historical_chunk_id: Optional[str]
    citation_status: CitationStatus
    quote_text: Optional[str]
    confidence_score: float
    metadata: dict[str, Any]
    created_at: str


class MemoryAssociationCreate(BaseModel):
    """Create directed or canonical relation between memories."""
    target_memory_id: str = Field(..., min_length=1)
    relation_type: RelationType
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryAssociationResponse(BaseModel):
    """Representation of an association edge."""
    id: str
    source_memory_id: str
    target_memory_id: str
    relation_type: RelationType
    metadata: dict[str, Any]
    created_at: str


class MemoryConflictCheckRequest(BaseModel):
    """Check candidate statement against active memories in subcategory."""
    content: str = Field(..., min_length=1, max_length=10000)
    category: MemoryCategory
    subcategory: Optional[PersonalSubcategory] = None
    duplicate_threshold: float = Field(default=0.88, ge=0.5, le=1.0)
    contradiction_threshold: float = Field(default=0.65, ge=0.4, le=1.0)


class MemoryConflictItem(BaseModel):
    conflicting_memory_id: str
    existing_content: str
    subcategory: Optional[PersonalSubcategory]
    similarity_score: Optional[float] = None
    conflict_type: ConflictType
    explanation: str
    recommended_action: str


class MemoryConflictCheckResponse(BaseModel):
    candidate_content: str
    has_conflicts: bool
    highest_severity_conflict: Optional[ConflictType] = None
    conflicts: list[MemoryConflictItem]
    semantic_detection_available: bool
    analysis_capability: str
    disclaimer: str = (
        "NO_CONFLICT_DETECTED indicates no matching heuristic rules or similarities met "
        "detection thresholds. It does not certify factual safety or objective truth."
    )


class MemorySearchRequest(BaseModel):
    """Search request with strictly typed filters."""
    query: str = Field(..., min_length=1, max_length=1000)
    mode: SearchMode = SearchMode.HYBRID
    category: Optional[MemoryCategory] = None
    subcategory: Optional[PersonalSubcategory] = None
    tags: Optional[list[str]] = None
    include_statuses: list[MemoryStatus] = Field(default_factory=lambda: [MemoryStatus.ACTIVE])
    include_verification: list[VerificationStatus] = Field(
        default_factory=lambda: [VerificationStatus.VERIFIED, VerificationStatus.UNVERIFIED]
    )
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class MemorySearchResult(BaseModel):
    memory: MemoryResponse
    score: float
    match_source: str
    citations: list[MemoryCitationResponse] = Field(default_factory=list)
    associations: list[MemoryAssociationResponse] = Field(default_factory=list)


class MemorySearchResponse(BaseModel):
    results: list[MemorySearchResult]
    total_results: int
    effective_mode: SearchMode
    fallback_applied: bool
    fallback_reason: Optional[str] = None
    active_model: Optional[str] = None
    active_model_version: Optional[str] = None


class EmbeddingReindexRequest(BaseModel):
    target_model_name: str = Field(..., min_length=1)
    target_model_version: str = Field(..., min_length=1)
    batch_size: int = Field(default=50, ge=1, le=200)


class EmbeddingReindexResponse(BaseModel):
    target_model_name: str
    target_model_version: str
    total_active_memories: int
    indexed_memories: int
    unindexed_active_count: int
    is_ready_for_cutover: bool


class EmbeddingCutoverRequest(BaseModel):
    target_model_name: str = Field(..., min_length=1)
    target_model_version: str = Field(..., min_length=1)


class EmbeddingCutoverResponse(BaseModel):
    cutover_successful: bool
    active_model_name: str
    active_model_version: str
    dimensions: int
    activated_at: str


# ==========================================
# DOCUMENT & CHUNK CONTRACTS
# ==========================================

class DocumentCreate(BaseModel):
    """Request payload to register an ingested document."""
    title: str = Field(..., min_length=1, max_length=500)
    raw_content: str = Field(..., min_length=1, description="Raw UTF-8 text content of the document")
    source_uri: Optional[str] = None
    source_type: DocumentSourceType = DocumentSourceType.MANUAL_TEXT
    mime_type: str = Field(default="text/plain")
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_options: Optional[ChunkOptions] = Field(default_factory=ChunkOptions)


class DocumentResponse(BaseModel):
    """Representation of an ingested document."""
    id: str
    title: str
    source_uri: Optional[str] = None
    source_type: DocumentSourceType
    mime_type: str
    file_size_bytes: int
    content_hash: str
    raw_storage_path: str
    extracted_storage_path: Optional[str] = None
    original_filename: Optional[str] = None
    file_extension: Optional[str] = None
    ingestion_status: IngestionStatus = IngestionStatus.PROCESSED
    error_message: Optional[str] = None
    chunk_count: int = 0
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class DocumentStatusResponse(BaseModel):
    """Inspection model for document processing status."""
    id: str
    title: str
    ingestion_status: IngestionStatus
    chunk_count: int
    error_message: Optional[str] = None
    content_hash: str
    updated_at: str


class DocumentChunkCreate(BaseModel):
    """Payload to store an atomic chunk with full retrieval provenance."""
    chunk_index: int = Field(ge=0)
    chunk_text: str = Field(..., min_length=1)
    extraction_method: str = Field(default="plain_text_v1")
    page_number: Optional[int] = Field(default=None, ge=1)
    section: Optional[str] = None
    source_location: Optional[str] = None
    token_count: Optional[int] = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentChunkResponse(BaseModel):
    """Inspection model for a document chunk and its retrieval provenance."""
    id: str
    document_id: str
    chunk_index: int
    page_number: Optional[int] = None
    section: Optional[str] = None
    source_location: Optional[str] = None
    extraction_method: str
    content_hash: str
    token_count: Optional[int] = None
    chunk_text: str
    metadata: dict[str, Any]
    created_at: str


# ==========================================
# RETRIEVAL CONTRACTS (PHASE B2)
# ==========================================

class RetrievalMode(str, Enum):
    """Retrieval strategies."""
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class RetrievalQuery(BaseModel):
    """Query payload for search operations."""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query string")
    mode: RetrievalMode = Field(default=RetrievalMode.HYBRID, description="Retrieval algorithm: keyword, semantic, or hybrid")
    top_k: int = Field(default=5, ge=1, le=100, description="Maximum number of chunks to return")
    document_id: Optional[str] = Field(default=None, description="Optional filter to search within a specific document")
    min_score: float = Field(default=0.0, ge=0.0, description="Minimum score threshold for returned results")


class SearchResultItem(BaseModel):
    """An individual retrieved chunk with scoring, highlights, and provenance."""
    chunk_id: str
    document_id: str
    document_title: str
    chunk_index: int
    chunk_text: str
    score: float
    page_number: Optional[int] = None
    section: Optional[str] = None
    source_location: Optional[str] = None
    highlights: Optional[str] = None
    retrieval_mode: RetrievalMode


class SearchResponse(BaseModel):
    """Result set for a search query."""
    query: str
    mode: RetrievalMode
    total_results: int
    results: list[SearchResultItem]
    latency_ms: float


class IndexStatsResponse(BaseModel):
    """Statistics for keyword and vector indices."""
    total_documents: int
    total_chunks: int
    fts5_indexed_chunks: int
    embedded_chunks: int
    embedding_model: str
    embedding_dimensions: int


class EmbeddingIndexRequest(BaseModel):
    """Request to generate embeddings for un-indexed document chunks."""
    document_id: Optional[str] = None
    batch_size: int = Field(default=50, ge=1, le=500)


class EmbeddingIndexResponse(BaseModel):
    """Status report of embedding generation."""
    indexed_count: int
    model_name: str
    dimensions: int


# ==========================================
# B4 EPISODIC & PROCEDURAL MEMORY CONTRACTS
# ==========================================

class EventType(str, Enum):
    CONVERSATION = "conversation"
    TASK_EXECUTION = "task_execution"
    OBSERVATION = "observation"
    SYSTEM_EVENT = "system_event"
    INCIDENT = "incident"


class EpisodeCreate(BaseModel):
    """Payload to log a discrete event, conversation, or task session."""
    session_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    event_type: EventType
    occurred_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_seconds: Optional[float] = Field(None, ge=0.0)
    summary: str = Field(..., min_length=1, max_length=2000)
    narrative_detail: Optional[str] = Field(None, max_length=20000)
    actors: list[str] = Field(default_factory=lambda: ["user"])
    context_tags: list[str] = Field(default_factory=list)
    significance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EpisodeResponse(BaseModel):
    """Representation of an episodic event."""
    id: str
    session_id: str
    title: str
    event_type: EventType
    occurred_at: str
    duration_seconds: Optional[float]
    summary: str
    narrative_detail: Optional[str]
    actors: list[str]
    context_tags: list[str]
    significance_score: float
    metadata: dict[str, Any]
    created_at: str


class EpisodeTimelineRequest(BaseModel):
    """Filter and query criteria for episodic timeline retrieval."""
    session_id: Optional[str] = None
    event_types: Optional[list[EventType]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    min_significance: float = Field(default=0.0, ge=0.0, le=1.0)
    query: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)
    order: str = Field(default="asc", pattern="^(asc|desc)$")


class ProcedureStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class ProcedureStep(BaseModel):
    """Atomic step in a multi-step procedure."""
    step_number: int = Field(..., ge=1)
    action: str = Field(..., min_length=1, max_length=1000)
    expected_outcome: Optional[str] = Field(None, max_length=1000)
    fallback_action: Optional[str] = Field(None, max_length=1000)
    validation_check: Optional[str] = Field(None, max_length=1000)


class ProcedureCreate(BaseModel):
    """Register a new repeatable workflow or operational procedure."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    status: ProcedureStatus = ProcedureStatus.ACTIVE
    trigger_conditions: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    steps: list[ProcedureStep] = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_step_sequence(self) -> "ProcedureCreate":
        step_numbers = [s.step_number for s in self.steps]
        if not step_numbers or step_numbers[0] != 1:
            raise ValueError("Procedure steps must start at 1.")
        if step_numbers != list(range(1, len(self.steps) + 1)):
            raise ValueError("Procedure steps must be strictly sequential starting from 1.")
        return self


class ProcedureResponse(BaseModel):
    """Representation of a procedural workflow."""
    id: str
    title: str
    description: str
    version: str
    status: ProcedureStatus
    trigger_conditions: list[str]
    prerequisites: list[str]
    steps: list[ProcedureStep]
    execution_count: int
    success_count: int
    success_rate: float
    last_executed_at: Optional[str]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class ProcedureExecutionLogCreate(BaseModel):
    """Log an execution of a procedure."""
    execution_status: str = Field(..., pattern="^(success|failure|aborted|partial)$")
    duration_seconds: Optional[float] = Field(None, ge=0.0)
    step_results: list[dict[str, Any]] = Field(default_factory=list)
    error_message: Optional[str] = Field(None, max_length=2000)
    notes: Optional[str] = Field(None, max_length=1000)


class ProcedureExecutionLogResponse(BaseModel):
    """Record of a procedure execution run."""
    id: int
    procedure_id: str
    executed_at: str
    execution_status: str
    duration_seconds: Optional[float]
    execution_actor: str
    step_results: list[dict[str, Any]]
    error_message: Optional[str]
    notes: Optional[str]


class LinkType(str, Enum):
    EXECUTED_PROCEDURE = "executed_procedure"
    DERIVED_MEMORY = "derived_memory"
    EXEMPLAR_EPISODE = "exemplar_episode"
    TROUBLESHOOTING_CONTEXT = "troubleshooting_context"


class MemoryLinkCreate(BaseModel):
    """Link between Episode, Procedure, and Memory."""
    episode_id: Optional[str] = None
    procedure_id: Optional[str] = None
    memory_id: Optional[str] = None
    link_type: LinkType
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_link_pairing(self) -> "MemoryLinkCreate":
        count = sum(1 for target in [self.episode_id, self.procedure_id, self.memory_id] if target is not None)
        if count < 2:
            raise ValueError("MemoryLink must connect at least two entities (episode, procedure, or memory).")
        return self


class EpisodeLinkCreate(BaseModel):
    """Endpoint payload to attach a procedure or memory link to an episode."""
    procedure_id: Optional[str] = None
    memory_id: Optional[str] = None
    link_type: LinkType
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryLinkResponse(BaseModel):
    """Representation of a cross-domain memory link."""
    id: str
    episode_id: Optional[str]
    procedure_id: Optional[str]
    memory_id: Optional[str]
    link_type: LinkType
    metadata: dict[str, Any]
    created_at: str


# ==========================================
# B5 MEMORY INTELLIGENCE & EVALUATION CONTRACTS
# ==========================================

class DecayConfig(BaseModel):
    """Configuration for half-life recency decay and dynamic scoring."""
    default_half_life_days: float = Field(default=90.0, ge=1.0, le=3650.0)
    subcategory_half_lives: dict[str, float] = Field(
        default_factory=lambda: {
            "profile_fact": 365.0,
            "preference": 180.0,
            "goal": 90.0,
            "skill": 180.0,
            "project_context": 30.0,
        }
    )
    recency_weight: float = Field(default=0.2, ge=0.0, le=1.0)
    access_weight: float = Field(default=0.1, ge=0.0, le=1.0)
    similarity_weight: float = Field(default=0.7, ge=0.0, le=1.0)


class MemoryTouchRequest(BaseModel):
    """Payload to record access/retrieval touch without modifying memory content."""
    memory_ids: list[str] = Field(..., min_length=1, max_length=100)


class MemoryDecayScore(BaseModel):
    """Calculated decay and combined relevance score for a memory."""
    memory_id: str
    base_confidence: float
    decay_score: float
    access_count: int
    last_accessed_at: Optional[str]
    effective_score: float


class ConsolidationStatus(str, Enum):
    """Lifecycle status of an episodic consolidation candidate."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class ConsolidationCandidateCreate(BaseModel):
    """Prospective semantic fact distilled from an episodic interaction session."""
    session_id: str = Field(..., min_length=1, max_length=100)
    candidate_category: MemoryCategory = MemoryCategory.PERSONAL
    candidate_subcategory: Optional[PersonalSubcategory] = PersonalSubcategory.PREFERENCE
    candidate_content: str = Field(..., min_length=1, max_length=10000)
    rationale: str = Field(..., min_length=1, max_length=2000)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    source_episode_ids: list[str] = Field(default_factory=list)


class ConsolidationCandidateResponse(BaseModel):
    """Representation of an episodic consolidation candidate."""
    id: str
    session_id: str
    candidate_category: MemoryCategory
    candidate_subcategory: Optional[PersonalSubcategory]
    candidate_content: str
    rationale: str
    confidence: float
    source_episode_ids: list[str]
    status: ConsolidationStatus
    applied_memory_id: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[str]
    created_at: str
    updated_at: str


class ConsolidationReviewAction(BaseModel):
    """Review decision for an episodic consolidation candidate."""
    action: str = Field(..., pattern="^(approve|reject)$")
    review_notes: Optional[str] = Field(None, max_length=1000)


class SessionConsolidationRequest(BaseModel):
    """Request to trigger automated memory consolidation across a session's episodes."""
    session_id: str = Field(..., min_length=1, max_length=100)
    min_significance: float = Field(default=0.5, ge=0.0, le=1.0)


class CompactionCandidateCluster(BaseModel):
    """Identified cluster of near-duplicate or overlapping memories proposed for compaction."""
    subcategory: Optional[str]
    memory_ids: list[str] = Field(..., min_length=2)
    proposed_consolidated_content: str
    similarity_score: float
    rationale: str


class CompactionPlan(BaseModel):
    """Advisory plan identifying memory redundancies and proposed merges."""
    clusters: list[CompactionCandidateCluster]
    total_memories_analyzed: int
    redundant_memories_identified: int
    estimated_space_savings_pct: float


class CompactionExecuteRequest(BaseModel):
    """Execution request to execute an advisory compaction plan."""
    dry_run: bool = Field(default=True)
    confirmed: bool = Field(default=False)
    cluster_indices: Optional[list[int]] = None
    plan: Optional[CompactionPlan] = None


class CompactionResult(BaseModel):
    """Outcome of an executed compaction run."""
    executed: bool
    dry_run: bool
    clusters_processed: int
    superseded_memory_ids: list[str]
    created_memory_ids: list[str]
    message: str


class BenchmarkRunRequest(BaseModel):
    """Parameters to trigger a quantitative evaluation benchmark run."""
    run_type: str = Field(default="full", pattern="^(full|retrieval|integrity|latency)$")
    k_values: list[int] = Field(default_factory=lambda: [1, 3, 5, 10])


class RetrievalMetrics(BaseModel):
    """Evaluated retrieval performance metrics."""
    precision_at_k: dict[str, float]
    recall_at_k: dict[str, float]
    mrr: float
    ndcg_at_k: dict[str, float]
    mean_latency_ms: float
    p95_latency_ms: float


class IntegrityMetrics(BaseModel):
    """Evaluated database and architectural integrity metrics."""
    citation_parentage_accuracy: float
    acyclic_association_rate: float
    stale_embedding_detection_rate: float
    verification_state_machine_compliance: float


class BenchmarkReportResponse(BaseModel):
    """Comprehensive evaluation benchmark report."""
    run_id: str
    run_type: str
    retrieval_metrics: RetrievalMetrics
    integrity_metrics: IntegrityMetrics
    execution_time_ms: float
    system_profile: dict[str, Any]
    created_at: str


# ==========================================
# SYSTEM & HEALTH CONTRACTS
# ==========================================

class HealthResponse(BaseModel):
    """System health and diagnostic status."""
    status: str
    app_version: str
    environment: str
    db_connected: bool
    wal_mode: bool
    foreign_keys_on: bool
    timestamp: str


class SystemInfoResponse(BaseModel):
    """Brain Core capabilities and active runtime parameters."""
    app_name: str
    app_version: str
    sqlite_version: str
    fts5_supported: bool
    supported_memory_categories: list[str]
    supported_personal_subcategories: list[str]
    max_file_size_bytes: int
