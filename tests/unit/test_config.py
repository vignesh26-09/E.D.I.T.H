"""Unit tests for configuration management."""

from pathlib import Path
from edith_brain.core.config import Settings


def test_settings_initialization(tmp_path: Path):
    """Settings initializes properly and creates missing directories."""
    settings = Settings(
        base_dir=tmp_path,
        database_path=tmp_path / "sub" / "db.sqlite",
        storage_raw_dir=tmp_path / "sub" / "raw",
        storage_extracted_dir=tmp_path / "sub" / "extracted",
    )
    assert not settings.database_path.parent.exists()

    settings.ensure_directories()
    assert settings.database_path.parent.exists()
    assert settings.storage_raw_dir.exists()
    assert settings.storage_extracted_dir.exists()
