"""Unit tests for security utilities: hashing, path sanitization, and file size checks."""

from pathlib import Path
import pytest

from edith_brain.core.security import compute_sha256, validate_safe_path, validate_file_size
from edith_brain.core.exceptions import SecurityError, ValidationError


def test_compute_sha256():
    """Verify standard SHA-256 computation."""
    content = "Hello E.D.I.T.H."
    digest = compute_sha256(content)
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert digest == compute_sha256(content.encode("utf-8"))


def test_validate_safe_path_valid(tmp_path: Path):
    """Safe path resolution within base directory succeeds."""
    base_dir = tmp_path / "storage"
    base_dir.mkdir()
    child_path = Path("documents/file.txt")

    resolved = validate_safe_path(child_path, base_dir)
    assert resolved == (base_dir / "documents" / "file.txt").resolve()


def test_validate_safe_path_traversal_detection(tmp_path: Path):
    """Path traversal attempting to escape base directory raises SecurityError."""
    base_dir = tmp_path / "storage"
    base_dir.mkdir()
    traversal_path = Path("../../windows/system32/calc.exe")

    with pytest.raises(SecurityError) as exc_info:
        validate_safe_path(traversal_path, base_dir)
    assert "Path traversal detected" in str(exc_info.value)


def test_validate_file_size():
    """Size check limits."""
    # Valid
    validate_file_size(size_bytes=500, max_bytes=1000)

    # Empty file
    with pytest.raises(ValidationError) as exc_info:
        validate_file_size(size_bytes=0, max_bytes=1000)
    assert "must not be empty" in str(exc_info.value)

    # Oversized file
    with pytest.raises(ValidationError) as exc_info:
        validate_file_size(size_bytes=1500, max_bytes=1000)
    assert "exceeds configured maximum" in str(exc_info.value)
