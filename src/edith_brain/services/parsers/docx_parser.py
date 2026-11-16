"""DOCX document parser adapter using python-docx."""

import io
from pathlib import Path
import docx

from edith_brain.core.exceptions import ValidationError
from edith_brain.services.parsers.base import BaseDocumentParser, ExtractedElement, ExtractionResult


class DocxParser(BaseDocumentParser):
    """Parses DOCX documents preserving heading styles, paragraphs, and tables."""

    def extract(self, file_path: Path, raw_bytes: bytes, filename: str) -> ExtractionResult:
        if not raw_bytes:
            raise ValidationError(f"File '{filename}' is empty.")

        try:
            doc = docx.Document(io.BytesIO(raw_bytes))
        except Exception as exc:
            raise ValidationError(f"Invalid or corrupted DOCX file '{filename}': {exc}") from exc

        elements: list[ExtractedElement] = []
        full_text_parts: list[str] = []
        current_section = None
        warnings = []

        # 1. Extract paragraphs
        for p_idx, paragraph in enumerate(doc.paragraphs, start=1):
            text = paragraph.text.strip()
            if not text:
                continue

            style_name = paragraph.style.name.lower() if paragraph.style else ""
            is_heading = "heading" in style_name or style_name.startswith("title")

            if is_heading:
                current_section = text
                element_type = "heading"
            else:
                element_type = "paragraph"

            full_text_parts.append(text)
            elements.append(
                ExtractedElement(
                    text=text,
                    page_number=1,  # DOCX does not have fixed layout pages in docx model
                    section=current_section,
                    source_location=f"paragraph {p_idx}",
                    element_type=element_type,
                )
            )

        # 2. Extract tables
        for t_idx, table in enumerate(doc.tables, start=1):
            for r_idx, row in enumerate(table.rows, start=1):
                row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_cells:
                    row_text = " | ".join(row_cells)
                    full_text_parts.append(row_text)
                    elements.append(
                        ExtractedElement(
                            text=row_text,
                            page_number=1,
                            section=current_section,
                            source_location=f"table {t_idx}, row {r_idx}",
                            element_type="table_row",
                        )
                    )

        full_document_text = "\n\n".join(full_text_parts)

        return ExtractionResult(
            text=full_document_text,
            elements=elements,
            extraction_method="docx_python_docx_v1",
            warnings=warnings,
            metadata={
                "paragraph_count": len(doc.paragraphs),
                "table_count": len(doc.tables),
            },
        )
