"""Idempotent database migration runner with checksum integrity verification."""

import re
import sqlite3
from pathlib import Path
from edith_brain.core.security import compute_sha256
from edith_brain.core.exceptions import MigrationError
from edith_brain.storage.db import SQLiteEngine


def _split_sql_statements(sql: str) -> list[str]:
    """Split a SQL migration script into individual executable statements using sqlite3.complete_statement."""
    statements = []
    current_lines = []
    for line in sql.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("--") or not trimmed:
            continue
        current_lines.append(line)
        candidate = "\n".join(current_lines).strip()
        if candidate.endswith(";") and sqlite3.complete_statement(candidate):
            statements.append(candidate)
            current_lines = []
    if current_lines:
        remainder = "\n".join(current_lines).strip()
        if remainder:
            statements.append(remainder)
    return statements


class MigrationRunner:
    """Discovers, validates, and applies SQLite schema migrations idempotently."""

    def __init__(self, engine: SQLiteEngine, migrations_dir: Path | None = None) -> None:
        self.engine = engine
        if migrations_dir is None:
            self.migrations_dir = Path(__file__).parent / "sql"
        else:
            self.migrations_dir = migrations_dir

    def _ensure_migrations_table(self) -> None:
        """Bootstrap the schema_migrations table if not present."""
        with self.engine.write_transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                );
            """)

    def get_applied_migrations(self) -> dict[int, dict]:
        """Fetch all previously applied migrations keyed by version."""
        self._ensure_migrations_table()
        with self.engine.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version ASC;")
            rows = cursor.fetchall()
            return {
                row["version"]: {
                    "version": row["version"],
                    "name": row["name"],
                    "checksum": row["checksum"],
                    "applied_at": row["applied_at"],
                }
                for row in rows
            }

    def run_migrations(self) -> list[int]:
        """Apply all pending migrations in order, verifying integrity."""
        self._ensure_migrations_table()
        applied = self.get_applied_migrations()

        # Discover migration files
        sql_files = sorted(self.migrations_dir.glob("*.sql"))
        newly_applied = []

        for sql_file in sql_files:
            match = re.match(r"^(\d+)_(.+)\.sql$", sql_file.name)
            if not match:
                continue

            version = int(match.group(1))
            name = sql_file.name
            content = sql_file.read_text(encoding="utf-8")
            checksum = compute_sha256(content)

            if version in applied:
                # Integrity check: verify checksum has not been tampered with
                recorded_checksum = applied[version]["checksum"]
                if recorded_checksum != checksum:
                    raise MigrationError(
                        f"Checksum mismatch for migration {name} (version {version})! "
                        f"Expected {recorded_checksum}, found {checksum}. Database schema integrity compromised."
                    )
                continue

            # Apply pending migration in an explicit write transaction
            try:
                with self.engine.write_transaction() as conn:
                    statements = _split_sql_statements(content)
                    for stmt in statements:
                        conn.execute(stmt)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, checksum) VALUES (?, ?, ?);",
                        (version, name, checksum),
                    )
                newly_applied.append(version)
            except Exception as exc:
                raise MigrationError(
                    f"Failed to execute migration {name} (version {version}): {exc}"
                ) from exc

        return newly_applied
