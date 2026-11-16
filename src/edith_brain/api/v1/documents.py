"""API router for knowledge document ingestion, multi-format upload, and retrieval provenance."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, File, UploadFile, Form, status
from edith_brain.core.contracts import (
    DocumentCreate,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentChunkCreate,
    DocumentChunkResponse,
    IngestionStatus,
    ChunkingStrategy,
    ChunkOptions,
)
from edith_brain.services.document_service import DocumentService
from edith_brain.api.deps import get_document_service

router = APIRouter(prefix="/documents", tags=["Knowledge Documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    strategy: ChunkingStrategy = Form(ChunkingStrategy.STRUCTURE_AWARE),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Upload and ingest a binary document file (PDF, Markdown, Plain Text, DOCX)."""
    raw_bytes = await file.read()
    chunk_opts = ChunkOptions(
        strategy=strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return service.ingest_binary_document(
        filename=file.filename or "uploaded_document.txt",
        raw_bytes=raw_bytes,
        title=title,
        mime_type=file.content_type,
        chunk_options=chunk_opts,
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def ingest_document(
    payload: DocumentCreate,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Ingest a knowledge document from JSON payload (B0 backwards compatible)."""
    return service.ingest_document(payload)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    status_filter: Optional[IngestionStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: DocumentService = Depends(get_document_service),
) -> list[DocumentResponse]:
    """List ingested documents with optional status filtering and pagination."""
    return service.list_documents(status=status_filter, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Retrieve document metadata by ID."""
    return service.get_document(document_id)


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> DocumentStatusResponse:
    """Retrieve document ingestion status, chunk count, and any error messages."""
    return service.get_document_status(document_id)


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> dict:
    """Permanently delete a document, cascading its chunks and cleaning up disk storage."""
    return service.delete_document(document_id)


@router.post("/{document_id}/chunks", response_model=DocumentChunkResponse, status_code=status.HTTP_201_CREATED)
def add_document_chunk(
    document_id: str,
    payload: DocumentChunkCreate,
    service: DocumentService = Depends(get_document_service),
) -> DocumentChunkResponse:
    """Register an atomic document chunk with deep retrieval provenance."""
    return service.add_chunk(document_id, payload)


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkResponse])
def get_document_chunks(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> list[DocumentChunkResponse]:
    """Retrieve all chunks with retrieval provenance for a given document."""
    return service.get_document_chunks(document_id)
