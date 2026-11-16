"""Integration tests for memory associations graph, canonical ordering, and cycle detection."""

import pytest
from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryPurge,
    MemoryAssociationCreate,
    RelationType,
    MemoryCategory,
    PersonalSubcategory,
)
from edith_brain.core.exceptions import ValidationError
from edith_brain.services.memory_service import MemoryService
from edith_brain.storage.db import SQLiteEngine


def test_self_association_rejected(test_engine: SQLiteEngine):
    """Attempting to associate a memory to itself is rejected."""
    service = MemoryService(engine=test_engine)
    mem = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.GOAL,
            content="Self goal",
        )
    )

    with pytest.raises(ValidationError) as exc:
        service.add_association(
            source_memory_id=mem.id,
            payload=MemoryAssociationCreate(
                target_memory_id=mem.id,
                relation_type=RelationType.RELATES_TO,
            ),
        )
    assert "Self-associations are prohibited" in str(exc.value)


def test_relates_to_canonical_ordering_and_bidirectional_query(test_engine: SQLiteEngine):
    """relates_to canonicalizes source < target and queries find edges in either direction."""
    service = MemoryService(engine=test_engine)

    mem1 = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.SKILL,
            content="FastAPI proficiency",
        )
    )
    mem2 = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="Prefers Python for backend",
        )
    )

    # Add association
    assoc = service.add_association(
        source_memory_id=mem1.id,
        payload=MemoryAssociationCreate(
            target_memory_id=mem2.id,
            relation_type=RelationType.RELATES_TO,
        ),
    )
    assert assoc.relation_type == RelationType.RELATES_TO

    # Query from mem1
    assocs1 = service.get_associations(mem1.id)
    assert len(assocs1) == 1

    # Query from mem2 (bidirectional discovery)
    assocs2 = service.get_associations(mem2.id)
    assert len(assocs2) == 1
    assert assocs1[0].id == assocs2[0].id


def test_supersedes_multi_level_cycle_prevention(test_engine: SQLiteEngine):
    """Recursive cycle detection prevents multi-level supersession loops (A -> B -> C -> A)."""
    service = MemoryService(engine=test_engine)

    a = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.DECISION,
            content="Decision A",
        )
    )
    b = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.DECISION,
            content="Decision B",
        )
    )
    c = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.DECISION,
            content="Decision C",
        )
    )

    # 1. A supersedes B
    service.add_association(
        source_memory_id=a.id,
        payload=MemoryAssociationCreate(target_memory_id=b.id, relation_type=RelationType.SUPERSEDES),
    )

    # 2. B supersedes C
    service.add_association(
        source_memory_id=b.id,
        payload=MemoryAssociationCreate(target_memory_id=c.id, relation_type=RelationType.SUPERSEDES),
    )

    # 3. Attempt C supersedes A (cycle: C -> A -> B -> C)
    with pytest.raises(ValidationError) as exc:
        service.add_association(
            source_memory_id=c.id,
            payload=MemoryAssociationCreate(target_memory_id=a.id, relation_type=RelationType.SUPERSEDES),
        )
    assert "cycle detected" in str(exc.value).lower()


def test_association_cascade_on_memory_purge(test_engine: SQLiteEngine):
    """Purging either memory physically deletes associated graph edges."""
    service = MemoryService(engine=test_engine)

    mem1 = service.create_memory(
        MemoryCreate(category=MemoryCategory.PERSONAL, subcategory=PersonalSubcategory.GOAL, content="Goal 1")
    )
    mem2 = service.create_memory(
        MemoryCreate(category=MemoryCategory.PERSONAL, subcategory=PersonalSubcategory.GOAL, content="Goal 2")
    )

    service.add_association(
        source_memory_id=mem1.id,
        payload=MemoryAssociationCreate(target_memory_id=mem2.id, relation_type=RelationType.SUPPORTS),
    )
    assert len(service.get_associations(mem1.id)) == 1

    # Purge mem2
    service.purge_memory(mem2.id, MemoryPurge(reason="Deleted", confirm_permanent_loss=True))

    assert len(service.get_associations(mem1.id)) == 0
