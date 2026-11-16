"""Query sanitization and parsing utilities for SQLite FTS5."""

import re


_PUNCTUATION_RE = re.compile(r"[^\w\s]")


def sanitize_fts5_query(raw_query: str, match_mode: str = "AND") -> str:
    """Sanitize user query into a safe SQLite FTS5 MATCH expression.

    Guards against syntax errors caused by special FTS5 operators (: * ^ NEAR NOT OR AND)
    or unclosed quotation marks. Formats tokens into prefix-match terms.
    """
    if not raw_query or not raw_query.strip():
        return '""'

    # Extract clean alphanumeric tokens (letters and digits only, excluding underscores and symbols)
    tokens = re.findall(r"[a-zA-Z0-9]+", raw_query)
    if not tokens:
        return '""'

    # Filter out empty tokens
    clean_tokens = [t.strip() for t in tokens if len(t.strip()) > 0]
    if not clean_tokens:
        return '""'

    # Wrap each token in double quotes with prefix wildcards
    sep = " OR " if match_mode.upper() == "OR" else " "
    return sep.join(f'"{t}"*' for t in clean_tokens)
