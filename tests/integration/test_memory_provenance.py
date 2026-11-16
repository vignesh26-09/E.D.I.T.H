"""Integration tests for memory document citations, parentage validation, and deletion lifecycle."""

import pytest
from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryPurge,
    MemoryCitationCreate,
    CitationStatus,
    MemoryCategory,
    PersonalSubcategory,
)
from edith_brain.core.exceptions import ValidationError, NotFoundError
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.document_service import DocumentService
from edith_brain.storage.db import SQLiteEngine
from edith_brain.core.config import Settings
from edith_brain.services.retrieval.embeddings import BaseEmbeddingProvider


def test_citation_parentage_validation(
    test_engine: SQLiteEngine,
    test_settings: Settings,
    test_embedding_provider: BaseEmbeddingProvider,
):
    """Parentage check asserts chunk belongs to document; rejects cross-document links."""
    mem_service = MemoryService(engine=test_engine)
    doc_service = DocumentService(engine=test_engine, settings=test_settings, embedding_provider=test_embedding_provider)

    # 1. Ingest two documents
    doc1 = doc_service.ingest_binary_document(
        filename="resume.txt",
        raw_bytes=b"Alex has 8 years experience as Python backend engineer.",
    )
    doc2 = doc_service.ingest_binary_document(
        filename="project.txt",
        raw_bytes=b"Project EDITH architecture overview and principles.",
    )

    chunks1 = doc_service.get_document_chunks(doc1.id)
    chunks2 = doc_service.get_document_chunks(doc2.id)

    # 2. Create memory
    mem = mem_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT,
            content="Alex has 8 years experience.",
        )
    )

    # Valid parentage
    citation = mem_service.add_citation(
        memory_id=mem.id,
        payload=MemoryCitationCreate(
            document_id=doc1.id,
            chunk_id=chunks1[0].id,
            quote_text="Alex has 8 years experience",
        ),
    )
    assert citation.citation_status == CitationStatus.VALID
    assert citation.document_id == doc1.id
    assert citation.chunk_id == chunks1[0].id
    assert citation.historical_document_id == doc1.id

    # Invalid cross-document parentage (doc1 with chunk from doc2)
    with pytest.raises(ValidationError) as exc:
        mem_service.add_citation(
            memory_id=mem.id,
            payload=MemoryCitationCreate(
                document_id=doc1.id,
                chunk_id=chunks2[0].id,
            ),
        )
    assert "belongs to document" in str(exc.value)


def test_document_deletion_transitions_citation_to_source_removed(
    test_engine: SQLiteEngine,
    test_settings: Settings,
    test_embedding_provider: BaseEmbeddingProvider,
):
    """Deleting a document sets document_id NULL and transitions citation_status to source_removed."""
    mem_service = MemoryService(engine=test_engine)
    doc_service = DocumentService(engine=test_engine, settings=test_settings, embedding_provider=test_embedding_provider)

    doc = doc_service.ingest_binary_document(
        filename="contract.txt",
        raw_bytes=b"Hourly consulting rate is 150 USD per hour.",
    )
    chunks = doc_service.get_document_chunks(doc.id)

    mem = mem_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT,
            content="Consulting rate is 150 USD.",
        )
    )

    cit = mem_service.add_citation(
        memory_id=mem.id,
        payload=MemoryCitationCreate(
            document_id=doc.id,
            chunk_id=chunks[0].id,
            quote_text="Hourly consulting rate is 150 USD",
        ),
    )
    assert cit.citation_status == CitationStatus.VALID

    # Delete the document
    doc_service.delete_document(doc.id)

    # Retrieve citations: document_id is NULL, status is source_removed, historical ref preserved
    citations = mem_service.get_citations(mem.id)
    assert len(citations) == 1
    assert citations[0].document_id is None
    assert citations[0].citation_status == CitationStatus.SOURCE_REMOVED
    assert citations[0].historical_document_id == doc.id
    assert citations[0].quote_text == "Hourly consulting rate is 150 USD"


def test_memory_hard_purge_cascades_to_citations(
    test_engine: SQLiteEngine,
    test_settings: Settings,
    test_embedding_provider: BaseEmbeddingProvider,
):
    """Purging memory deletes all citation records physically."""
    mem_service = MemoryService(engine=test_engine)
    doc_service = DocumentService(engine=test_engine, settings=test_settings, embedding_provider=test_embedding_provider)

    doc = doc_service.ingest_binary_document(
        filename="notes.txt",
        raw_bytes=b"Personal notes about sensitive goals.",
    )
    mem = mem_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.GOAL,
            content="Sensitive goal",
        )
    )
    mem_service.add_citation(
        memory_id=mem.id,
        payload=MemoryCitationCreate(document_id=doc.id, quote_text="Sensitive goals"),
    )

    # Hard purge memory
    mem_service.purge_memory(mem.id, MemoryPurge(reason="Privacy request", confirm_permanent_loss=True))

    with test_engine.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS c FROM memory_citations WHERE memory_id = ?", (mem.id,))
        assert cursor.fetchone()["c"] == 0
