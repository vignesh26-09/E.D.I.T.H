"""Repository for documents and document chunks."""

import sqlite3
from typing import Optional


class DocumentRepository:
    """Manages raw SQL operations for the documents and document_chunks tables."""

    def insert_document(self, conn: sqlite3.Connection, doc_data: dict) -> None:
        """Insert a new document record."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (
                id, title, source_uri, source_type, mime_type, file_size_bytes,
                content_hash, raw_storage_path, extracted_storage_path, metadata_json,
                original_filename, file_extension, ingestion_status, error_message, chunk_count,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                doc_data["id"],
                doc_data["title"],
                doc_data.get("source_uri"),
                doc_data["source_type"],
                doc_data["mime_type"],
                doc_data["file_size_bytes"],
                doc_data["content_hash"],
                doc_data["raw_storage_path"],
                doc_data.get("extracted_storage_path"),
                doc_data["metadata_json"],
                doc_data.get("original_filename"),
                doc_data.get("file_extension"),
                doc_data.get("ingestion_status", "processed"),
                doc_data.get("error_message"),
                doc_data.get("chunk_count", 0),
                doc_data["created_at"],
                doc_data["updated_at"],
            ),
        )

    def update_status(
        self,
        conn: sqlite3.Connection,
        doc_id: str,
        status: str,
        error_message: Optional[str] = None,
        chunk_count: Optional[int] = None,
        updated_at: Optional[str] = None,
    ) -> int:
        """Update document ingestion status, error message, and chunk count."""
        query = "UPDATE documents SET ingestion_status = ?"
        params = [status]

        if error_message is not None:
            query += ", error_message = ?"
            params.append(error_message)
        if chunk_count is not None:
            query += ", chunk_count = ?"
            params.append(chunk_count)
        if updated_at is not None:
            query += ", updated_at = ?"
            params.append(updated_at)

        query += " WHERE id = ?;"
        params.append(doc_id)

        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return cursor.rowcount

    def get_document_by_id(self, conn: sqlite3.Connection, doc_id: str) -> Optional[sqlite3.Row]:
        """Fetch document row by ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?;", (doc_id,))
        return cursor.fetchone()

    def get_document_by_hash(self, conn: sqlite3.Connection, content_hash: str) -> Optional[sqlite3.Row]:
        """Fetch document row by content hash (for duplicate detection)."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE content_hash = ?;", (content_hash,))
        return cursor.fetchone()

    def list_documents(
        self,
        conn: sqlite3.Connection,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        """List documents with optional status filtering and pagination."""
        query = "SELECT * FROM documents WHERE 1=1"
        params = []

        if status:
            query += " AND ingestion_status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return cursor.fetchall()

    def delete_document(self, conn: sqlite3.Connection, doc_id: str) -> int:
        """Delete document by ID (cascades chunks via foreign keys)."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documents WHERE id = ?;", (doc_id,))
        return cursor.rowcount

    def insert_chunk(self, conn: sqlite3.Connection, chunk_data: dict) -> None:
        """Insert a single document chunk."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO document_chunks (
                id, document_id, chunk_index, page_number, section,
                source_location, extraction_method, content_hash,
                token_count, chunk_text, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                chunk_data["id"],
                chunk_data["document_id"],
                chunk_data["chunk_index"],
                chunk_data.get("page_number"),
                chunk_data.get("section"),
                chunk_data.get("source_location"),
                chunk_data["extraction_method"],
                chunk_data["content_hash"],
                chunk_data.get("token_count"),
                chunk_data["chunk_text"],
                chunk_data["metadata_json"],
                chunk_data["created_at"],
            ),
        )

    def insert_chunks_bulk(self, conn: sqlite3.Connection, chunks_data: list[dict]) -> None:
        """Insert multiple document chunks in an efficient batch."""
        if not chunks_data:
            return

        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO document_chunks (
                id, document_id, chunk_index, page_number, section,
                source_location, extraction_method, content_hash,
                token_count, chunk_text, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            [
                (
                    c["id"],
                    c["document_id"],
                    c["chunk_index"],
                    c.get("page_number"),
                    c.get("section"),
                    c.get("source_location"),
                    c["extraction_method"],
                    c["content_hash"],
                    c.get("token_count"),
                    c["chunk_text"],
                    c["metadata_json"],
                    c["created_at"],
                )
                for c in chunks_data
            ],
        )

    def get_chunks_by_document_id(self, conn: sqlite3.Connection, doc_id: str) -> list[sqlite3.Row]:
        """Fetch all chunks for a document ordered by chunk_index."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY chunk_index ASC;",
            (doc_id,),
        )
        return cursor.fetchall()
