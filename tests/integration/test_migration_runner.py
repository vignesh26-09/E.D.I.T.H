"""Integration tests for the schema migration runner."""

from pathlib import Path
import pytest

from edith_brain.storage.db import SQLiteEngine
from edith_brain.storage.migrations import MigrationRunner
from edith_brain.core.exceptions import MigrationError


def test_migration_runner_applied_and_idempotent(tmp_path: Path):
    """Running migrations applies them once, and running again is completely idempotent."""
    db_file = tmp_path / "migration_test.db"
    engine = SQLiteEngine(db_path=db_file)
    runner = MigrationRunner(engine=engine)

    # First run: should apply baseline migration 1
    newly_applied = runner.run_migrations()
    assert 1 in newly_applied

    applied = runner.get_applied_migrations()
    assert 1 in applied
    assert applied[1]["name"] == "001_initial_schema.sql"

    # Second run: should apply nothing
    second_run = runner.run_migrations()
    assert len(second_run) == 0


def test_migration_runner_detects_checksum_tampering(tmp_path: Path):
    """Tampering with an applied migration record causes MigrationError on startup."""
    db_file = tmp_path / "tamper_test.db"
    engine = SQLiteEngine(db_path=db_file)
    runner = MigrationRunner(engine=engine)

    # Apply migration
    runner.run_migrations()

    # Tamper with the recorded checksum in SQLite
    with engine.write_transaction() as conn:
        conn.execute(
            "UPDATE schema_migrations SET checksum = 'tampered-invalid-checksum' WHERE version = 1;"
        )

    # Re-running migrations must fail with MigrationError
    with pytest.raises(MigrationError) as exc_info:
        runner.run_migrations()
    assert "Checksum mismatch" in str(exc_info.value)
