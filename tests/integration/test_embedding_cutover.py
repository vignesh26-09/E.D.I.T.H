"""Integration tests for multi-model embedding coexistence, anti-join validation, cutover, and rollback."""

import pytest
from edith_brain.core.contracts import (
    MemoryCreate,
    EmbeddingReindexRequest,
    EmbeddingCutoverRequest,
    MemoryCategory,
    PersonalSubcategory,
)
from edith_brain.core.exceptions import ValidationError
from edith_brain.services.memory_service import MemoryService
from edith_brain.services.retrieval.memory_embedding_service import MemoryEmbeddingService
from edith_brain.storage.db import SQLiteEngine
from edith_brain.services.retrieval.embeddings import DeterministicEmbeddingProvider


def test_embedding_cutover_rejected_when_unindexed_memories_exist(test_engine: SQLiteEngine):
    """Cutover fails with ValidationError when active memories lack embeddings for target model."""
    provider = DeterministicEmbeddingProvider(dimensions=384, model_name="model-v1", model_version="1.0")
    mem_service = MemoryService(engine=test_engine)
    emb_service = MemoryEmbeddingService(engine=test_engine, embedding_provider=provider)

    # Create active memory
    mem_service.create_memory(
        MemoryCreate(
            category=MemoryCategory.PERSONAL,
            subcategory=PersonalSubcategory.PROFILE_FACT,
            content="Alex is an engineer.",
        )
    )

    # Attempt cutover without re-indexing
    with pytest.raises(ValidationError) as exc:
        emb_service.cutover_active_model(
            EmbeddingCutoverRequest(target_model_name="model-v1", target_model_version="1.0")
        )
    assert "unindexed" in str(exc.value)


def test_embedding_staged_reindexing_and_atomic_cutover(test_engine: SQLiteEngine):
    """Staged re-indexing indexes memories, passes anti-join gate, and switches active model."""
    provider = DeterministicEmbeddingProvider(dimensions=384, model_name="bge-small", model_version="1.0")
    mem_service = MemoryService(engine=test_engine)
    emb_service = MemoryEmbeddingService(engine=test_engine, embedding_provider=provider)

    # 1. Create memories
    mem1 = mem_service.create_memory(
        MemoryCreate(category=MemoryCategory.PERSONAL, subcategory=PersonalSubcategory.SKILL, content="FastAPI")
    )
    mem2 = mem_service.create_memory(
        MemoryCreate(category=MemoryCategory.PERSONAL, subcategory=PersonalSubcategory.SKILL, content="Python")
    )

    # 2. Re-index
    reindex_res = emb_service.reindex_batch(
        EmbeddingReindexRequest(target_model_name="bge-small", target_model_version="1.0", batch_size=50)
    )
    assert reindex_res.is_ready_for_cutover is True
    assert reindex_res.indexed_memories == 2
    assert reindex_res.unindexed_active_count == 0

    # 3. Cutover
    cutover_res = emb_service.cutover_active_model(
        EmbeddingCutoverRequest(target_model_name="bge-small", target_model_version="1.0")
    )
    assert cutover_res.cutover_successful is True
    assert cutover_res.active_model_name == "bge-small"

    # 4. Verify active model
    info = emb_service.get_active_model_info()
    assert info["active"] is True
    assert info["model_name"] == "bge-small"


def test_content_mutation_evicts_stale_embeddings_trigger(test_engine: SQLiteEngine):
    """Updating memory content in-place fires trg_memories_content_stale_emb, evicting cached vectors."""
    provider = DeterministicEmbeddingProvider(dimensions=384, model_name="bge-small", model_version="1.0")
    mem_service = MemoryService(engine=test_engine)
    emb_service = MemoryEmbeddingService(engine=test_engine, embedding_provider=provider)

    mem = mem_service.create_memory(
        MemoryCreate(category=MemoryCategory.PERSONAL, subcategory=PersonalSubcategory.GOAL, content="Old goal")
    )

    # Index embedding
    emb_service.reindex_batch(
        EmbeddingReindexRequest(target_model_name="bge-small", target_model_version="1.0")
    )

    with test_engine.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS c FROM memory_embeddings WHERE memory_id = ?", (mem.id,))
        assert cursor.fetchone()["c"] == 1

    # In-place update content on memories table
    with test_engine.write_transaction() as conn:
        conn.execute("UPDATE memories SET content = 'New altered goal' WHERE id = ?", (mem.id,))

    # Embedding must be evicted
    with test_engine.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS c FROM memory_embeddings WHERE memory_id = ?", (mem.id,))
        assert cursor.fetchone()["c"] == 0
