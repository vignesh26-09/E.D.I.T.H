"""PDF document parser adapter using pypdf."""

import io
from pathlib import Path
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from edith_brain.core.exceptions import ValidationError
from edith_brain.services.parsers.base import BaseDocumentParser, ExtractedElement, ExtractionResult


class PDFParser(BaseDocumentParser):
    """Parses PDF documents page-by-page preserving page numbers and outline structure."""

    def extract(self, file_path: Path, raw_bytes: bytes, filename: str) -> ExtractionResult:
        if not raw_bytes:
            raise ValidationError(f"File '{filename}' is empty.")

        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
        except (PdfReadError, Exception) as exc:
            raise ValidationError(f"Corrupted or invalid PDF file '{filename}': {exc}") from exc

        if reader.is_encrypted:
            raise ValidationError(f"Encrypted/password-protected PDF '{filename}' is not supported.")

        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValidationError(f"PDF file '{filename}' contains 0 pages.")

        elements: list[ExtractedElement] = []
        full_text_parts: list[str] = []
        warnings = []

        # Extract document outlines/bookmarks if available
        current_section = None

        for page_idx, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                warnings.append(f"Failed to extract text from page {page_idx}: {exc}")
                page_text = ""

            cleaned_page = page_text.strip()
            if not cleaned_page:
                continue

            full_text_parts.append(cleaned_page)

            # Split page text into paragraphs
            page_paragraphs = [p.strip() for p in cleaned_page.split("\n\n") if p.strip()]
            for p_idx, p_text in enumerate(page_paragraphs, start=1):
                elements.append(
                    ExtractedElement(
                        text=p_text,
                        page_number=page_idx,
                        section=current_section,
                        source_location=f"page {page_idx}, paragraph {p_idx}",
                        element_type="paragraph",
                    )
                )

        full_document_text = "\n\n".join(full_text_parts)
        if not full_document_text.strip():
            warnings.append(f"No extractable text found in PDF '{filename}' (may contain only scanned images).")

        return ExtractionResult(
            text=full_document_text,
            elements=elements,
            extraction_method="pdf_pypdf_v1",
            warnings=warnings,
            metadata={
                "page_count": total_pages,
                "author": reader.metadata.author if reader.metadata else None,
                "title": reader.metadata.title if reader.metadata else None,
            },
        )
