"""Repository for memory audit trail operations."""

import sqlite3
from typing import Optional


class MemoryAuditRepository:
    """Manages raw SQL operations for the memory_audit_log table."""

    def insert_entry(
        self,
        conn: sqlite3.Connection,
        memory_id: str,
        action: str,
        change_reason: str,
        previous_state_json: Optional[str] = None,
    ) -> int:
        """Insert a new audit record into the append-only log."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_audit_log (memory_id, action, change_reason, previous_state_json)
            VALUES (?, ?, ?, ?);
            """,
            (memory_id, action, change_reason, previous_state_json),
        )
        return cursor.lastrowid

    def get_trail_by_memory_id(self, conn: sqlite3.Connection, memory_id: str) -> list[sqlite3.Row]:
        """Fetch full audit trail for a memory in chronological order."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, memory_id, action, change_reason, previous_state_json, timestamp
            FROM memory_audit_log
            WHERE memory_id = ?
            ORDER BY id ASC;
            """,
            (memory_id,),
        )
        return cursor.fetchall()

    def redact_snapshots_for_memory(self, conn: sqlite3.Connection, memory_id: str) -> int:
        """Overwrite sensitive snapshots with '[REDACTED_PURGED]' on permanent purge."""
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE memory_audit_log
            SET previous_state_json = '[REDACTED_PURGED]'
            WHERE memory_id = ?;
            """,
            (memory_id,),
        )
        return cursor.rowcount
