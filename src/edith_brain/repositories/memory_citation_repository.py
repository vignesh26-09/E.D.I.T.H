"""Repository for memory provenance citations linking memories to documents and chunks."""

from __future__ import annotations

import sqlite3
from typing import Optional
from edith_brain.core.exceptions import ValidationError, NotFoundError


class MemoryCitationRepository:
    """Manages memory_citations table operations and document-chunk parentage checks."""

    def validate_parentage(
        self,
        conn: sqlite3.Connection,
        document_id: Optional[str],
        chunk_id: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        """Validate that document and chunk exist and that chunk belongs to document.

        Returns resolved (document_id, chunk_id).
        """
        cursor = conn.cursor()

        if chunk_id:
            cursor.execute("SELECT id, document_id FROM document_chunks WHERE id = ?;", (chunk_id,))
            chunk_row = cursor.fetchone()
            if not chunk_row:
                raise NotFoundError(f"Document chunk with ID '{chunk_id}' not found.")
            actual_doc_id = chunk_row["document_id"]

            if document_id and document_id != actual_doc_id:
                raise ValidationError(
                    f"Chunk '{chunk_id}' belongs to document '{actual_doc_id}', not '{document_id}'."
                )
            return actual_doc_id, chunk_id

        if document_id:
            cursor.execute("SELECT id FROM documents WHERE id = ?;", (document_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                raise NotFoundError(f"Document with ID '{document_id}' not found.")
            return document_id, None

        raise ValidationError("Citation must specify at least document_id or chunk_id.")

    def insert(
        self,
        conn: sqlite3.Connection,
        citation_data: dict,
    ) -> None:
        """Insert a validated provenance citation."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_citations (
                id, memory_id, document_id, chunk_id,
                historical_document_id, historical_chunk_id,
                citation_status, quote_text, confidence_score,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                citation_data["id"],
                citation_data["memory_id"],
                citation_data.get("document_id"),
                citation_data.get("chunk_id"),
                citation_data.get("historical_document_id"),
                citation_data.get("historical_chunk_id"),
                citation_data.get("citation_status", "valid"),
                citation_data.get("quote_text"),
                citation_data.get("confidence_score", 1.0),
                citation_data.get("metadata_json", "{}"),
                citation_data["created_at"],
            ),
        )

    def get_by_memory_id(self, conn: sqlite3.Connection, memory_id: str) -> list[sqlite3.Row]:
        """Fetch all citations for a given memory."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM memory_citations
            WHERE memory_id = ?
            ORDER BY created_at ASC;
            """,
            (memory_id,),
        )
        return cursor.fetchall()

    def get_by_id(self, conn: sqlite3.Connection, citation_id: str) -> Optional[sqlite3.Row]:
        """Fetch a specific citation by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_citations WHERE id = ?;", (citation_id,))
        return cursor.fetchone()
