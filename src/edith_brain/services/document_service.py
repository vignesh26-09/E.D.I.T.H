"""Document domain service managing multi-tier file storage, ingestion, and retrieval provenance."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

from edith_brain.core.config import Settings, get_settings
from edith_brain.core.contracts import (
    DocumentCreate,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentChunkCreate,
    DocumentChunkResponse,
    DocumentSourceType,
    IngestionStatus,
    ChunkOptions,
    ChunkingStrategy,
)
from edith_brain.core.exceptions import NotFoundError, ConflictError, ValidationError
from edith_brain.core.security import compute_sha256, validate_safe_path, validate_file_size
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.document_repository import DocumentRepository
from edith_brain.repositories.retrieval_repository import RetrievalRepository
from edith_brain.services.parsers.registry import get_parser_for_file
from edith_brain.services.parsers.base import ExtractionResult, ExtractedElement
from edith_brain.services.normalizer import normalize_text
from edith_brain.services.chunking.chunkers import get_chunker, Chunk
from edith_brain.services.retrieval.embeddings import (
    BaseEmbeddingProvider,
    get_embedding_provider,
    pack_vector,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_document_response(row) -> DocumentResponse:
    # Keys might be missing in partial queries, safely get them
    keys = row.keys()
    return DocumentResponse(
        id=row["id"],
        title=row["title"],
        source_uri=row["source_uri"],
        source_type=DocumentSourceType(row["source_type"]),
        mime_type=row["mime_type"],
        file_size_bytes=row["file_size_bytes"],
        content_hash=row["content_hash"],
        raw_storage_path=row["raw_storage_path"],
        extracted_storage_path=row["extracted_storage_path"],
        original_filename=row["original_filename"] if "original_filename" in keys else None,
        file_extension=row["file_extension"] if "file_extension" in keys else None,
        ingestion_status=IngestionStatus(row["ingestion_status"]) if "ingestion_status" in keys and row["ingestion_status"] else IngestionStatus.PROCESSED,
        error_message=row["error_message"] if "error_message" in keys else None,
        chunk_count=row["chunk_count"] if "chunk_count" in keys and row["chunk_count"] is not None else 0,
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_chunk_response(row) -> DocumentChunkResponse:
    return DocumentChunkResponse(
        id=row["id"],
        document_id=row["document_id"],
        chunk_index=row["chunk_index"],
        page_number=row["page_number"],
        section=row["section"],
        source_location=row["source_location"],
        extraction_method=row["extraction_method"],
        content_hash=row["content_hash"],
        token_count=row["token_count"],
        chunk_text=row["chunk_text"],
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
    )


class DocumentService:
    """Coordinates file system storage, hash verification, parser execution, and chunk provenance."""

    def __init__(
        self,
        engine: SQLiteEngine,
        settings: Settings | None = None,
        doc_repo: DocumentRepository | None = None,
        retrieval_repo: RetrievalRepository | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings or get_settings()
        self.doc_repo = doc_repo or DocumentRepository()
        self.retrieval_repo = retrieval_repo or RetrievalRepository()
        self.embedding_provider = embedding_provider or get_embedding_provider(settings=self.settings)

    def ingest_document(self, payload: DocumentCreate) -> DocumentResponse:
        """Ingest a raw text document with size validation, deduplication, and safe multi-tier storage (B0 compatible)."""
        raw_bytes = payload.raw_content.encode("utf-8")
        file_size = len(raw_bytes)

        # 1. File size validation
        validate_file_size(file_size, self.settings.max_file_size_bytes)

        # 2. Content hashing
        content_hash = compute_sha256(raw_bytes)

        # 3. Check for duplicates
        with self.engine.connection() as conn:
            existing = self.doc_repo.get_document_by_hash(conn, content_hash)
            if existing:
                raise ConflictError(
                    f"Document with identical content hash already exists (ID: {existing['id']})."
                )

        doc_id = str(uuid.uuid4())
        now = _utc_now_iso()

        # 4. Safe storage path resolution
        raw_filename = f"{content_hash}.txt"
        raw_path = validate_safe_path(Path(raw_filename), self.settings.storage_raw_dir)
        raw_path.write_bytes(raw_bytes)

        extracted_filename = f"{doc_id}.txt"
        extracted_path = validate_safe_path(Path(extracted_filename), self.settings.storage_extracted_dir)
        normalized_content = normalize_text(payload.raw_content)
        extracted_path.write_text(normalized_content, encoding="utf-8")

        # 5. Insert record in SQLite
        doc_dict = {
            "id": doc_id,
            "title": payload.title,
            "source_uri": payload.source_uri,
            "source_type": payload.source_type.value,
            "mime_type": payload.mime_type,
            "file_size_bytes": file_size,
            "content_hash": content_hash,
            "raw_storage_path": str(raw_path),
            "extracted_storage_path": str(extracted_path),
            "metadata_json": json.dumps(payload.metadata),
            "original_filename": f"{payload.title}.txt",
            "file_extension": ".txt",
            "ingestion_status": IngestionStatus.PROCESSED.value,
            "error_message": None,
            "chunk_count": 0,
            "created_at": now,
            "updated_at": now,
        }

        with self.engine.write_transaction() as conn:
            self.doc_repo.insert_document(conn, doc_dict)

        with self.engine.connection() as conn:
            row = self.doc_repo.get_document_by_id(conn, doc_id)
            return _row_to_document_response(row)

    def ingest_binary_document(
        self,
        filename: str,
        raw_bytes: bytes,
        title: Optional[str] = None,
        source_uri: Optional[str] = None,
        mime_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        chunk_options: Optional[ChunkOptions] = None,
    ) -> DocumentResponse:
        """Full document ingestion pipeline for binary files (PDF, DOCX, MD, TXT)."""
        file_size = len(raw_bytes)

        # 1. Size validation
        validate_file_size(file_size, self.settings.max_file_size_bytes)

        # 2. Content hashing
        content_hash = compute_sha256(raw_bytes)

        # 3. Duplicate check
        with self.engine.connection() as conn:
            existing = self.doc_repo.get_document_by_hash(conn, content_hash)
            if existing:
                raise ConflictError(
                    f"Document with identical content hash already exists (ID: {existing['id']})."
                )

        doc_id = str(uuid.uuid4())
        doc_title = title.strip() if title and title.strip() else Path(filename).stem
        ext = Path(filename).suffix.lower()
        if not ext:
            ext = ".txt"

        now = _utc_now_iso()
        options = chunk_options or ChunkOptions()
        meta = metadata or {}

        # Filesystem paths
        raw_filename = f"{content_hash}{ext}"
        raw_path = validate_safe_path(Path(raw_filename), self.settings.storage_raw_dir)
        extracted_filename = f"{doc_id}.txt"
        extracted_path = validate_safe_path(Path(extracted_filename), self.settings.storage_extracted_dir)

        files_written = []
        try:
            # 4. Save original bytes untouched
            raw_path.write_bytes(raw_bytes)
            files_written.append(raw_path)

            # 5. Resolve parser and extract text & structure
            parser = get_parser_for_file(filename=filename, mime_type=mime_type)
            extraction: ExtractionResult = parser.extract(raw_path, raw_bytes, filename)

            # 6. Normalize text
            normalized = normalize_text(extraction.text)
            extracted_path.write_text(normalized, encoding="utf-8")
            files_written.append(extracted_path)

            # Merge parser metadata
            meta.update(extraction.metadata)
            if extraction.warnings:
                meta["extraction_warnings"] = extraction.warnings

            # 7. Chunking
            chunker = get_chunker(
                strategy=options.strategy,
                chunk_size=options.chunk_size,
                chunk_overlap=options.chunk_overlap,
            )
            # Create a normalized extraction result for chunker
            normalized_extraction = ExtractionResult(
                text=normalized,
                elements=extraction.elements,
                extraction_method=extraction.extraction_method,
                warnings=extraction.warnings,
                metadata=extraction.metadata,
            )
            chunks: list[Chunk] = chunker.chunk(normalized_extraction)

            # Prepare chunk records
            chunk_dicts = []
            for c in chunks:
                c_hash = compute_sha256(c.chunk_text)
                chunk_dicts.append({
                    "id": str(uuid.uuid4()),
                    "document_id": doc_id,
                    "chunk_index": c.chunk_index,
                    "page_number": c.page_number,
                    "section": c.section,
                    "source_location": c.source_location,
                    "extraction_method": c.extraction_method,
                    "content_hash": c_hash,
                    "token_count": c.token_count,
                    "chunk_text": c.chunk_text,
                    "metadata_json": json.dumps(c.metadata),
                    "created_at": now,
                })

            # 8. Database atomic write
            doc_dict = {
                "id": doc_id,
                "title": doc_title,
                "source_uri": source_uri or filename,
                "source_type": DocumentSourceType.FILE.value,
                "mime_type": mime_type or "application/octet-stream",
                "file_size_bytes": file_size,
                "content_hash": content_hash,
                "raw_storage_path": str(raw_path),
                "extracted_storage_path": str(extracted_path),
                "original_filename": filename,
                "file_extension": ext,
                "ingestion_status": IngestionStatus.PROCESSED.value,
                "error_message": None,
                "chunk_count": len(chunk_dicts),
                "metadata_json": json.dumps(meta),
                "created_at": now,
                "updated_at": now,
            }

            # Prepare embedding records if provider is active
            embeddings_data = []
            if chunk_dicts and self.embedding_provider:
                texts = [c["chunk_text"] for c in chunk_dicts]
                vectors = self.embedding_provider.embed_documents(texts)
                for idx, c in enumerate(chunk_dicts):
                    embeddings_data.append({
                        "chunk_id": c["id"],
                        "model_name": self.embedding_provider.model_name,
                        "dimensions": self.embedding_provider.dimensions,
                        "embedding_blob": pack_vector(vectors[idx]),
                    })

            with self.engine.write_transaction() as conn:
                self.doc_repo.insert_document(conn, doc_dict)
                self.doc_repo.insert_chunks_bulk(conn, chunk_dicts)
                if embeddings_data:
                    self.retrieval_repo.insert_embeddings_bulk(conn, embeddings_data)

        except Exception as exc:
            # Clean up disk files on failure so no orphans remain
            for f in files_written:
                try:
                    if f.exists():
                        f.unlink()
                except Exception:
                    pass
            raise

        with self.engine.connection() as conn:
            row = self.doc_repo.get_document_by_id(conn, doc_id)
            return _row_to_document_response(row)

    def delete_document(self, doc_id: str) -> dict:
        """Delete document, cascade chunk deletion, and remove disk files."""
        with self.engine.connection() as conn:
            doc = self.doc_repo.get_document_by_id(conn, doc_id)
            if not doc:
                raise NotFoundError(f"Cannot delete document '{doc_id}': not found.")

        raw_path_str = doc["raw_storage_path"]
        extracted_path_str = doc["extracted_storage_path"]

        # 1. Delete from database inside transaction (cascades document_chunks)
        with self.engine.write_transaction() as conn:
            self.doc_repo.delete_document(conn, doc_id)

        # 2. Remove physical files safely
        for path_str in [raw_path_str, extracted_path_str]:
            if path_str:
                p = Path(path_str)
                try:
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass

        return {
            "document_id": doc_id,
            "deleted": True,
            "message": "Document record, chunks, and storage files successfully removed.",
        }

    def get_document_status(self, doc_id: str) -> DocumentStatusResponse:
        """Retrieve ingestion status, chunk count, and any processing errors."""
        with self.engine.connection() as conn:
            row = self.doc_repo.get_document_by_id(conn, doc_id)
            if not row:
                raise NotFoundError(f"Document with ID '{doc_id}' not found.")

            keys = row.keys()
            return DocumentStatusResponse(
                id=row["id"],
                title=row["title"],
                ingestion_status=IngestionStatus(row["ingestion_status"]) if "ingestion_status" in keys and row["ingestion_status"] else IngestionStatus.PROCESSED,
                chunk_count=row["chunk_count"] if "chunk_count" in keys and row["chunk_count"] is not None else 0,
                error_message=row["error_message"] if "error_message" in keys else None,
                content_hash=row["content_hash"],
                updated_at=row["updated_at"],
            )

    def list_documents(
        self,
        status: Optional[IngestionStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DocumentResponse]:
        """List documents with optional status filtering."""
        with self.engine.connection() as conn:
            rows = self.doc_repo.list_documents(
                conn=conn,
                status=status.value if status else None,
                limit=limit,
                offset=offset,
            )
            return [_row_to_document_response(row) for row in rows]

    def add_chunk(self, doc_id: str, payload: DocumentChunkCreate) -> DocumentChunkResponse:
        """Add a document chunk with deep retrieval provenance."""
        with self.engine.connection() as conn:
            doc = self.doc_repo.get_document_by_id(conn, doc_id)
            if not doc:
                raise NotFoundError(f"Cannot add chunk: parent document '{doc_id}' not found.")

        chunk_id = str(uuid.uuid4())
        now = _utc_now_iso()
        chunk_hash = compute_sha256(payload.chunk_text)

        chunk_dict = {
            "id": chunk_id,
            "document_id": doc_id,
            "chunk_index": payload.chunk_index,
            "page_number": payload.page_number,
            "section": payload.section,
            "source_location": payload.source_location,
            "extraction_method": payload.extraction_method,
            "content_hash": chunk_hash,
            "token_count": payload.token_count,
            "chunk_text": payload.chunk_text,
            "metadata_json": json.dumps(payload.metadata),
            "created_at": now,
        }

        with self.engine.write_transaction() as conn:
            self.doc_repo.insert_chunk(conn, chunk_dict)
            if self.embedding_provider:
                vec = self.embedding_provider.embed_query(payload.chunk_text)
                self.retrieval_repo.insert_embedding(
                    conn=conn,
                    chunk_id=chunk_id,
                    model_name=self.embedding_provider.model_name,
                    dimensions=self.embedding_provider.dimensions,
                    embedding_blob=pack_vector(vec),
                )

        return DocumentChunkResponse(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=payload.chunk_index,
            page_number=payload.page_number,
            section=payload.section,
            source_location=payload.source_location,
            extraction_method=payload.extraction_method,
            content_hash=chunk_hash,
            token_count=payload.token_count,
            chunk_text=payload.chunk_text,
            metadata=payload.metadata,
            created_at=now,
        )

    def get_document(self, doc_id: str) -> DocumentResponse:
        """Retrieve document by ID."""
        with self.engine.connection() as conn:
            row = self.doc_repo.get_document_by_id(conn, doc_id)
            if not row:
                raise NotFoundError(f"Document with ID '{doc_id}' not found.")
            return _row_to_document_response(row)

    def get_document_chunks(self, doc_id: str) -> list[DocumentChunkResponse]:
        """Retrieve all chunks with retrieval provenance for a document."""
        with self.engine.connection() as conn:
            doc = self.doc_repo.get_document_by_id(conn, doc_id)
            if not doc:
                raise NotFoundError(f"Document with ID '{doc_id}' not found.")
            rows = self.doc_repo.get_chunks_by_document_id(conn, doc_id)
            return [_row_to_chunk_response(row) for row in rows]
