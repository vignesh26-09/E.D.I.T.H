"""E.D.I.T.H. Brain Core Python Client SDK.

Provides a synchronous, strongly-typed interface for client applications, CLI tools,
and autonomous agents interacting with the Brain Core REST API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Union
import httpx

from edith_brain.core.contracts import (
    HealthResponse,
    SystemInfoResponse,
    MemoryCreate,
    MemoryResponse,
    MemoryCorrection,
    MemoryRevoke,
    MemoryPurge,
    MemoryVerifyRequest,
    MemoryCitationCreate,
    MemoryCitationResponse,
    MemoryAssociationCreate,
    MemoryAssociationResponse,
    MemoryConflictCheckRequest,
    MemoryConflictCheckResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentChunkResponse,
    RetrievalQuery,
    SearchResponse,
    EpisodeCreate,
    EpisodeResponse,
    EpisodeTimelineRequest,
    EpisodeLinkCreate,
    MemoryLinkResponse,
    ProcedureCreate,
    ProcedureResponse,
    ProcedureExecutionLogCreate,
    ProcedureExecutionLogResponse,
    ProcedureStatus,
    MemoryTouchRequest,
    MemoryDecayScore,
    ConsolidationCandidateResponse,
    ConsolidationReviewAction,
    SessionConsolidationRequest,
    CompactionPlan,
    CompactionExecuteRequest,
    CompactionResult,
    BenchmarkRunRequest,
    BenchmarkReportResponse,
)


class EdithBrainClient:
    """Synchronous HTTP client for E.D.I.T.H. Brain Core."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        token: Optional[str] = None,
        timeout: float = 30.0,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        if http_client is not None:
            self.http_client = http_client
        else:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            self.http_client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=timeout,
            )

    def close(self) -> None:
        """Close the underlying HTTP client session."""
        self.http_client.close()

    def __enter__(self) -> EdithBrainClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ==========================================
    # HEALTH & SYSTEM
    # ==========================================

    def get_health(self) -> HealthResponse:
        """Retrieve system health and database WAL mode diagnostics."""
        resp = self.http_client.get("/api/v1/health")
        resp.raise_for_status()
        return HealthResponse(**resp.json())

    def get_system_info(self) -> SystemInfoResponse:
        """Retrieve runtime version and supported memory categories."""
        resp = self.http_client.get("/api/v1/system/info")
        resp.raise_for_status()
        return SystemInfoResponse(**resp.json())

    # ==========================================
    # DOCUMENT INGESTION & RETRIEVAL
    # ==========================================

    def upload_document(
        self,
        file_path: Union[str, Path],
        title: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> DocumentResponse:
        """Upload a file (PDF, TXT, MD, DOCX) for automatic parsing and chunking."""
        path = Path(file_path)
        with open(path, "rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            data = {}
            if title:
                data["title"] = title
            if tags:
                data["tags"] = ",".join(tags)
            resp = self.http_client.post(
                "/api/v1/documents/upload",
                files=files,
                data=data,
            )
        resp.raise_for_status()
        return DocumentResponse(**resp.json())

    def get_document(self, document_id: str) -> DocumentResponse:
        """Retrieve document metadata."""
        resp = self.http_client.get(f"/api/v1/documents/{document_id}")
        resp.raise_for_status()
        return DocumentResponse(**resp.json())

    def get_document_status(self, document_id: str) -> DocumentStatusResponse:
        """Retrieve ingestion status, chunk count, and potential errors."""
        resp = self.http_client.get(f"/api/v1/documents/{document_id}/status")
        resp.raise_for_status()
        return DocumentStatusResponse(**resp.json())

    def get_document_chunks(self, document_id: str) -> list[DocumentChunkResponse]:
        """Retrieve all chunks and provenance metadata for a document."""
        resp = self.http_client.get(f"/api/v1/documents/{document_id}/chunks")
        resp.raise_for_status()
        return [DocumentChunkResponse(**c) for c in resp.json()]

    def delete_document(self, document_id: str) -> dict:
        """Delete a document, cascading chunk and storage file cleanup."""
        resp = self.http_client.delete(f"/api/v1/documents/{document_id}")
        resp.raise_for_status()
        return resp.json()

    def search_knowledge(self, query: RetrievalQuery) -> SearchResponse:
        """Perform hybrid, keyword, or semantic search over knowledge chunks."""
        resp = self.http_client.post("/api/v1/retrieval/search", json=query.model_dump())
        resp.raise_for_status()
        return SearchResponse(**resp.json())

    # ==========================================
    # PERSONAL MEMORY LIFECYCLE
    # ==========================================

    def create_memory(self, memory: MemoryCreate) -> MemoryResponse:
        """Create a new personal or semantic memory entry."""
        resp = self.http_client.post("/api/v1/memories", json=memory.model_dump(exclude_none=True))
        resp.raise_for_status()
        return MemoryResponse(**resp.json())

    def get_memory(self, memory_id: str) -> MemoryResponse:
        """Fetch memory details including verification status and lineage."""
        resp = self.http_client.get(f"/api/v1/memories/{memory_id}")
        resp.raise_for_status()
        return MemoryResponse(**resp.json())

    def list_memories(
        self,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        status_filter: Optional[str] = "active",
        limit: int = 50,
    ) -> list[MemoryResponse]:
        """List memories with category, subcategory, and status filtering."""
        params = {"limit": limit}
        if category:
            params["category"] = category
        if subcategory:
            params["subcategory"] = subcategory
        if status_filter:
            params["status"] = status_filter
        resp = self.http_client.get("/api/v1/memories", params=params)
        resp.raise_for_status()
        return [MemoryResponse(**m) for m in resp.json()]

    def correct_memory(self, memory_id: str, correction: MemoryCorrection) -> MemoryResponse:
        """Correct a memory, superseding predecessor and preserving historical audit trail."""
        resp = self.http_client.post(
            f"/api/v1/memories/{memory_id}/correct",
            json=correction.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return MemoryResponse(**resp.json())

    def revoke_memory(self, memory_id: str, revocation: MemoryRevoke) -> MemoryResponse:
        """Deactivate a memory without physical destruction."""
        resp = self.http_client.post(
            f"/api/v1/memories/{memory_id}/revoke",
            json=revocation.model_dump(),
        )
        resp.raise_for_status()
        return MemoryResponse(**resp.json())

    def purge_memory(self, memory_id: str, purge: MemoryPurge) -> dict:
        """Permanently hard-delete a memory, redacting snapshots from audit logs."""
        resp = self.http_client.request(
            "DELETE",
            f"/api/v1/memories/{memory_id}/purge",
            json=purge.model_dump(),
        )
        resp.raise_for_status()
        return resp.json()

    def verify_memory(self, memory_id: str, verify_req: MemoryVerifyRequest) -> MemoryResponse:
        """Transition memory verification status through state machine."""
        resp = self.http_client.post(
            f"/api/v1/memories/{memory_id}/verify",
            json=verify_req.model_dump(),
        )
        resp.raise_for_status()
        return MemoryResponse(**resp.json())

    def add_citation(self, memory_id: str, citation: MemoryCitationCreate) -> MemoryCitationResponse:
        """Link memory to a supporting document or chunk citation."""
        resp = self.http_client.post(
            f"/api/v1/memories/{memory_id}/citations",
            json=citation.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return MemoryCitationResponse(**resp.json())

    def add_association(self, memory_id: str, association: MemoryAssociationCreate) -> MemoryAssociationResponse:
        """Create a directed relation between two memories with cycle checks."""
        resp = self.http_client.post(
            f"/api/v1/memories/{memory_id}/associations",
            json=association.model_dump(),
        )
        resp.raise_for_status()
        return MemoryAssociationResponse(**resp.json())

    def check_conflicts(self, request: MemoryConflictCheckRequest) -> MemoryConflictCheckResponse:
        """Perform advisory pre-flight conflict and contradiction analysis."""
        resp = self.http_client.post(
            "/api/v1/memories/check-conflicts",
            json=request.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return MemoryConflictCheckResponse(**resp.json())

    def search_memories(self, request: MemorySearchRequest) -> MemorySearchResponse:
        """Retrieve memories under keyword, semantic, or hybrid search."""
        resp = self.http_client.post(
            "/api/v1/memories/search",
            json=request.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return MemorySearchResponse(**resp.json())

    # ==========================================
    # EPISODIC MEMORY
    # ==========================================

    def create_episode(self, episode: EpisodeCreate) -> EpisodeResponse:
        """Record an episodic event, conversation turn, or milestone."""
        resp = self.http_client.post("/api/v1/episodes", json=episode.model_dump(exclude_none=True))
        resp.raise_for_status()
        return EpisodeResponse(**resp.json())

    def get_episode(self, episode_id: str) -> EpisodeResponse:
        """Retrieve episodic event details."""
        resp = self.http_client.get(f"/api/v1/episodes/{episode_id}")
        resp.raise_for_status()
        return EpisodeResponse(**resp.json())

    def get_timeline(self, request: EpisodeTimelineRequest) -> list[EpisodeResponse]:
        """Query chronological timeline with multi-factor filters and FTS search."""
        resp = self.http_client.post("/api/v1/episodes/timeline", json=request.model_dump(exclude_none=True))
        resp.raise_for_status()
        return [EpisodeResponse(**e) for e in resp.json()]

    def list_sessions(self, limit: int = 50) -> list[dict]:
        """List aggregated conversational/task sessions with event counts."""
        resp = self.http_client.get("/api/v1/episodes/sessions", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    def link_episode(self, episode_id: str, link: EpisodeLinkCreate) -> MemoryLinkResponse:
        """Attach a cross-domain link from an episode to a procedure or personal memory."""
        resp = self.http_client.post(
            f"/api/v1/episodes/{episode_id}/links",
            json=link.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return MemoryLinkResponse(**resp.json())

    # ==========================================
    # PROCEDURAL MEMORY
    # ==========================================

    def create_procedure(self, procedure: ProcedureCreate) -> ProcedureResponse:
        """Register a repeatable multi-step procedural playbook."""
        resp = self.http_client.post("/api/v1/procedures", json=procedure.model_dump())
        resp.raise_for_status()
        return ProcedureResponse(**resp.json())

    def get_procedure(self, procedure_id: str) -> ProcedureResponse:
        """Retrieve procedure steps, trigger conditions, and telemetry."""
        resp = self.http_client.get(f"/api/v1/procedures/{procedure_id}")
        resp.raise_for_status()
        return ProcedureResponse(**resp.json())

    def search_procedures(self, query: str, status_filter: Optional[ProcedureStatus] = None) -> list[ProcedureResponse]:
        """Search procedures via trigger condition and description matching."""
        params = {"q": query}
        if status_filter:
            params["status"] = status_filter.value
        resp = self.http_client.get("/api/v1/procedures/search", params=params)
        resp.raise_for_status()
        return [ProcedureResponse(**p) for p in resp.json()]

    def log_execution(self, procedure_id: str, log: ProcedureExecutionLogCreate) -> ProcedureExecutionLogResponse:
        """Record an execution run and update live procedure telemetry."""
        resp = self.http_client.post(
            f"/api/v1/procedures/{procedure_id}/execute",
            json=log.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return ProcedureExecutionLogResponse(**resp.json())

    def update_procedure_status(self, procedure_id: str, new_status: ProcedureStatus) -> ProcedureResponse:
        """Transition procedure status (draft, active, deprecated)."""
        resp = self.http_client.patch(
            f"/api/v1/procedures/{procedure_id}/status",
            params={"status": new_status.value},
        )
        resp.raise_for_status()
        return ProcedureResponse(**resp.json())

    # ==========================================
    # MEMORY INTELLIGENCE & EVALUATION
    # ==========================================

    def touch_memories(self, memory_ids: list[str]) -> dict:
        """Record access/retrieval touch without mutating memory content."""
        resp = self.http_client.post(
            "/api/v1/intelligence/touch",
            json=MemoryTouchRequest(memory_ids=memory_ids).model_dump(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_decay_score(self, memory_id: str) -> MemoryDecayScore:
        """Inspect recency decay and effective relevance score."""
        resp = self.http_client.get(f"/api/v1/intelligence/decay/{memory_id}")
        resp.raise_for_status()
        return MemoryDecayScore(**resp.json())

    def consolidate_session(self, session_id: str, min_significance: float = 0.5) -> list[ConsolidationCandidateResponse]:
        """Scan an episodic session and extract candidate personal facts/preferences."""
        resp = self.http_client.post(
            "/api/v1/intelligence/consolidations/session",
            json=SessionConsolidationRequest(session_id=session_id, min_significance=min_significance).model_dump(),
        )
        resp.raise_for_status()
        return [ConsolidationCandidateResponse(**c) for c in resp.json()]

    def review_consolidation(self, candidate_id: str, action: str, notes: Optional[str] = None) -> ConsolidationCandidateResponse:
        """Approve or reject a consolidation candidate."""
        resp = self.http_client.post(
            f"/api/v1/intelligence/consolidations/{candidate_id}/review",
            json=ConsolidationReviewAction(action=action, review_notes=notes).model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return ConsolidationCandidateResponse(**resp.json())

    def get_compaction_plan(self, subcategory: Optional[str] = None, threshold: float = 0.65) -> CompactionPlan:
        """Generate an advisory compaction plan identifying redundant memory clusters."""
        params = {"similarity_threshold": threshold}
        if subcategory:
            params["subcategory"] = subcategory
        resp = self.http_client.get("/api/v1/intelligence/compaction/plan", params=params)
        resp.raise_for_status()
        return CompactionPlan(**resp.json())

    def execute_compaction(self, request: CompactionExecuteRequest) -> CompactionResult:
        """Execute or dry-run a compaction plan."""
        resp = self.http_client.post(
            "/api/v1/intelligence/compaction/execute",
            json=request.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return CompactionResult(**resp.json())

    def run_benchmark(self, request: Optional[BenchmarkRunRequest] = None) -> BenchmarkReportResponse:
        """Execute the quantitative benchmark evaluation suite."""
        req = request or BenchmarkRunRequest()
        resp = self.http_client.post("/api/v1/evaluation/benchmark", json=req.model_dump())
        resp.raise_for_status()
        return BenchmarkReportResponse(**resp.json())
