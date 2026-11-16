"""Integration tests for SQLite concurrency, PRAGMA enforcement, and transaction rollback."""

import sqlite3
import pytest
from edith_brain.storage.db import SQLiteEngine


def test_sqlite_pragmas_and_wal(test_engine: SQLiteEngine):
    """Ensure WAL mode and foreign keys are strictly enforced on every connection."""
    health = test_engine.check_health()
    assert health["connected"] is True
    assert health["wal_mode"] is True
    assert health["foreign_keys_on"] is True


def test_sqlite_foreign_key_enforcement(test_engine: SQLiteEngine):
    """Attempting to insert a child record with invalid foreign key must raise IntegrityError."""
    with pytest.raises(sqlite3.IntegrityError):
        with test_engine.write_transaction() as conn:
            conn.execute(
                """
                INSERT INTO document_chunks (
                    id, document_id, chunk_index, extraction_method, content_hash, chunk_text
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                ("chunk-1", "non-existent-doc-id", 0, "plain_v1", "hash123", "Sample text"),
            )


def test_sqlite_transaction_rollback_on_failure(test_engine: SQLiteEngine):
    """Ensure write transaction rolls back completely when an unhandled exception occurs."""
    initial_count = 0
    with test_engine.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM memories;")
        initial_count = cursor.fetchone()[0]

    # Attempt a transaction that inserts one row then raises an error
    with pytest.raises(RuntimeError):
        with test_engine.write_transaction() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, category, subcategory, content, confidence, source_type, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                ("mem-rollback-test", "semantic", None, "This will be rolled back", 1.0, "user_explicit", "active"),
            )
            # Simulated crash
            raise RuntimeError("Intentional failure to trigger rollback")

    # Verify count did not change
    with test_engine.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM memories;")
        post_count = cursor.fetchone()[0]
        assert post_count == initial_count
