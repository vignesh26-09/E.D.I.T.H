"""Repository for Phase B5 memory access tracking, consolidations, and evaluation records."""

from __future__ import annotations

import sqlite3
from typing import Optional


class IntelligenceRepository:
    """Manages memory telemetry, consolidation candidates, and benchmark run logs."""

    def touch_memories(
        self,
        conn: sqlite3.Connection,
        memory_ids: list[str],
        accessed_at: str,
    ) -> int:
        """Increment access_count and update last_accessed_at without mutating memory content."""
        if not memory_ids:
            return 0
        placeholders = ",".join("?" for _ in memory_ids)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE memories
            SET access_count = access_count + 1,
                last_accessed_at = ?
            WHERE id IN ({placeholders}) AND status = 'active';
            """,
            [accessed_at, *memory_ids],
        )
        return cursor.rowcount

    def get_memory_access_telemetry(
        self,
        conn: sqlite3.Connection,
        memory_id: str,
    ) -> Optional[sqlite3.Row]:
        """Fetch access telemetry for a specific memory."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, confidence, access_count, last_accessed_at, created_at, subcategory
            FROM memories
            WHERE id = ?;
            """,
            (memory_id,),
        )
        return cursor.fetchone()

    def insert_consolidation_candidate(
        self,
        conn: sqlite3.Connection,
        candidate_dict: dict,
    ) -> None:
        """Insert a newly distilled consolidation candidate."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_consolidations (
                id, session_id, candidate_category, candidate_subcategory,
                candidate_content, rationale, confidence, source_episode_ids_json,
                status, applied_memory_id, reviewed_by, reviewed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                candidate_dict["id"],
                candidate_dict["session_id"],
                candidate_dict["candidate_category"],
                candidate_dict["candidate_subcategory"],
                candidate_dict["candidate_content"],
                candidate_dict["rationale"],
                candidate_dict["confidence"],
                candidate_dict["source_episode_ids_json"],
                candidate_dict["status"],
                candidate_dict.get("applied_memory_id"),
                candidate_dict.get("reviewed_by"),
                candidate_dict.get("reviewed_at"),
                candidate_dict["created_at"],
                candidate_dict["updated_at"],
            ),
        )

    def get_consolidation_candidate(
        self,
        conn: sqlite3.Connection,
        candidate_id: str,
    ) -> Optional[sqlite3.Row]:
        """Fetch candidate by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_consolidations WHERE id = ?;", (candidate_id,))
        return cursor.fetchone()

    def list_consolidation_candidates(
        self,
        conn: sqlite3.Connection,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[sqlite3.Row]:
        """List consolidation candidates with optional session or status filters."""
        query = "SELECT * FROM memory_consolidations WHERE 1=1"
        params = []
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return cursor.fetchall()

    def update_consolidation_status(
        self,
        conn: sqlite3.Connection,
        candidate_id: str,
        status: str,
        applied_memory_id: Optional[str],
        reviewed_by: Optional[str],
        reviewed_at: Optional[str],
        updated_at: str,
    ) -> int:
        """Update review or applied status of a consolidation candidate."""
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE memory_consolidations
            SET status = ?,
                applied_memory_id = COALESCE(?, applied_memory_id),
                reviewed_by = ?,
                reviewed_at = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (status, applied_memory_id, reviewed_by, reviewed_at, updated_at, candidate_id),
        )
        return cursor.rowcount

    def insert_evaluation_run(
        self,
        conn: sqlite3.Connection,
        run_dict: dict,
    ) -> None:
        """Persist benchmark execution results."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_evaluation_runs (
                id, run_type, metrics_json, parameters_json, execution_time_ms, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                run_dict["id"],
                run_dict["run_type"],
                run_dict["metrics_json"],
                run_dict["parameters_json"],
                run_dict["execution_time_ms"],
                run_dict["status"],
                run_dict["created_at"],
            ),
        )

    def get_evaluation_run(
        self,
        conn: sqlite3.Connection,
        run_id: str,
    ) -> Optional[sqlite3.Row]:
        """Retrieve evaluation run record by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_evaluation_runs WHERE id = ?;", (run_id,))
        return cursor.fetchone()

    def list_evaluation_runs(
        self,
        conn: sqlite3.Connection,
        limit: int = 20,
    ) -> list[sqlite3.Row]:
        """List historical benchmark runs."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM memory_evaluation_runs ORDER BY created_at DESC LIMIT ?;",
            (limit,),
        )
        return cursor.fetchall()
