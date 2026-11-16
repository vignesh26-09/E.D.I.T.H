"""Memory domain service orchestrating lifecycle, verification, citations, associations, and privacy purge."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from edith_brain.core.contracts import (
    MemoryCreate,
    MemoryCorrection,
    MemoryRevoke,
    MemoryPurge,
    MemoryResponse,
    MemoryAuditRecordResponse,
    MemoryCategory,
    MemoryStatus,
    VerificationStatus,
    VerificationMethod,
    ActorRole,
    MemoryVerifyRequest,
    MemoryVerificationResponse,
    MemoryCitationCreate,
    MemoryCitationResponse,
    CitationStatus,
    MemoryAssociationCreate,
    MemoryAssociationResponse,
    RelationType,
)
from edith_brain.core.exceptions import NotFoundError, ValidationError
from edith_brain.core.security import compute_sha256
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.memory_repository import MemoryRepository
from edith_brain.repositories.audit_repository import MemoryAuditRepository
from edith_brain.repositories.memory_verification_repository import MemoryVerificationRepository
from edith_brain.repositories.memory_citation_repository import MemoryCitationRepository
from edith_brain.repositories.memory_association_repository import MemoryAssociationRepository
from edith_brain.repositories.memory_embedding_repository import MemoryEmbeddingRepository


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_memory_response(row) -> MemoryResponse:
    keys = row.keys() if hasattr(row, "keys") else []
    v_status = row["verification_status"] if "verification_status" in keys and row["verification_status"] else "unverified"
    v_method = row["verification_method"] if "verification_method" in keys and row["verification_method"] else "system_inferred"
    c_hash = row["content_hash"] if "content_hash" in keys else None

    return MemoryResponse(
        id=row["id"],
        category=MemoryCategory(row["category"]),
        subcategory=row["subcategory"],
        content=row["content"],
        confidence=row["confidence"],
        source_type=row["source_type"],
        source_reference_id=row["source_reference_id"],
        status=MemoryStatus(row["status"]),
        parent_memory_id=row["parent_memory_id"],
        tags=json.loads(row["tags_json"]),
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        verified_at=row["verified_at"],
        verification_status=VerificationStatus(v_status),
        verification_method=VerificationMethod(v_method),
        content_hash=c_hash,
    )


class MemoryService:
    """Encapsulates memory business rules, verification transitions, citations, and privacy sanitization."""

    def __init__(
        self,
        engine: SQLiteEngine,
        memory_repo: MemoryRepository | None = None,
        audit_repo: MemoryAuditRepository | None = None,
        verification_repo: MemoryVerificationRepository | None = None,
        citation_repo: MemoryCitationRepository | None = None,
        association_repo: MemoryAssociationRepository | None = None,
        embedding_repo: MemoryEmbeddingRepository | None = None,
    ) -> None:
        self.engine = engine
        self.memory_repo = memory_repo or MemoryRepository()
        self.audit_repo = audit_repo or MemoryAuditRepository()
        self.verification_repo = verification_repo or MemoryVerificationRepository()
        self.citation_repo = citation_repo or MemoryCitationRepository()
        self.association_repo = association_repo or MemoryAssociationRepository()
        self.embedding_repo = embedding_repo or MemoryEmbeddingRepository()

    def create_memory(self, payload: MemoryCreate) -> MemoryResponse:
        """Create and persist a new structured memory with an audit event and canonical hash."""
        now = _utc_now_iso()
        memory_id = str(uuid.uuid4())
        content_hash = compute_sha256(payload.content)

        # Inferred / extracted statements default to unverified
        initial_status = VerificationStatus.UNVERIFIED.value
        initial_method = VerificationMethod.SYSTEM_INFERRED.value

        memory_dict = {
            "id": memory_id,
            "category": payload.category.value,
            "subcategory": payload.subcategory.value if payload.subcategory else None,
            "content": payload.content,
            "confidence": payload.confidence,
            "source_type": payload.source_type.value,
            "source_reference_id": payload.source_reference_id,
            "status": MemoryStatus.ACTIVE.value,
            "parent_memory_id": None,
            "tags_json": json.dumps(payload.tags),
            "metadata_json": json.dumps(payload.metadata),
            "created_at": now,
            "updated_at": now,
            "verified_at": None,
            "verification_status": initial_status,
            "verification_method": initial_method,
            "content_hash": content_hash,
        }

        with self.engine.write_transaction() as conn:
            self.memory_repo.insert(conn, memory_dict)
            self.audit_repo.insert_entry(
                conn=conn,
                memory_id=memory_id,
                action="created",
                change_reason="Initial memory creation",
                previous_state_json=None,
            )

        with self.engine.connection() as conn:
            row = self.memory_repo.get_by_id(conn, memory_id)
            return _row_to_memory_response(row)

    def get_memory(self, memory_id: str) -> MemoryResponse:
        """Fetch memory by ID or raise NotFoundError."""
        with self.engine.connection() as conn:
            row = self.memory_repo.get_by_id(conn, memory_id)
            if not row:
                raise NotFoundError(f"Memory with ID '{memory_id}' not found.")
            return _row_to_memory_response(row)

    def correct_memory(self, memory_id: str, payload: MemoryCorrection) -> MemoryResponse:
        """Correct a memory: supersedes predecessor and creates a new memory with unverified state."""
        now = _utc_now_iso()
        new_memory_id = str(uuid.uuid4())
        new_content_hash = compute_sha256(payload.new_content)

        with self.engine.write_transaction() as conn:
            existing = self.memory_repo.get_by_id(conn, memory_id)
            if not existing:
                raise NotFoundError(f"Cannot correct non-existent memory '{memory_id}'.")
            if existing["status"] == MemoryStatus.REVOKED.value:
                raise ValidationError(f"Cannot correct revoked memory '{memory_id}'.")

            old_snapshot = json.dumps(dict(existing))

            # Mark existing as superseded
            self.memory_repo.update_status(
                conn=conn,
                memory_id=memory_id,
                new_status=MemoryStatus.SUPERSEDED.value,
                updated_at=now,
            )
            self.audit_repo.insert_entry(
                conn=conn,
                memory_id=memory_id,
                action="superseded",
                change_reason=f"Superseded by correction {new_memory_id}: {payload.reason}",
                previous_state_json=old_snapshot,
            )

            # Insert corrected replacement (fresh unverified state, never inherits verification)
            new_tags = payload.tags if payload.tags is not None else json.loads(existing["tags_json"])
            new_metadata = payload.metadata if payload.metadata is not None else json.loads(existing["metadata_json"])

            new_memory_dict = {
                "id": new_memory_id,
                "category": existing["category"],
                "subcategory": existing["subcategory"],
                "content": payload.new_content,
                "confidence": payload.confidence,
                "source_type": existing["source_type"],
                "source_reference_id": existing["source_reference_id"],
                "status": MemoryStatus.ACTIVE.value,
                "parent_memory_id": memory_id,
                "tags_json": json.dumps(new_tags),
                "metadata_json": json.dumps(new_metadata),
                "created_at": now,
                "updated_at": now,
                "verified_at": None,
                "verification_status": VerificationStatus.UNVERIFIED.value,
                "verification_method": VerificationMethod.SYSTEM_INFERRED.value,
                "content_hash": new_content_hash,
            }
            self.memory_repo.insert(conn, new_memory_dict)
            self.audit_repo.insert_entry(
                conn=conn,
                memory_id=new_memory_id,
                action="corrected",
                change_reason=f"Corrected from {memory_id}: {payload.reason}",
                previous_state_json=None,
            )

        with self.engine.connection() as conn:
            new_row = self.memory_repo.get_by_id(conn, new_memory_id)
            return _row_to_memory_response(new_row)

    def verify_memory(
        self,
        memory_id: str,
        payload: MemoryVerifyRequest,
        actor: ActorRole = ActorRole.LOCAL_USER,
    ) -> MemoryResponse:
        """Execute a state-machine governed verification transition with immutable audit log."""
        now = _utc_now_iso()

        valid_transitions = {
            (VerificationStatus.UNVERIFIED, VerificationStatus.VERIFIED),
            (VerificationStatus.UNVERIFIED, VerificationStatus.NEEDS_REVIEW),
            (VerificationStatus.UNVERIFIED, VerificationStatus.REJECTED),
            (VerificationStatus.NEEDS_REVIEW, VerificationStatus.VERIFIED),
            (VerificationStatus.NEEDS_REVIEW, VerificationStatus.REJECTED),
            (VerificationStatus.VERIFIED, VerificationStatus.NEEDS_REVIEW),
            (VerificationStatus.VERIFIED, VerificationStatus.REJECTED),
            (VerificationStatus.REJECTED, VerificationStatus.NEEDS_REVIEW),
        }

        with self.engine.write_transaction() as conn:
            existing = self.memory_repo.get_by_id(conn, memory_id)
            if not existing:
                raise NotFoundError(f"Memory with ID '{memory_id}' not found.")

            curr_status_str = existing["verification_status"] or "unverified"
            current_status = VerificationStatus(curr_status_str)
            target_status = payload.status

            if current_status == target_status:
                raise ValidationError(f"Cannot transition verification status to identical state '{target_status.value}'.")

            if current_status == VerificationStatus.REJECTED and target_status == VerificationStatus.VERIFIED:
                raise ValidationError(
                    "Cannot transition directly from 'rejected' to 'verified'. Must transition through 'needs_review' first."
                )

            if (current_status, target_status) not in valid_transitions:
                raise ValidationError(
                    f"Invalid verification transition from '{current_status.value}' to '{target_status.value}'."
                )

            # Actor & method validation
            if target_status == VerificationStatus.VERIFIED and payload.method == VerificationMethod.USER_CONFIRMED:
                if actor != ActorRole.LOCAL_USER:
                    raise ValidationError("Only LOCAL_USER can verify memories with method 'user_confirmed'.")

            if current_status == VerificationStatus.REJECTED and target_status == VerificationStatus.NEEDS_REVIEW:
                if not payload.notes or not payload.notes.strip():
                    raise ValidationError("Transitioning from 'rejected' to 'needs_review' requires an explicit rationale in notes.")

            verified_at = now if target_status == VerificationStatus.VERIFIED else None

            # 1. Update memory record
            self.memory_repo.update_verification(
                conn=conn,
                memory_id=memory_id,
                verification_status=target_status.value,
                verification_method=payload.method.value,
                verified_at=verified_at,
                updated_at=now,
            )

            # 2. Append immutable verification event
            self.verification_repo.insert_verification(
                conn=conn,
                memory_id=memory_id,
                previous_status=current_status.value,
                new_status=target_status.value,
                verification_method=payload.method.value,
                verifier_actor=actor.value,
                notes=payload.notes,
                created_at=now,
            )

            # 3. Append to memory audit log
            self.audit_repo.insert_entry(
                conn=conn,
                memory_id=memory_id,
                action="verified",
                change_reason=f"Verification status transitioned to {target_status.value} via {payload.method.value} by {actor.value}",
                previous_state_json=json.dumps({"verification_status": current_status.value}),
            )

        with self.engine.connection() as conn:
            updated_row = self.memory_repo.get_by_id(conn, memory_id)
            return _row_to_memory_response(updated_row)

    def get_verification_history(self, memory_id: str) -> list[MemoryVerificationResponse]:
        """Fetch immutable verification audit trail for a memory."""
        with self.engine.connection() as conn:
            if not self.memory_repo.get_by_id(conn, memory_id):
                raise NotFoundError(f"Memory with ID '{memory_id}' not found.")
            rows = self.verification_repo.get_history(conn, memory_id)
            return [
                MemoryVerificationResponse(
                    id=r["id"],
                    memory_id=r["memory_id"],
                    previous_status=VerificationStatus(r["previous_status"]) if r["previous_status"] else None,
                    new_status=VerificationStatus(r["new_status"]),
                    verification_method=VerificationMethod(r["verification_method"]),
                    verifier_actor=ActorRole(r["verifier_actor"]),
                    notes=r["notes"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def add_citation(self, memory_id: str, payload: MemoryCitationCreate) -> MemoryCitationResponse:
        """Link a memory to supporting document or chunk provenance with parentage validation."""
        now = _utc_now_iso()
        citation_id = str(uuid.uuid4())

        with self.engine.write_transaction() as conn:
            if not self.memory_repo.get_by_id(conn, memory_id):
                raise NotFoundError(f"Memory with ID '{memory_id}' not found.")

            doc_id, chunk_id = self.citation_repo.validate_parentage(
                conn=conn,
                document_id=payload.document_id,
                chunk_id=payload.chunk_id,
            )

            # Preserve permanent historical source identifiers
            citation_dict = {
                "id": citation_id,
                "memory_id": memory_id,
                "document_id": doc_id,
                "chunk_id": chunk_id,
                "historical_document_id": doc_id,
                "historical_chunk_id": chunk_id,
                "citation_status": CitationStatus.VALID.value,
                "quote_text": payload.quote_text,
                "confidence_score": payload.confidence_score,
                "metadata_json": json.dumps(payload.metadata),
                "created_at": now,
            }
            self.citation_repo.insert(conn, citation_dict)

        with self.engine.connection() as conn:
            row = self.citation_repo.get_by_id(conn, citation_id)
            return MemoryCitationResponse(
                id=row["id"],
                memory_id=row["memory_id"],
                document_id=row["document_id"],
                chunk_id=row["chunk_id"],
                historical_document_id=row["historical_document_id"],
                historical_chunk_id=row["historical_chunk_id"],
                citation_status=CitationStatus(row["citation_status"]),
                quote_text=row["quote_text"],
                confidence_score=row["confidence_score"],
                metadata=json.loads(row["metadata_json"]),
                created_at=row["created_at"],
            )

    def get_citations(self, memory_id: str) -> list[MemoryCitationResponse]:
        """Fetch all citations for a given memory."""
        with self.engine.connection() as conn:
            if not self.memory_repo.get_by_id(conn, memory_id):
                raise NotFoundError(f"Memory with ID '{memory_id}' not found.")
            rows = self.citation_repo.get_by_memory_id(conn, memory_id)
            return [
                MemoryCitationResponse(
                    id=r["id"],
                    memory_id=r["memory_id"],
                    document_id=r["document_id"],
                    chunk_id=r["chunk_id"],
                    historical_document_id=r["historical_document_id"],
                    historical_chunk_id=r["historical_chunk_id"],
                    citation_status=CitationStatus(r["citation_status"]),
                    quote_text=r["quote_text"],
                    confidence_score=r["confidence_score"],
                    metadata=json.loads(r["metadata_json"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def add_association(
        self,
        source_memory_id: str,
        payload: MemoryAssociationCreate,
    ) -> MemoryAssociationResponse:
        """Create an association edge between two memories with cycle and canonical checks."""
        now = _utc_now_iso()
        assoc_id = str(uuid.uuid4())

        with self.engine.write_transaction() as conn:
            if not self.memory_repo.get_by_id(conn, source_memory_id):
                raise NotFoundError(f"Source memory with ID '{source_memory_id}' not found.")
            if not self.memory_repo.get_by_id(conn, payload.target_memory_id):
                raise NotFoundError(f"Target memory with ID '{payload.target_memory_id}' not found.")

            assoc_dict = {
                "id": assoc_id,
                "source_memory_id": source_memory_id,
                "target_memory_id": payload.target_memory_id,
                "relation_type": payload.relation_type.value,
                "metadata_json": json.dumps(payload.metadata),
                "created_at": now,
            }
            self.association_repo.insert(conn, assoc_dict)

        with self.engine.connection() as conn:
            row = self.association_repo.get_by_id(conn, assoc_id)
            return MemoryAssociationResponse(
                id=row["id"],
                source_memory_id=row["source_memory_id"],
                target_memory_id=row["target_memory_id"],
                relation_type=RelationType(row["relation_type"]),
                metadata=json.loads(row["metadata_json"]),
                created_at=row["created_at"],
            )

    def get_associations(self, memory_id: str) -> list[MemoryAssociationResponse]:
        """Fetch all incoming and outgoing associations for a memory."""
        with self.engine.connection() as conn:
            if not self.memory_repo.get_by_id(conn, memory_id):
                raise NotFoundError(f"Memory with ID '{memory_id}' not found.")
            rows = self.association_repo.get_by_memory_id(conn, memory_id)
            return [
                MemoryAssociationResponse(
                    id=r["id"],
                    source_memory_id=r["source_memory_id"],
                    target_memory_id=r["target_memory_id"],
                    relation_type=RelationType(r["relation_type"]),
                    metadata=json.loads(r["metadata_json"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def delete_association(self, assoc_id: str) -> dict:
        """Remove a memory association edge."""
        with self.engine.write_transaction() as conn:
            deleted = self.association_repo.delete(conn, assoc_id)
            if deleted == 0:
                raise NotFoundError(f"Association with ID '{assoc_id}' not found.")
        return {"id": assoc_id, "deleted": True}

    def revoke_memory(self, memory_id: str, payload: MemoryRevoke) -> MemoryResponse:
        """Deactivate a memory without permanent deletion, logging the reason in audit trail."""
        now = _utc_now_iso()

        with self.engine.write_transaction() as conn:
            existing = self.memory_repo.get_by_id(conn, memory_id)
            if not existing:
                raise NotFoundError(f"Cannot revoke non-existent memory '{memory_id}'.")
            if existing["status"] == MemoryStatus.REVOKED.value:
                raise ValidationError(f"Memory '{memory_id}' is already revoked.")

            old_snapshot = json.dumps(dict(existing))
            self.memory_repo.update_status(
                conn=conn,
                memory_id=memory_id,
                new_status=MemoryStatus.REVOKED.value,
                updated_at=now,
            )
            self.audit_repo.insert_entry(
                conn=conn,
                memory_id=memory_id,
                action="revoked",
                change_reason=payload.reason,
                previous_state_json=old_snapshot,
            )

        with self.engine.connection() as conn:
            row = self.memory_repo.get_by_id(conn, memory_id)
            return _row_to_memory_response(row)

    def purge_memory(self, memory_id: str, payload: MemoryPurge) -> dict:
        """Hard-delete memory and redact any sensitive personal content from audit records."""
        with self.engine.write_transaction() as conn:
            existing = self.memory_repo.get_by_id(conn, memory_id)
            if not existing:
                raise NotFoundError(f"Cannot purge non-existent memory '{memory_id}'.")

            # 1. Redact all existing audit record snapshots for this memory
            self.audit_repo.redact_snapshots_for_memory(conn, memory_id)

            # 2. Physically remove the memory row from SQLite (cascades to verifications, citations, associations, embeddings)
            self.memory_repo.hard_delete(conn, memory_id)

            # 3. Add final tombstone entry with zero personal content
            self.audit_repo.insert_entry(
                conn=conn,
                memory_id=memory_id,
                action="purged",
                change_reason=payload.reason,
                previous_state_json=None,
            )

        return {
            "memory_id": memory_id,
            "purged": True,
            "message": "Memory permanently deleted and historical audit snapshots redacted.",
        }

    def get_audit_trail(self, memory_id: str) -> list[MemoryAuditRecordResponse]:
        """Fetch audit trail for a memory."""
        with self.engine.connection() as conn:
            rows = self.audit_repo.get_trail_by_memory_id(conn, memory_id)
            if not rows:
                if not self.memory_repo.get_by_id(conn, memory_id):
                    raise NotFoundError(f"No memory or audit records found for ID '{memory_id}'.")
            return [
                MemoryAuditRecordResponse(
                    id=row["id"],
                    memory_id=row["memory_id"],
                    action=row["action"],
                    change_reason=row["change_reason"],
                    previous_state_json=row["previous_state_json"],
                    timestamp=row["timestamp"],
                )
                for row in rows
            ]

    def list_memories(
        self,
        category: Optional[MemoryCategory] = None,
        subcategory: Optional[str] = None,
        status: Optional[MemoryStatus] = MemoryStatus.ACTIVE,
        verification_status: Optional[VerificationStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryResponse]:
        """List memories with domain filtering."""
        with self.engine.connection() as conn:
            rows = self.memory_repo.list(
                conn=conn,
                category=category.value if category else None,
                subcategory=subcategory,
                status=status.value if status else None,
                verification_status=verification_status.value if verification_status else None,
                limit=limit,
                offset=offset,
            )
            return [_row_to_memory_response(row) for row in rows]
