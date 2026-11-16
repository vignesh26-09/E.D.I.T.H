"""Integration tests for memory lifecycle: creation, correction, revocation, and purge redaction."""

import pytest
from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCorrection,
    MemoryRevoke,
    MemoryPurge,
    MemoryCategory,
    PersonalSubcategory,
    MemoryStatus,
)
from edith_brain.core.exceptions import NotFoundError, ValidationError
from edith_brain.services.memory_service import MemoryService
from edith_brain.storage.db import SQLiteEngine


def test_personal_memory_creation_and_subcategories(memory_service: MemoryService):
    """Create personal memories with all 6 supported subcategories."""
    subcategories = [
        PersonalSubcategory.PROFILE_FACT,
        PersonalSubcategory.PREFERENCE,
        PersonalSubcategory.GOAL,
        PersonalSubcategory.SKILL,
        PersonalSubcategory.PROJECT_CONTEXT,
        PersonalSubcategory.DECISION,
    ]

    for sub in subcategories:
        created = memory_service.create_memory(
            MemoryCreate(
                category=MemoryCategory.PERSONAL,
                subcategory=sub,
                content=f"Test content for {sub.value}",
                confidence=0.95,
                tags=[sub.value, "automated-test"],
            )
        )
        assert created.category == MemoryCategory.PERSONAL
        assert created.subcategory == sub
        assert created.status == MemoryStatus.ACTIVE

        # Verify audit trail
        trail = memory_service.get_audit_trail(created.id)
        assert len(trail) == 1
        assert trail[0].action == "created"


def test_memory_correction_preserves_lineage(memory_service: MemoryService):
    """Correcting a memory marks predecessor superseded and links lineage."""
    original = memory_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="User prefers light theme.",
            confidence=0.8,
        )
    )

    corrected = memory_service.correct_memory(
        original.id,
        MemoryCorrection(
            new_content="User prefers dark theme with high contrast.",
            confidence=1.0,
            reason="User explicitly requested dark mode in settings.",
        ),
    )

    # 1. New memory must be active and point to parent
    assert corrected.status == MemoryStatus.ACTIVE
    assert corrected.content == "User prefers dark theme with high contrast."
    assert corrected.parent_memory_id == original.id

    # 2. Original memory must now be superseded
    superseded = memory_service.get_memory(original.id)
    assert superseded.status == MemoryStatus.SUPERSEDED

    # 3. Check audit trails
    parent_trail = memory_service.get_audit_trail(original.id)
    assert any(entry.action == "superseded" for entry in parent_trail)

    child_trail = memory_service.get_audit_trail(corrected.id)
    assert any(entry.action == "corrected" for entry in child_trail)


def test_memory_revocation(memory_service: MemoryService):
    """Revoking deactivates a memory while retaining non-sensitive audit metadata."""
    mem = memory_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.SEMANTIC,
            content="Temporary fact to be revoked.",
            confidence=0.7,
        )
    )

    revoked = memory_service.revoke_memory(
        mem.id,
        MemoryRevoke(reason="Information was retracted by source."),
    )

    assert revoked.status == MemoryStatus.REVOKED

    # Should not show in active memory list
    active_memories = memory_service.list_memories(status=MemoryStatus.ACTIVE)
    assert all(m.id != mem.id for m in active_memories)

    # Audit trail captures revocation
    trail = memory_service.get_audit_trail(mem.id)
    assert len(trail) == 2
    assert trail[1].action == "revoked"
    assert "retracted by source" in trail[1].change_reason


def test_memory_permanent_purge_and_audit_redaction(
    memory_service: MemoryService,
    test_engine: SQLiteEngine,
):
    """Permanent purge physically deletes memory and redacts sensitive personal content from audit logs."""
    sensitive_text = "Highly private secret personal memory text 12345"
    mem = memory_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT,
            content=sensitive_text,
            confidence=1.0,
        )
    )

    # Make a correction to create multiple historical snapshots in audit log
    corrected = memory_service.correct_memory(
        mem.id,
        MemoryCorrection(
            new_content=sensitive_text + " revised",
            confidence=1.0,
            reason="Minor typo update",
        ),
    )

    # Execute permanent purge on the original memory
    purge_result = memory_service.purge_memory(
        mem.id,
        MemoryPurge(reason="GDPR right to be forgotten request", confirm_permanent_loss=True),
    )
    assert purge_result["purged"] is True

    # 1. Assert memory is no longer found in memories table
    with pytest.raises(NotFoundError):
        memory_service.get_memory(mem.id)

    # 2. Assert raw SQL query finds 0 rows for this memory in memories table
    with test_engine.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM memories WHERE id = ?;", (mem.id,))
        assert cursor.fetchone()[0] == 0

    # 3. Assert ALL audit snapshots for this memory have sensitive content REDACTED
    with test_engine.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT action, change_reason, previous_state_json FROM memory_audit_log WHERE memory_id = ?;", (mem.id,))
        rows = cursor.fetchall()
        assert len(rows) >= 2

        for row in rows:
            # Sensitive text must NOT appear anywhere in the database row
            assert sensitive_text not in (row["previous_state_json"] or "")
            if row["action"] == "superseded":
                assert row["previous_state_json"] == "[REDACTED_PURGED]"
            if row["action"] == "purged":
                assert row["previous_state_json"] is None
