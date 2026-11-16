"""Repository for append-only memory verification state transitions."""

from __future__ import annotations

import sqlite3
from typing import Optional


class MemoryVerificationRepository:
    """Manages append-only records in the memory_verifications table."""

    def insert_verification(
        self,
        conn: sqlite3.Connection,
        memory_id: str,
        previous_status: Optional[str],
        new_status: str,
        verification_method: str,
        verifier_actor: str,
        notes: Optional[str],
        created_at: str,
    ) -> int:
        """Append an immutable verification transition event."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_verifications (
                memory_id, previous_status, new_status,
                verification_method, verifier_actor, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                memory_id,
                previous_status,
                new_status,
                verification_method,
                verifier_actor,
                notes,
                created_at,
            ),
        )
        return cursor.lastrowid

    def get_history(self, conn: sqlite3.Connection, memory_id: str) -> list[sqlite3.Row]:
        """Fetch all verification transitions for a memory in chronological order."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM memory_verifications
            WHERE memory_id = ?
            ORDER BY created_at ASC, id ASC;
            """,
            (memory_id,),
        )
        return cursor.fetchall()
