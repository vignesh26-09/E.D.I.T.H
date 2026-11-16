"""Repository for cross-domain memory links connecting episodes, procedures, and personal memories."""

from __future__ import annotations

import sqlite3
from typing import Optional


class CrossMemoryLinkRepository:
    """Manages multi-domain relationships in episodic_procedural_links."""

    def insert(self, conn: sqlite3.Connection, link_data: dict) -> None:
        """Insert a cross-memory relation link."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO episodic_procedural_links (
                id, episode_id, procedure_id, memory_id,
                link_type, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                link_data["id"],
                link_data.get("episode_id"),
                link_data.get("procedure_id"),
                link_data.get("memory_id"),
                link_data["link_type"],
                link_data.get("metadata_json", "{}"),
                link_data["created_at"],
            ),
        )

    def get_by_id(self, conn: sqlite3.Connection, link_id: str) -> Optional[sqlite3.Row]:
        """Fetch link by unique ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM episodic_procedural_links WHERE id = ?;", (link_id,))
        return cursor.fetchone()

    def get_by_episode_id(self, conn: sqlite3.Connection, episode_id: str) -> list[sqlite3.Row]:
        """Fetch all links associated with an episode."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM episodic_procedural_links WHERE episode_id = ? ORDER BY created_at ASC;",
            (episode_id,),
        )
        return cursor.fetchall()

    def get_by_procedure_id(self, conn: sqlite3.Connection, procedure_id: str) -> list[sqlite3.Row]:
        """Fetch all links associated with a procedure."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM episodic_procedural_links WHERE procedure_id = ? ORDER BY created_at ASC;",
            (procedure_id,),
        )
        return cursor.fetchall()

    def get_by_memory_id(self, conn: sqlite3.Connection, memory_id: str) -> list[sqlite3.Row]:
        """Fetch all links associated with a personal memory."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM episodic_procedural_links WHERE memory_id = ? ORDER BY created_at ASC;",
            (memory_id,),
        )
        return cursor.fetchall()

    def delete(self, conn: sqlite3.Connection, link_id: str) -> int:
        """Remove a cross-domain memory link."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM episodic_procedural_links WHERE id = ?;", (link_id,))
        return cursor.rowcount
