"""Repository for SQLite FTS5 keyword search and vector embedding queries."""

import sqlite3
from typing import Optional


class RetrievalRepository:
    """Manages raw SQL operations for full-text search and embedding vector storage."""

    def search_keyword_fts5(
        self,
        conn: sqlite3.Connection,
        sanitized_query: str,
        document_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[sqlite3.Row]:
        """Execute FTS5 MATCH query with BM25 ranking and highlight snippets."""
        sql = """
            SELECT 
                c.id AS chunk_id,
                c.document_id,
                d.title AS document_title,
                c.chunk_index,
                c.page_number,
                c.section,
                c.source_location,
                c.chunk_text,
                bm25(document_chunks_fts, 2.0, 1.0, 0.5) AS bm25_score,
                snippet(document_chunks_fts, 0, '<mark>', '</mark>', '...', 25) AS highlight
            FROM document_chunks_fts f
            JOIN document_chunks c ON c.rowid = f.rowid
            JOIN documents d ON d.id = c.document_id
            WHERE document_chunks_fts MATCH ?
        """
        params = [sanitized_query]

        if document_id:
            sql += " AND c.document_id = ?"
            params.append(document_id)

        # FTS5 bm25 produces negative scores where more negative = better match
        sql += " ORDER BY bm25_score ASC LIMIT ?;"
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()

    def insert_embedding(
        self,
        conn: sqlite3.Connection,
        chunk_id: str,
        model_name: str,
        dimensions: int,
        embedding_blob: bytes,
    ) -> None:
        """Upsert a chunk embedding vector."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chunk_embeddings (chunk_id, model_name, dimensions, embedding_blob)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                model_name = excluded.model_name,
                dimensions = excluded.dimensions,
                embedding_blob = excluded.embedding_blob,
                created_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            """,
            (chunk_id, model_name, dimensions, embedding_blob),
        )

    def insert_embeddings_bulk(
        self,
        conn: sqlite3.Connection,
        embeddings_data: list[dict],
    ) -> None:
        """Batch upsert embeddings."""
        if not embeddings_data:
            return

        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO chunk_embeddings (chunk_id, model_name, dimensions, embedding_blob)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                model_name = excluded.model_name,
                dimensions = excluded.dimensions,
                embedding_blob = excluded.embedding_blob,
                created_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            """,
            [
                (item["chunk_id"], item["model_name"], item["dimensions"], item["embedding_blob"])
                for item in embeddings_data
            ],
        )

    def get_unembedded_chunks(
        self,
        conn: sqlite3.Connection,
        document_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        """Fetch chunks that do not yet have an embedding record."""
        sql = """
            SELECT c.id, c.chunk_text, c.document_id
            FROM document_chunks c
            LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id
            WHERE e.chunk_id IS NULL
        """
        params = []
        if document_id:
            sql += " AND c.document_id = ?"
            params.append(document_id)

        sql += " ORDER BY c.rowid ASC LIMIT ?;"
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()

    def get_all_embeddings(
        self,
        conn: sqlite3.Connection,
        document_id: Optional[str] = None,
    ) -> list[sqlite3.Row]:
        """Fetch chunk metadata and embedding blobs for in-memory cosine similarity."""
        sql = """
            SELECT 
                c.id AS chunk_id,
                c.document_id,
                d.title AS document_title,
                c.chunk_index,
                c.page_number,
                c.section,
                c.source_location,
                c.chunk_text,
                e.embedding_blob,
                e.dimensions
            FROM chunk_embeddings e
            JOIN document_chunks c ON c.id = e.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE 1=1
        """
        params = []
        if document_id:
            sql += " AND c.document_id = ?"
            params.append(document_id)

        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()

    def get_index_stats(self, conn: sqlite3.Connection) -> dict:
        """Fetch counts for documents, chunks, FTS5 rows, and embeddings."""
        cursor = conn.cursor()

        cursor.execute("SELECT count(*) FROM documents;")
        doc_count = cursor.fetchone()[0]

        cursor.execute("SELECT count(*) FROM document_chunks;")
        chunk_count = cursor.fetchone()[0]

        cursor.execute("SELECT count(*) FROM document_chunks_fts;")
        fts5_count = cursor.fetchone()[0]

        cursor.execute("SELECT count(*), max(model_name), max(dimensions) FROM chunk_embeddings;")
        row = cursor.fetchone()
        emb_count = row[0]
        model_name = row[1] or "none"
        dimensions = row[2] or 0

        return {
            "total_documents": doc_count,
            "total_chunks": chunk_count,
            "fts5_indexed_chunks": fts5_count,
            "embedded_chunks": emb_count,
            "embedding_model": model_name,
            "embedding_dimensions": dimensions,
        }
