"""SQLite connection lifecycle management, PRAGMA enforcement, and transaction boundaries."""

import sqlite3
from pathlib import Path
from typing import Generator
from contextlib import contextmanager

from edith_brain.core.config import Settings, get_settings
from edith_brain.core.exceptions import StorageError


class SQLiteEngine:
    """Manages SQLite database connections with strict PRAGMA and concurrency controls."""

    def __init__(self, db_path: Path | str | None = None, busy_timeout_ms: int = 5000) -> None:
        if db_path is None:
            settings = get_settings()
            self.db_path = str(settings.database_path)
            self.busy_timeout_ms = settings.sqlite_busy_timeout_ms
        else:
            self.db_path = str(db_path)
            self.busy_timeout_ms = busy_timeout_ms

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        """Apply required PRAGMAs to every opened connection."""
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms};")
        cursor.execute("PRAGMA temp_store = MEMORY;")
        cursor.close()

    def get_raw_connection(self) -> sqlite3.Connection:
        """Open a raw connection with PRAGMAs applied.

        Note: autocommit=False ensures manual transaction control with BEGIN IMMEDIATE.
        """
        # In Python 3.12+, autocommit can be explicitly controlled via isolation_level=None
        # to allow explicit BEGIN IMMEDIATE statements.
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1000.0,
            isolation_level=None,  # Autocommit mode enabled so we can control BEGIN manually
            check_same_thread=False
        )
        self._apply_pragmas(conn)
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a connection context manager with automatic close."""
        conn = self.get_raw_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def write_transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Execute a write transaction using BEGIN IMMEDIATE to avoid SQLite lock escalation deadlocks."""
        conn = self.get_raw_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT;")
        except Exception as exc:
            try:
                if conn.in_transaction:
                    conn.execute("ROLLBACK;")
            except Exception:
                pass
            if isinstance(exc, sqlite3.OperationalError) and "busy" in str(exc).lower():
                raise StorageError(f"Database locked or busy timeout reached: {exc}") from exc
            raise
        finally:
            conn.close()

    def check_health(self) -> dict:
        """Inspect active SQLite connection status and PRAGMAs."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]

            cursor.execute("PRAGMA foreign_keys;")
            foreign_keys = bool(cursor.fetchone()[0])

            cursor.execute("SELECT sqlite_version();")
            version = cursor.fetchone()[0]

            return {
                "connected": True,
                "sqlite_version": version,
                "journal_mode": journal_mode,
                "wal_mode": journal_mode.lower() == "wal",
                "foreign_keys_on": foreign_keys,
            }
