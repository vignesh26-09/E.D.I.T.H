"""Unit tests for text normalization."""

from edith_brain.services.normalizer import normalize_text


def test_normalize_line_endings():
    """Converts CRLF and CR to clean standard UNIX LF."""
    raw = "Line 1\r\nLine 2\rLine 3\nLine 4"
    normalized = normalize_text(raw)
    assert "\r" not in normalized
    assert normalized == "Line 1\nLine 2\nLine 3\nLine 4"


def test_normalize_control_characters():
    """Strips non-printable control characters while preserving tabs and newlines."""
    # 0x00 (NUL), 0x07 (BEL), 0x09 (TAB), 0x0A (LF), 0x1B (ESC)
    raw = "Valid Text\x00 with\x07 control\x1b chars.\tTab preserved.\nNewline preserved."
    normalized = normalize_text(raw)
    assert "\x00" not in normalized
    assert "\x07" not in normalized
    assert "\x1b" not in normalized
    assert "\t" in normalized
    assert "\n" in normalized
    assert "Valid Text with control chars.\tTab preserved.\nNewline preserved." == normalized


def test_normalize_trailing_whitespace_and_empty_lines():
    """Strips trailing whitespace and collapses > 2 empty lines to 2."""
    raw = "Line 1   \n\n\n\n\nLine 2  \t  \n\n\nLine 3"
    normalized = normalize_text(raw)
    assert "\n\n\n" not in normalized
    assert normalized == "Line 1\n\nLine 2\n\nLine 3"


def test_normalize_preserves_content_integrity():
    """Does not alter casing, punctuation, symbols, or word meaning."""
    text = "“Hello, World!” — 100% verified: [code] != {null} & *bold*."
    assert normalize_text(text) == text
