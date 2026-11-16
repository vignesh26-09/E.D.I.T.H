"""Repository for procedural workflows, multi-step playbooks, and execution telemetry."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional


class ProceduralRepository:
    """Manages SQL operations for procedures, procedure_execution_logs, and procedures_fts."""

    def insert(self, conn: sqlite3.Connection, proc_data: dict) -> None:
        """Insert a new procedure."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO procedures (
                id, title, description, version, status,
                trigger_conditions_json, prerequisites_json, steps_json,
                execution_count, success_count, last_executed_at,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                proc_data["id"],
                proc_data["title"],
                proc_data["description"],
                proc_data.get("version", "1.0.0"),
                proc_data.get("status", "active"),
                proc_data.get("trigger_conditions_json", "[]"),
                proc_data.get("prerequisites_json", "[]"),
                proc_data["steps_json"],
                proc_data.get("execution_count", 0),
                proc_data.get("success_count", 0),
                proc_data.get("last_executed_at"),
                proc_data.get("metadata_json", "{}"),
                proc_data["created_at"],
                proc_data["updated_at"],
            ),
        )

    def get_by_id(self, conn: sqlite3.Connection, procedure_id: str) -> Optional[sqlite3.Row]:
        """Fetch procedure by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM procedures WHERE id = ?;", (procedure_id,))
        return cursor.fetchone()

    def update_status(self, conn: sqlite3.Connection, procedure_id: str, new_status: str, updated_at: str) -> int:
        """Update procedure status (e.g. active -> deprecated)."""
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE procedures SET status = ?, updated_at = ? WHERE id = ?;",
            (new_status, updated_at, procedure_id),
        )
        return cursor.rowcount

    def record_execution(
        self,
        conn: sqlite3.Connection,
        procedure_id: str,
        executed_at: str,
        execution_status: str,
        duration_seconds: Optional[float],
        execution_actor: str,
        step_results_json: str,
        error_message: Optional[str],
        notes: Optional[str],
    ) -> int:
        """Record execution telemetry and atomically update execution counters and success rate."""
        cursor = conn.cursor()

        # 1. Insert execution log
        cursor.execute(
            """
            INSERT INTO procedure_execution_logs (
                procedure_id, executed_at, execution_status, duration_seconds,
                execution_actor, step_results_json, error_message, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                procedure_id,
                executed_at,
                execution_status,
                duration_seconds,
                execution_actor,
                step_results_json,
                error_message,
                notes,
            ),
        )
        log_id = cursor.lastrowid

        # 2. Update procedure telemetry counters
        is_success = 1 if execution_status == "success" else 0
        cursor.execute(
            """
            UPDATE procedures
            SET execution_count = execution_count + 1,
                success_count = success_count + ?,
                last_executed_at = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (is_success, executed_at, executed_at, procedure_id),
        )

        return log_id

    def list(
        self,
        conn: sqlite3.Connection,
        status: Optional[str] = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        """List procedures with optional status filtering."""
        query = "SELECT * FROM procedures WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return cursor.fetchall()

    def search_fts(
        self,
        conn: sqlite3.Connection,
        sanitized_query: str,
        status: Optional[str] = "active",
        limit: int = 20,
    ) -> list[sqlite3.Row]:
        """Search procedures via FTS5 trigger condition and text matching."""
        query = """
            SELECT p.*
            FROM procedures_fts fts
            JOIN procedures p ON p.rowid = fts.rowid
            WHERE procedures_fts MATCH ?
        """
        params = [sanitized_query]
        if status:
            query += " AND p.status = ?"
            params.append(status)
        query += " ORDER BY p.execution_count DESC, p.updated_at DESC LIMIT ?;"
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return cursor.fetchall()

    def get_execution_logs(
        self,
        conn: sqlite3.Connection,
        procedure_id: str,
        limit: int = 50,
    ) -> list[sqlite3.Row]:
        """Fetch execution logs for a procedure."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM procedure_execution_logs
            WHERE procedure_id = ?
            ORDER BY executed_at DESC, id DESC
            LIMIT ?;
            """,
            (procedure_id, limit),
        )
        return cursor.fetchall()

    def delete(self, conn: sqlite3.Connection, procedure_id: str) -> int:
        """Physically delete a procedure."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM procedures WHERE id = ?;", (procedure_id,))
        return cursor.rowcount
