"""Typed domain exception hierarchy."""


class BrainCoreException(Exception):
    """Base exception for all Brain Core domain errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(BrainCoreException):
    """Raised when an entity or resource does not exist."""
    pass


class ConflictError(BrainCoreException):
    """Raised when an operation conflicts with existing entity state (e.g. duplicate hash)."""
    pass


class ValidationError(BrainCoreException):
    """Raised when an input or state fails domain business validation."""
    pass


class SecurityError(BrainCoreException):
    """Raised when an access control or safety invariant is violated (e.g. path traversal)."""
    pass


class StorageError(BrainCoreException):
    """Raised when low-level storage or database operations fail."""
    pass


class MigrationError(BrainCoreException):
    """Raised when database schema migrations fail or are corrupted."""
    pass
