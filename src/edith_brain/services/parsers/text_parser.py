"""Plain text document parser adapter."""

from pathlib import Path
from edith_brain.core.exceptions import ValidationError
from edith_brain.services.parsers.base import BaseDocumentParser, ExtractedElement, ExtractionResult


class PlainTextParser(BaseDocumentParser):
    """Parses plain text (.txt) files with encoding fallback and paragraph tracking."""

    SUPPORTED_ENCODINGS = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

    def extract(self, file_path: Path, raw_bytes: bytes, filename: str) -> ExtractionResult:
        if not raw_bytes:
            raise ValidationError(f"File '{filename}' is empty.")

        decoded_text = None
        used_encoding = None
        warnings = []

        for encoding in self.SUPPORTED_ENCODINGS:
            try:
                decoded_text = raw_bytes.decode(encoding)
                used_encoding = encoding
                break
            except UnicodeDecodeError:
                continue

        if decoded_text is None:
            raise ValidationError(
                f"Failed to decode plain text file '{filename}' with supported encodings."
            )

        if used_encoding != "utf-8":
            warnings.append(f"Decoded file using fallback encoding '{used_encoding}'.")

        # Split into paragraphs and structural elements
        elements: list[ExtractedElement] = []
        raw_paragraphs = decoded_text.split("\n\n")
        current_line = 1

        for p_idx, p_text in enumerate(raw_paragraphs):
            cleaned = p_text.strip()
            num_lines = p_text.count("\n") + 1
            if cleaned:
                elements.append(
                    ExtractedElement(
                        text=cleaned,
                        page_number=1,
                        section=None,
                        source_location=f"lines {current_line}-{current_line + num_lines - 1}",
                        element_type="paragraph",
                    )
                )
            current_line += num_lines + 1

        return ExtractionResult(
            text=decoded_text,
            elements=elements,
            extraction_method="plaintext_parser_v1",
            warnings=warnings,
            metadata={"encoding": used_encoding, "paragraph_count": len(elements)},
        )
