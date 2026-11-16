"""API router for keyword, semantic, and hybrid retrieval operations."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from edith_brain.core.contracts import (
    RetrievalMode,
    RetrievalQuery,
    SearchResponse,
    IndexStatsResponse,
    EmbeddingIndexRequest,
    EmbeddingIndexResponse,
)
from edith_brain.services.retrieval.retrieval_service import RetrievalService
from edith_brain.api.deps import get_retrieval_service

router = APIRouter(prefix="/retrieval", tags=["Knowledge Retrieval"])


@router.post("/search", response_model=SearchResponse, status_code=status.HTTP_200_OK)
def search_knowledge(
    payload: RetrievalQuery,
    service: RetrievalService = Depends(get_retrieval_service),
) -> SearchResponse:
    """Execute keyword, semantic, or hybrid retrieval across ingested document chunks."""
    return service.search(payload)


@router.get("/search", response_model=SearchResponse, status_code=status.HTTP_200_OK)
def search_knowledge_get(
    q: str = Query(..., min_length=1, description="Search query string"),
    mode: RetrievalMode = Query(default=RetrievalMode.HYBRID, description="Retrieval mode"),
    top_k: int = Query(default=5, ge=1, le=100),
    document_id: Optional[str] = Query(default=None),
    min_score: float = Query(default=0.0, ge=0.0),
    service: RetrievalService = Depends(get_retrieval_service),
) -> SearchResponse:
    """Convenience GET endpoint for document retrieval."""
    query_obj = RetrievalQuery(
        query=q,
        mode=mode,
        top_k=top_k,
        document_id=document_id,
        min_score=min_score,
    )
    return service.search(query_obj)


@router.post("/index-embeddings", response_model=EmbeddingIndexResponse, status_code=status.HTTP_200_OK)
def index_embeddings(
    payload: EmbeddingIndexRequest = EmbeddingIndexRequest(),
    service: RetrievalService = Depends(get_retrieval_service),
) -> EmbeddingIndexResponse:
    """Batch generate vector embeddings for document chunks missing embeddings."""
    return service.index_unembedded_chunks(
        document_id=payload.document_id,
        batch_size=payload.batch_size,
    )


@router.get("/stats", response_model=IndexStatsResponse, status_code=status.HTTP_200_OK)
def get_retrieval_stats(
    service: RetrievalService = Depends(get_retrieval_service),
) -> IndexStatsResponse:
    """Inspect keyword index (FTS5) and vector embedding index metrics."""
    return service.get_index_stats()
