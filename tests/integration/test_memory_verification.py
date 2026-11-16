"""Integration tests for memory verification state transitions, audit trail, and immutability triggers."""

import pytest
import sqlite3
from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCorrection,
    MemoryPurge,
    MemoryVerifyRequest,
    VerificationStatus,
    VerificationMethod,
    ActorRole,
    MemoryCategory,
    PersonalSubcategory,
)
from edith_brain.core.exceptions import ValidationError
from edith_brain.services.memory_service import MemoryService
from edith_brain.storage.db import SQLiteEngine


def test_verification_state_machine_valid_transitions(test_engine: SQLiteEngine):
    """Test standard progression: UNVERIFIED -> NEEDS_REVIEW -> VERIFIED."""
    service = MemoryService(engine=test_engine)

    # 1. Create memory (starts UNVERIFIED)
    mem = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT,
            content="Alex lives in Bangalore.",
        )
    )
    assert mem.verification_status == VerificationStatus.UNVERIFIED
    assert mem.verified_at is None

    # 2. Transition to NEEDS_REVIEW
    v1 = service.verify_memory(
        memory_id=mem.id,
        payload=MemoryVerifyRequest(
            status=VerificationStatus.NEEDS_REVIEW,
            method=VerificationMethod.SYSTEM_INFERRED,
            notes="Detected potential new address document.",
        ),
        actor=ActorRole.LOCAL_USER,
    )
    assert v1.verification_status == VerificationStatus.NEEDS_REVIEW
    assert v1.verified_at is None

    # 3. Transition to VERIFIED
    v2 = service.verify_memory(
        memory_id=mem.id,
        payload=MemoryVerifyRequest(
            status=VerificationStatus.VERIFIED,
            method=VerificationMethod.USER_CONFIRMED,
            notes="Confirmed by user during interview.",
        ),
        actor=ActorRole.LOCAL_USER,
    )
    assert v2.verification_status == VerificationStatus.VERIFIED
    assert v2.verified_at is not None

    # 4. Check verification history trail
    history = service.get_verification_history(mem.id)
    assert len(history) == 2
    assert history[0].new_status == VerificationStatus.NEEDS_REVIEW
    assert history[1].new_status == VerificationStatus.VERIFIED


def test_prohibited_verification_transitions(test_engine: SQLiteEngine):
    """Direct transition from REJECTED to VERIFIED without review is rejected."""
    service = MemoryService(engine=test_engine)

    mem = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PREFERENCE,
            content="Prefers light mode",
        )
    )

    # Transition to REJECTED
    service.verify_memory(
        memory_id=mem.id,
        payload=MemoryVerifyRequest(
            status=VerificationStatus.REJECTED,
            method=VerificationMethod.USER_CONFIRMED,
            notes="User explicitly denied this preference.",
        ),
    )

    # Prohibited jump: REJECTED -> VERIFIED
    with pytest.raises(ValidationError) as exc:
        service.verify_memory(
            memory_id=mem.id,
            payload=MemoryVerifyRequest(
                status=VerificationStatus.VERIFIED,
                method=VerificationMethod.USER_CONFIRMED,
            ),
        )
    assert "rejected" in str(exc.value) and "verified" in str(exc.value)

    # Prohibited self-transition: REJECTED -> REJECTED
    with pytest.raises(ValidationError) as exc_self:
        service.verify_memory(
            memory_id=mem.id,
            payload=MemoryVerifyRequest(
                status=VerificationStatus.REJECTED,
                method=VerificationMethod.USER_CONFIRMED,
            ),
        )
    assert "identical state" in str(exc_self.value)


def test_corrected_memory_receives_unverified_status(test_engine: SQLiteEngine):
    """Corrected replacement memories never inherit verification status."""
    service = MemoryService(engine=test_engine)

    mem = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT,
            content="Alex is 28 years old.",
        )
    )
    # Verify the initial memory
    service.verify_memory(
        memory_id=mem.id,
        payload=MemoryVerifyRequest(
            status=VerificationStatus.VERIFIED,
            method=VerificationMethod.USER_CONFIRMED,
        ),
    )

    # Correct memory to 29 years old
    corrected = service.correct_memory(
        memory_id=mem.id,
        payload=MemoryCorrection(
            new_content="Alex is 29 years old.",
            reason="Birthday passed",
        ),
    )

    # New memory must be UNVERIFIED
    assert corrected.verification_status == VerificationStatus.UNVERIFIED
    assert corrected.verified_at is None


def test_verification_history_append_only_trigger(test_engine: SQLiteEngine):
    """Database trigger trg_no_update_memory_verifications prevents UPDATE on verification rows."""
    service = MemoryService(engine=test_engine)

    mem = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT,
            content="Test statement",
        )
    )
    service.verify_memory(
        memory_id=mem.id,
        payload=MemoryVerifyRequest(
            status=VerificationStatus.VERIFIED,
            method=VerificationMethod.USER_CONFIRMED,
        ),
    )

    with test_engine.write_transaction() as conn:
        with pytest.raises(sqlite3.IntegrityError) as exc:
            conn.execute("UPDATE memory_verifications SET notes = 'tampered' WHERE memory_id = ?", (mem.id,))
        assert "append-only" in str(exc.value).lower()


def test_verification_history_purged_on_memory_hard_purge(test_engine: SQLiteEngine):
    """Hard purge of parent memory cascades cleanly to remove verification rows."""
    service = MemoryService(engine=test_engine)

    mem = service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT,
            content="Sensitive medical fact",
        )
    )
    service.verify_memory(
        memory_id=mem.id,
        payload=MemoryVerifyRequest(
            status=VerificationStatus.VERIFIED,
            method=VerificationMethod.USER_CONFIRMED,
            notes="Confirmed with doctor note",
        ),
    )

    # Purge memory
    service.purge_memory(mem.id, MemoryPurge(reason="User privacy request", confirm_permanent_loss=True))

    with test_engine.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM memory_verifications WHERE memory_id = ?", (mem.id,))
        assert cursor.fetchone()["count"] == 0
