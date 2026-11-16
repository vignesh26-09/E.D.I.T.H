"""Repository for multi-model memory vector embeddings and active model cutover management."""

from __future__ import annotations

import sqlite3
from typing import Optional


class MemoryEmbeddingRepository:
    """Manages memory_embeddings table and active_memory_embedding_model registry."""

    def insert_embedding(
        self,
        conn: sqlite3.Connection,
        memory_id: str,
        model_name: str,
        model_version: str,
        dimensions: int,
        content_hash: str,
        embedding_blob: bytes,
        created_at: str,
    ) -> None:
        """Insert or replace vector embedding for a memory and model version."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO memory_embeddings (
                memory_id, model_name, model_version, dimensions,
                data_type, content_hash, embedding_blob, created_at
            ) VALUES (?, ?, ?, ?, 'float32', ?, ?, ?);
            """,
            (
                memory_id,
                model_name,
                model_version,
                dimensions,
                content_hash,
                embedding_blob,
                created_at,
            ),
        )

    def get_active_model(self, conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
        """Fetch the currently active memory embedding model configuration."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM active_memory_embedding_model WHERE singleton_id = 1;")
        return cursor.fetchone()

    def set_active_model(
        self,
        conn: sqlite3.Connection,
        model_name: str,
        model_version: str,
        dimensions: int,
        activated_at: str,
    ) -> None:
        """Atomically set or update the active memory embedding model."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO active_memory_embedding_model (
                singleton_id, model_name, model_version, dimensions, activated_at
            ) VALUES (1, ?, ?, ?, ?);
            """,
            (model_name, model_version, dimensions, activated_at),
        )

    def validate_cutover_anti_join(
        self,
        conn: sqlite3.Connection,
        target_model: str,
        target_version: str,
    ) -> list[str]:
        """Exhaustive anti-join check across all active memories.

        Returns list of active memory IDs that are either unindexed for target model/version
        or whose indexed content_hash does not match the memory's canonical content_hash.
        """
        cursor = conn.cursor()
        query = """
            SELECT m.id
            FROM memories m
            WHERE m.status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM memory_embeddings e
                  WHERE e.memory_id = m.id
                    AND e.model_name = ?
                    AND e.model_version = ?
                    AND e.content_hash = m.content_hash
              );
        """
        cursor.execute(query, (target_model, target_version))
        return [row["id"] for row in cursor.fetchall()]

    def get_unindexed_active_memories(
        self,
        conn: sqlite3.Connection,
        target_model: str,
        target_version: str,
        limit: int = 50,
    ) -> list[sqlite3.Row]:
        """Fetch a batch of active memories needing embeddings for target model/version."""
        cursor = conn.cursor()
        query = """
            SELECT m.id, m.content, m.content_hash
            FROM memories m
            WHERE m.status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM memory_embeddings e
                  WHERE e.memory_id = m.id
                    AND e.model_name = ?
                    AND e.model_version = ?
                    AND e.content_hash = m.content_hash
              )
            ORDER BY m.created_at ASC
            LIMIT ?;
        """
        cursor.execute(query, (target_model, target_version, limit))
        return cursor.fetchall()

    def get_active_embeddings(
        self,
        conn: sqlite3.Connection,
        model_name: str,
        model_version: str,
    ) -> list[sqlite3.Row]:
        """Load vector embeddings for semantic retrieval.

        Guarantees freshness by matching e.content_hash = m.content_hash.
        """
        cursor = conn.cursor()
        query = """
            SELECT e.memory_id, e.embedding_blob
            FROM memory_embeddings e
            JOIN memories m ON m.id = e.memory_id
            WHERE m.status = 'active'
              AND e.model_name = ?
              AND e.model_version = ?
              AND e.content_hash = m.content_hash;
        """
        cursor.execute(query, (model_name, model_version))
        return cursor.fetchall()
