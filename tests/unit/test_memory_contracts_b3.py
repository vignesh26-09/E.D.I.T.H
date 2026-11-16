"""Unit tests for B3 Pydantic v2 domain contracts and validation constraints."""

import pytest
from pydantic import ValidationError

from edith_brain.core.contracts import (
    VerificationStatus,
    VerificationMethod,
    ActorRole,
    RelationType,
    CitationStatus,
    ConflictType,
    MemoryVerifyRequest,
    MemoryCitationCreate,
    MemoryAssociationCreate,
    MemoryConflictCheckRequest,
    MemoryCategory,
    PersonalSubcategory,
)


def test_verification_status_enums():
    """Verify all verification status values exist as closed enum."""
    assert VerificationStatus.UNVERIFIED == "unverified"
    assert VerificationStatus.NEEDS_REVIEW == "needs_review"
    assert VerificationStatus.VERIFIED == "verified"
    assert VerificationStatus.REJECTED == "rejected"


def test_verification_method_enums():
    """Verify all verification method values exist as closed enum."""
    assert VerificationMethod.USER_CONFIRMED == "user_confirmed"
    assert VerificationMethod.DOCUMENT_SUPPORTED == "document_supported"
    assert VerificationMethod.EXTERNALLY_VERIFIED == "externally_verified"
    assert VerificationMethod.SYSTEM_INFERRED == "system_inferred"


def test_citation_create_requires_doc_or_chunk():
    """Citation must specify at least document_id or chunk_id."""
    with pytest.raises(ValidationError):
        MemoryCitationCreate(document_id=None, chunk_id=None)

    valid1 = MemoryCitationCreate(document_id="doc-123")
    assert valid1.document_id == "doc-123"

    valid2 = MemoryCitationCreate(chunk_id="chunk-456")
    assert valid2.chunk_id == "chunk-456"


def test_association_create_validates():
    """Association validates relation type and target."""
    assoc = MemoryAssociationCreate(target_memory_id="mem-target", relation_type=RelationType.RELATES_TO)
    assert assoc.target_memory_id == "mem-target"
    assert assoc.relation_type == RelationType.RELATES_TO


def test_conflict_check_request_validation():
    """Conflict request validates thresholds and category."""
    req = MemoryConflictCheckRequest(
        content="I love Python",
        category=MemoryCategory.PERSONAL,
        subcategory=PersonalSubcategory.PREFERENCE,
        duplicate_threshold=0.9,
        contradiction_threshold=0.7,
    )
    assert req.duplicate_threshold == 0.9
    assert req.contradiction_threshold == 0.7
