"""Repository for memory associations graph, canonical undirected edges, and acyclic supersession checks."""

from __future__ import annotations

import sqlite3
from typing import Optional
from edith_brain.core.exceptions import ValidationError, NotFoundError


class MemoryAssociationRepository:
    """Manages memory_associations table operations, canonical ordering, and cycle prevention."""

    def check_supersedes_cycle(
        self,
        conn: sqlite3.Connection,
        source_id: str,
        target_id: str,
    ) -> bool:
        """Check if adding supersedes edge source_id -> target_id creates a cycle.

        Uses recursive CTE with UNION to detect if target_id already reaches source_id.
        Returns True if a cycle would be created.
        """
        cursor = conn.cursor()
        query = """
            WITH RECURSIVE lineage(id) AS (
                SELECT target_memory_id FROM memory_associations 
                WHERE source_memory_id = ? AND relation_type = 'supersedes'
                UNION
                SELECT a.target_memory_id FROM memory_associations a
                JOIN lineage l ON a.source_memory_id = l.id
                WHERE a.relation_type = 'supersedes'
            )
            SELECT 1 FROM lineage WHERE id = ? LIMIT 1;
        """
        cursor.execute(query, (target_id, source_id))
        return cursor.fetchone() is not None

    def insert(
        self,
        conn: sqlite3.Connection,
        association_data: dict,
    ) -> None:
        """Insert an association edge with validation and canonical ordering."""
        source_id = association_data["source_memory_id"]
        target_id = association_data["target_memory_id"]
        relation_type = association_data["relation_type"]

        if source_id == target_id:
            raise ValidationError("Self-associations are prohibited.")

        # Canonicalize undirected relations (relates_to)
        if relation_type == "relates_to" and source_id > target_id:
            source_id, target_id = target_id, source_id

        # Cycle check for supersedes
        if relation_type == "supersedes":
            if self.check_supersedes_cycle(conn, source_id, target_id):
                raise ValidationError(
                    f"Supersession cycle detected: memory '{source_id}' cannot supersede '{target_id}' "
                    f"as it already exists in its supersession lineage."
                )

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_associations (
                id, source_memory_id, target_memory_id, relation_type,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                association_data["id"],
                source_id,
                target_id,
                relation_type,
                association_data.get("metadata_json", "{}"),
                association_data["created_at"],
            ),
        )

    def get_by_memory_id(
        self,
        conn: sqlite3.Connection,
        memory_id: str,
    ) -> list[sqlite3.Row]:
        """Fetch all incoming and outgoing associations for a memory."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM memory_associations
            WHERE source_memory_id = ? OR target_memory_id = ?
            ORDER BY created_at ASC;
            """,
            (memory_id, memory_id),
        )
        return cursor.fetchall()

    def get_by_id(self, conn: sqlite3.Connection, assoc_id: str) -> Optional[sqlite3.Row]:
        """Fetch association by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_associations WHERE id = ?;", (assoc_id,))
        return cursor.fetchone()

    def delete(self, conn: sqlite3.Connection, assoc_id: str) -> int:
        """Remove an association edge."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_associations WHERE id = ?;", (assoc_id,))
        return cursor.rowcount
