"""Unit tests for FTS5 query parser and sanitizer."""

from edith_brain.services.retrieval.query_parser import sanitize_fts5_query


def test_sanitize_normal_query():
    """Converts normal words to prefix terms."""
    q = "fastapi sqlite wal"
    sanitized = sanitize_fts5_query(q)
    assert sanitized == '"fastapi"* "sqlite"* "wal"*'


def test_sanitize_special_characters_and_colons():
    """Removes colons, asterisks, hyphens, and unbalanced quotes to prevent FTS5 syntax errors."""
    q = 'error: column* "unmatched quote -special (operators)^'
    sanitized = sanitize_fts5_query(q)
    assert ":" not in sanitized
    assert "^" not in sanitized
    assert "(" not in sanitized
    assert ")" not in sanitized
    assert '"error"*' in sanitized
    assert '"column"*' in sanitized
    assert '"quote"*' in sanitized


def test_sanitize_empty_or_punctuation_only():
    """Returns empty quotes for empty or symbol-only inputs."""
    assert sanitize_fts5_query("") == '""'
    assert sanitize_fts5_query("   ") == '""'
    assert sanitize_fts5_query("!@#$%^&*()_+:<>?") == '""'
