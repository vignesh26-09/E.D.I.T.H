"""Repository for structured memory CRUD and FTS5 keyword retrieval."""

from __future__ import annotations

import sqlite3
from typing import Optional


class MemoryRepository:
    """Manages SQL operations for the memories and memories_fts tables."""

    def insert(self, conn: sqlite3.Connection, memory_data: dict) -> None:
        """Insert a new memory record."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memories (
                id, category, subcategory, content, confidence,
                source_type, source_reference_id, status, parent_memory_id,
                tags_json, metadata_json, created_at, updated_at, verified_at,
                verification_status, verification_method, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                memory_data["id"],
                memory_data["category"],
                memory_data.get("subcategory"),
                memory_data["content"],
                memory_data["confidence"],
                memory_data["source_type"],
                memory_data.get("source_reference_id"),
                memory_data["status"],
                memory_data.get("parent_memory_id"),
                memory_data["tags_json"],
                memory_data["metadata_json"],
                memory_data["created_at"],
                memory_data["updated_at"],
                memory_data.get("verified_at"),
                memory_data.get("verification_status", "unverified"),
                memory_data.get("verification_method", "system_inferred"),
                memory_data.get("content_hash"),
            ),
        )

    def get_by_id(self, conn: sqlite3.Connection, memory_id: str) -> Optional[sqlite3.Row]:
        """Fetch memory row by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE id = ?;", (memory_id,))
        return cursor.fetchone()

    def update_status(
        self,
        conn: sqlite3.Connection,
        memory_id: str,
        new_status: str,
        updated_at: str,
    ) -> int:
        """Update memory status (e.g. active -> superseded or revoked)."""
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE memories
            SET status = ?, updated_at = ?
            WHERE id = ?;
            """,
            (new_status, updated_at, memory_id),
        )
        return cursor.rowcount

    def update_verification(
        self,
        conn: sqlite3.Connection,
        memory_id: str,
        verification_status: str,
        verification_method: str,
        verified_at: Optional[str],
        updated_at: str,
    ) -> int:
        """Update memory verification status and method."""
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE memories
            SET verification_status = ?, verification_method = ?, verified_at = ?, updated_at = ?
            WHERE id = ?;
            """,
            (verification_status, verification_method, verified_at, updated_at, memory_id),
        )
        return cursor.rowcount

    def hard_delete(self, conn: sqlite3.Connection, memory_id: str) -> int:
        """Physically remove memory row on permanent purge."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE id = ?;", (memory_id,))
        return cursor.rowcount

    def list(
        self,
        conn: sqlite3.Connection,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        status: Optional[str] = "active",
        verification_status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        """Query memories with filtering and pagination."""
        query = "SELECT * FROM memories WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if subcategory:
            query += " AND subcategory = ?"
            params.append(subcategory)
        if status:
            query += " AND status = ?"
            params.append(status)
        if verification_status:
            query += " AND verification_status = ?"
            params.append(verification_status)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return cursor.fetchall()

    def get_active_by_subcategory(
        self,
        conn: sqlite3.Connection,
        category: str,
        subcategory: Optional[str] = None,
    ) -> list[sqlite3.Row]:
        """Fetch all active memories in a category/subcategory for conflict evaluation."""
        query = "SELECT * FROM memories WHERE status = 'active' AND category = ?"
        params = [category]
        if subcategory:
            query += " AND subcategory = ?"
            params.append(subcategory)
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return cursor.fetchall()

    def search_keyword_fts5(
        self,
        conn: sqlite3.Connection,
        sanitized_query: str,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        include_statuses: Optional[list[str]] = None,
        include_verification: Optional[list[str]] = None,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> list[dict]:
        """FTS5 keyword search over memories_fts ordered by BM25 ascending (lower is better)."""
        statuses = include_statuses or ["active"]
        verifications = include_verification or ["verified", "unverified"]

        status_placeholders = ",".join(["?"] * len(statuses))
        verif_placeholders = ",".join(["?"] * len(verifications))

        sql = f"""
            SELECT 
                m.*,
                bm25(memories_fts) AS bm25_rank,
                snippet(memories_fts, 0, '<mark>', '</mark>', '...', 20) AS snippet
            FROM memories_fts fts
            JOIN memories m ON m.rowid = fts.rowid
            WHERE memories_fts MATCH ?
              AND m.status IN ({status_placeholders})
              AND m.verification_status IN ({verif_placeholders})
              AND m.confidence >= ?
        """
        params = [sanitized_query]
        params.extend(statuses)
        params.extend(verifications)
        params.append(min_confidence)

        if category:
            sql += " AND m.category = ?"
            params.append(category)
        if subcategory:
            sql += " AND m.subcategory = ?"
            params.append(subcategory)

        sql += " ORDER BY bm25(memories_fts) ASC, m.confidence DESC, m.created_at DESC LIMIT ?;"
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        return [dict(row) for row in cursor.fetchall()]
