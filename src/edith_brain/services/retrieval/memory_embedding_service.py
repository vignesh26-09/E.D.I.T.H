"""Service for staged batch memory embedding re-indexing and atomic transactional cutover."""

from datetime import datetime, timezone
import numpy as np

from edith_brain.core.contracts import (
    EmbeddingReindexRequest,
    EmbeddingReindexResponse,
    EmbeddingCutoverRequest,
    EmbeddingCutoverResponse,
)
from edith_brain.core.exceptions import ValidationError
from edith_brain.storage.db import SQLiteEngine
from edith_brain.repositories.memory_embedding_repository import MemoryEmbeddingRepository
from edith_brain.services.retrieval.embeddings import BaseEmbeddingProvider, pack_vector


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryEmbeddingService:
    """Orchestrates staged multi-model vector embedding re-indexing, validation, and cutover."""

    def __init__(
        self,
        engine: SQLiteEngine,
        embedding_repo: MemoryEmbeddingRepository | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
    ) -> None:
        self.engine = engine
        self.embedding_repo = embedding_repo or MemoryEmbeddingRepository()
        self.embedding_provider = embedding_provider

    def reindex_batch(self, request: EmbeddingReindexRequest) -> EmbeddingReindexResponse:
        """Process a batch of unindexed active memories for the target model/version."""
        if not self.embedding_provider:
            raise ValidationError("No embedding provider is configured for re-indexing.")

        now = _utc_now_iso()
        target_model = request.target_model_name
        target_ver = request.target_model_version
        dims = self.embedding_provider.dimensions

        with self.engine.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM memories WHERE status = 'active';")
            total_active = cursor.fetchone()["total"]

            unindexed = self.embedding_repo.get_unindexed_active_memories(
                conn,
                target_model=target_model,
                target_version=target_ver,
                limit=request.batch_size,
            )

        if unindexed:
            texts = [r["content"] for r in unindexed]
            vectors = self.embedding_provider.embed_documents(texts)

            with self.engine.write_transaction() as conn:
                for row, vec in zip(unindexed, vectors):
                    arr = np.array(vec, dtype=np.float32)
                    if not np.all(np.isfinite(arr)):
                        raise ValidationError(f"Non-finite vector values detected for memory '{row['id']}'.")
                    if len(arr) != dims:
                        raise ValidationError(
                            f"Dimension mismatch for memory '{row['id']}': expected {dims}, got {len(arr)}."
                        )

                    blob = pack_vector(arr)
                    self.embedding_repo.insert_embedding(
                        conn=conn,
                        memory_id=row["id"],
                        model_name=target_model,
                        model_version=target_ver,
                        dimensions=dims,
                        content_hash=row["content_hash"],
                        embedding_blob=blob,
                        created_at=now,
                    )

        with self.engine.connection() as conn:
            missing_ids = self.embedding_repo.validate_cutover_anti_join(
                conn,
                target_model=target_model,
                target_version=target_ver,
            )

        unindexed_count = len(missing_ids)
        indexed_count = total_active - unindexed_count
        ready = (unindexed_count == 0) and (total_active > 0)

        return EmbeddingReindexResponse(
            target_model_name=target_model,
            target_model_version=target_ver,
            total_active_memories=total_active,
            indexed_memories=indexed_count,
            unindexed_active_count=unindexed_count,
            is_ready_for_cutover=ready,
        )

    def cutover_active_model(self, request: EmbeddingCutoverRequest) -> EmbeddingCutoverResponse:
        """Atomically switch the active memory embedding model after anti-join completeness verification."""
        if not self.embedding_provider:
            raise ValidationError("No embedding provider is configured for cutover.")

        now = _utc_now_iso()
        target_model = request.target_model_name
        target_ver = request.target_model_version
        dims = self.embedding_provider.dimensions

        with self.engine.write_transaction() as conn:
            missing = self.embedding_repo.validate_cutover_anti_join(
                conn,
                target_model=target_model,
                target_version=target_ver,
            )
            if missing:
                raise ValidationError(
                    f"Cannot cutover: {len(missing)} active memories remain unindexed or have mismatched content hashes."
                )

            self.embedding_repo.set_active_model(
                conn=conn,
                model_name=target_model,
                model_version=target_ver,
                dimensions=dims,
                activated_at=now,
            )

        return EmbeddingCutoverResponse(
            cutover_successful=True,
            active_model_name=target_model,
            active_model_version=target_ver,
            dimensions=dims,
            activated_at=now,
        )

    def get_active_model_info(self) -> dict:
        """Fetch active model configuration if set."""
        with self.engine.connection() as conn:
            row = self.embedding_repo.get_active_model(conn)
            if not row:
                return {"active": False, "model_name": None, "model_version": None, "dimensions": None}
            return {
                "active": True,
                "model_name": row["model_name"],
                "model_version": row["model_version"],
                "dimensions": row["dimensions"],
                "activated_at": row["activated_at"],
            }
