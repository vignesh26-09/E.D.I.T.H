"""Security utilities: Path sanitization, content hashing, and size validation."""

import hashlib
import hmac
import secrets
from pathlib import Path
from edith_brain.core.exceptions import SecurityError, ValidationError


def compute_sha256(content: bytes | str) -> str:
    """Compute the hexadecimal SHA-256 digest of binary or text content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    hasher = hashlib.sha256()
    hasher.update(content)
    return hasher.hexdigest()


def validate_safe_path(target_path: Path, base_dir: Path) -> Path:
    """Validate that a target path resolves strictly inside the allowed base directory.

    Guards against directory traversal attacks (e.g. `../windows/system32`, symlink escapes).
    """
    resolved_base = base_dir.resolve()
    resolved_target = (resolved_base / target_path).resolve() if not target_path.is_absolute() else target_path.resolve()

    try:
        resolved_target.relative_to(resolved_base)
    except ValueError as exc:
        raise SecurityError(
            f"Path traversal detected: path '{target_path}' escapes base directory '{base_dir}'."
        ) from exc

    return resolved_target


def validate_file_size(size_bytes: int, max_bytes: int) -> None:
    """Validate that an uploaded or processed file does not exceed size limits."""
    if size_bytes <= 0:
        raise ValidationError("File content must not be empty.")
    if size_bytes > max_bytes:
        raise ValidationError(
            f"File size ({size_bytes} bytes) exceeds configured maximum ({max_bytes} bytes)."
        )


def get_or_create_local_token(token_path: Path, configured_secret: str | None = None) -> str:
    """Retrieve or generate local-only authentication bearer token.

    If configured_secret is provided via settings, returns it. Otherwise generates a 32-byte
    cryptographically secure random token and stores it at token_path with restricted permissions.
    """
    if configured_secret and configured_secret.strip():
        return configured_secret.strip()

    if token_path.exists():
        try:
            stored = token_path.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        except Exception:
            pass

    token = secrets.token_hex(32)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token, encoding="utf-8")
    try:
        token_path.chmod(0o600)
    except Exception:
        pass
    return token


def verify_local_token(provided_token: str, expected_token: str) -> bool:
    """Constant-time token verification."""
    if not provided_token or not expected_token:
        return False
    return hmac.compare_digest(provided_token.strip(), expected_token.strip())
