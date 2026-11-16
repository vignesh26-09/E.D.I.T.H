"""Controlled text normalization preserving semantic and structural boundaries."""

import re


# Characters to strip: ASCII control chars 0x00-0x08, 0x0B-0x0C, 0x0E-0x1F, and 0x7F (DEL)
# Keep \t (0x09) and \n (0x0A)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTIPLE_BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Perform controlled normalization on extracted document text.

    Guarantees:
    - Consistent UNIX line endings (\n).
    - Non-printable control characters removed.
    - Trailing whitespace removed from individual lines.
    - Excessive blank lines (> 2) collapsed to 2, preserving paragraph breaks.
    - Zero modification of punctuation, casing, or word order.
    """
    if not text:
        return ""

    # 1. Normalize line endings
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Strip disallowed control characters
    normalized = _CONTROL_CHAR_RE.sub("", normalized)

    # 3. Strip trailing whitespace per line
    lines = [line.rstrip() for line in normalized.split("\n")]
    normalized = "\n".join(lines)

    # 4. Collapse excessive consecutive newlines (max 2 consecutive, preserving paragraph separation)
    normalized = _MULTIPLE_BLANK_LINES_RE.sub("\n\n", normalized)

    return normalized.strip()
