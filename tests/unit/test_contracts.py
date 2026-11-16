"""Unit tests for Pydantic domain models and contracts."""

import pytest
from pydantic import ValidationError

from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCorrection,
    MemoryRevoke,
    MemoryPurge,
    MemoryCategory,
    PersonalSubcategory,
    SourceType,
    DocumentCreate,
    DocumentChunkCreate,
)


def test_personal_memory_requires_subcategory():
    """Personal category must specify a valid subcategory."""
    with pytest.raises(ValidationError) as exc_info:
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            content="I am a senior Python engineer.",
            # subcategory omitted
        )
    assert "Subcategory is required when memory category is 'personal'" in str(exc_info.value)


def test_personal_memory_with_valid_subcategory():
    """Personal category with valid subcategory succeeds."""
    mem = MemoryCreate(
        category=MemoryCategory.PERSONAL,
        subcategory=PersonalSubcategory.PROFILE_FACT,
        content="User lives in Bangalore.",
        confidence=1.0,
    )
    assert mem.category == MemoryCategory.PERSONAL
    assert mem.subcategory == PersonalSubcategory.PROFILE_FACT
    assert mem.content == "User lives in Bangalore."


def test_non_personal_memory_rejects_subcategory():
    """Non-personal categories must NOT specify a personal subcategory."""
    with pytest.raises(ValidationError) as exc_info:
        MemoryCreate(
            category=MemoryCategory.SEMANTIC,
            subcategory=PersonalSubcategory.SKILL,
            content="Python 3.13 was released in 2024.",
        )
    assert "only permitted for 'personal' memories" in str(exc_info.value)


def test_memory_confidence_range_validation():
    """Confidence must strictly be between 0.0 and 1.0."""
    with pytest.raises(ValidationError):
        MemoryCreate(
            category=MemoryCategory.SEMANTIC,
            content="Testing",
            confidence=1.5,
        )

    with pytest.raises(ValidationError):
        MemoryCreate(
            category=MemoryCategory.SEMANTIC,
            content="Testing",
            confidence=-0.1,
        )


def test_memory_purge_requires_confirmation_flag():
    """MemoryPurge must have confirm_permanent_loss=True."""
    with pytest.raises(ValidationError) as exc_info:
        MemoryPurge(
            reason="User requested removal",
            confirm_permanent_loss=False,
        )
    assert "confirm_permanent_loss must be set to True" in str(exc_info.value)


def test_document_contracts_validation():
    """Document and chunk validation."""
    doc = DocumentCreate(
        title="Architecture Guide",
        raw_content="This is the raw content of the guide.",
    )
    assert doc.title == "Architecture Guide"

    chunk = DocumentChunkCreate(
        chunk_index=0,
        chunk_text="This is chunk zero.",
        page_number=1,
        section="Introduction",
    )
    assert chunk.chunk_index == 0
    assert chunk.page_number == 1
