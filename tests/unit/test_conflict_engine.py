"""Unit tests for MemoryConflictEngine heuristic detection rules and precedence."""

import pytest
from edith_brain.core.contracts import (
    MemoryConflictCheckRequest,
    ConflictType,
    MemoryCategory,
    PersonalSubcategory,
    MemoryCreate,
)
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.memory_conflict_engine import MemoryConflictEngine
from edith_brain.storage.db import SQLiteEngine


def test_conflict_engine_duplicate_detection(test_engine: SQLiteEngine):
    """Engine flags identical statements as POTENTIAL_DUPLICATE."""
    mem_service = MemoryService(engine=test_engine)
    conflict_engine = MemoryConflictEngine(engine=test_engine)

    # 1. Insert existing active preference
    mem_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="Prefers dark mode in all editors",
        )
    )

    # 2. Check duplicate candidate
    res = conflict_engine.check_conflicts(
        MemoryConflictCheckRequest(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="prefers dark mode in all editors",
        )
    )

    assert res.has_conflicts is True
    assert res.highest_severity_conflict == ConflictType.POTENTIAL_DUPLICATE
    assert len(res.conflicts) >= 1
    assert res.conflicts[0].conflict_type == ConflictType.POTENTIAL_DUPLICATE
    assert res.semantic_detection_available is False
    assert res.analysis_capability == "lexical_and_slot_only"
    assert res.conflicts[0].similarity_score is None


def test_conflict_engine_contradiction_detection(test_engine: SQLiteEngine):
    """Engine flags opposing slot values (antonyms) as POTENTIAL_CONTRADICTION."""
    mem_service = MemoryService(engine=test_engine)
    conflict_engine = MemoryConflictEngine(engine=test_engine)

    # 1. Insert existing active preference
    mem_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="Prefers dark mode for editors",
        )
    )

    # 2. Candidate asserts opposing light mode
    res = conflict_engine.check_conflicts(
        MemoryConflictCheckRequest(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="Prefers light mode for editors",
        )
    )

    assert res.has_conflicts is True
    assert res.highest_severity_conflict == ConflictType.POTENTIAL_CONTRADICTION
    assert any(c.conflict_type == ConflictType.POTENTIAL_CONTRADICTION for c in res.conflicts)


def test_conflict_engine_disjoint_slots_no_conflict(test_engine: SQLiteEngine):
    """Disjoint, non-conflicting statements report NO_CONFLICT_DETECTED without safety claims."""
    mem_service = MemoryService(engine=test_engine)
    conflict_engine = MemoryConflictEngine(engine=test_engine)

    mem_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="Prefers dark mode for editors",
        )
    )

    res = conflict_engine.check_conflicts(
        MemoryConflictCheckRequest(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="Drinks black coffee without sugar",
        )
    )

    assert res.has_conflicts is False
    assert res.highest_severity_conflict is None
    assert len(res.conflicts) == 0
    assert "NO_CONFLICT_DETECTED" in res.disclaimer
