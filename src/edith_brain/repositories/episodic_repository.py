"""Repository for episodic memory events, session grouping, and timeline querying."""

from __future__ import annotations

import sqlite3
from typing import Optional


class EpisodicRepository:
    """Manages SQL operations for the episodes table and episodes_fts."""

    def insert(self, conn: sqlite3.Connection, episode_data: dict) -> None:
        """Insert a new episodic event."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO episodes (
                id, session_id, title, event_type, occurred_at,
                duration_seconds, summary, narrative_detail,
                actors_json, context_tags_json, significance_score,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                episode_data["id"],
                episode_data["session_id"],
                episode_data["title"],
                episode_data["event_type"],
                episode_data["occurred_at"],
                episode_data.get("duration_seconds"),
                episode_data["summary"],
                episode_data.get("narrative_detail"),
                episode_data.get("actors_json", "[]"),
                episode_data.get("context_tags_json", "[]"),
                episode_data.get("significance_score", 0.5),
                episode_data.get("metadata_json", "{}"),
                episode_data["created_at"],
            ),
        )

    def get_by_id(self, conn: sqlite3.Connection, episode_id: str) -> Optional[sqlite3.Row]:
        """Fetch episode by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM episodes WHERE id = ?;", (episode_id,))
        return cursor.fetchone()

    def delete(self, conn: sqlite3.Connection, episode_id: str) -> int:
        """Physically delete an episode."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM episodes WHERE id = ?;", (episode_id,))
        return cursor.rowcount

    def get_timeline(
        self,
        conn: sqlite3.Connection,
        session_id: Optional[str] = None,
        event_types: Optional[list[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        min_significance: float = 0.0,
        query: Optional[str] = None,
        limit: int = 50,
        order: str = "asc",
    ) -> list[sqlite3.Row]:
        """Retrieve chronological or significance-ordered episodes with multi-facet filtering."""
        params = []
        sort_order = "DESC" if order.lower() == "desc" else "ASC"

        if query and query.strip():
            # Query with FTS5 join
            sql = """
                SELECT e.*
                FROM episodes_fts fts
                JOIN episodes e ON e.rowid = fts.rowid
                WHERE episodes_fts MATCH ?
                  AND e.significance_score >= ?
            """
            params.append(query.strip())
            params.append(min_significance)
        else:
            sql = "SELECT * FROM episodes WHERE significance_score >= ?"
            params.append(min_significance)

        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)

        if event_types:
            placeholders = ",".join(["?"] * len(event_types))
            sql += f" AND event_type IN ({placeholders})"
            params.extend(event_types)

        if start_time:
            sql += " AND occurred_at >= ?"
            params.append(start_time)

        if end_time:
            sql += " AND occurred_at <= ?"
            params.append(end_time)

        sql += f" ORDER BY occurred_at {sort_order} LIMIT ?;"
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()

    def list_sessions(self, conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
        """Aggregate sessions with event count, start time, and latest activity."""
        cursor = conn.cursor()
        query = """
            SELECT 
                session_id,
                COUNT(*) AS event_count,
                MIN(occurred_at) AS first_event_at,
                MAX(occurred_at) AS last_event_at,
                AVG(significance_score) AS avg_significance
            FROM episodes
            GROUP BY session_id
            ORDER BY last_event_at DESC
            LIMIT ?;
        """
        cursor.execute(query, (limit,))
        return [dict(r) for r in cursor.fetchall()]
