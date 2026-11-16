"""Unit tests for document parser adapters: PlainText, Markdown, PDF, and DOCX."""

import io
from pathlib import Path
import pytest
from pypdf import PdfWriter
import docx

from edith_brain.core.exceptions import ValidationError
from edith_brain.services.parsers.text_parser import PlainTextParser
from edith_brain.services.parsers.markdown_parser import MarkdownParser
from edith_brain.services.parsers.pdf_parser import PDFParser
from edith_brain.services.parsers.docx_parser import DocxParser
from edith_brain.services.parsers.registry import get_parser_for_file


def _create_synthetic_pdf(pages_text: list[str]) -> bytes:
    """Helper to generate in-memory PDF bytes with text."""
    from pypdf import PageObject
    writer = PdfWriter()
    for text in pages_text:
        # Create a blank page and add text
        page = PageObject.create_blank_page(width=612, height=792)
        writer.add_page(page)
    # Write to buffer
    buf = io.BytesIO()
    writer.write(buf)
    # Note: pypdf can inject plain text or we can use PyPDF's annotations/content stream
    return buf.getvalue()


def test_plain_text_parser():
    """PlainTextParser extracts paragraphs and handles utf-8."""
    parser = PlainTextParser()
    content = "Paragraph 1 line 1.\nParagraph 1 line 2.\n\nParagraph 2 line 1."
    res = parser.extract(Path("test.txt"), content.encode("utf-8"), "test.txt")

    assert res.text == content
    assert len(res.elements) == 2
    assert res.elements[0].text == "Paragraph 1 line 1.\nParagraph 1 line 2."
    assert res.elements[1].text == "Paragraph 2 line 1."
    assert "lines 1-2" in res.elements[0].source_location


def test_plain_text_parser_latin1_fallback():
    """PlainTextParser falls back to Latin-1 on non-UTF8 byte sequences."""
    parser = PlainTextParser()
    # 0xE9 is é in Latin-1, invalid standalone in UTF-8
    raw = b"Caf\xe9 de Paris\n\nSecond paragraph."
    res = parser.extract(Path("cafe.txt"), raw, "cafe.txt")
    assert "Café de Paris" in res.text
    assert len(res.warnings) > 0


def test_plain_text_parser_empty_file():
    """Empty plain text file raises ValidationError."""
    parser = PlainTextParser()
    with pytest.raises(ValidationError) as exc:
        parser.extract(Path("empty.txt"), b"", "empty.txt")
    assert "is empty" in str(exc.value)


def test_markdown_parser_headings_and_structure():
    """MarkdownParser captures heading hierarchy and sections."""
    parser = MarkdownParser()
    md_content = """# Architecture Overview

This is the system architecture.

## Storage Layer

The storage layer uses SQLite WAL.

```python
def example():
    return 42
```

### Ingestion Subsystem

Handles document parsing and chunking.
"""
    res = parser.extract(Path("arch.md"), md_content.encode("utf-8"), "arch.md")
    assert len(res.elements) >= 5

    # Check headings and breadcrumbs
    headings = [e for e in res.elements if e.element_type == "heading"]
    assert len(headings) == 3
    assert headings[0].text == "Architecture Overview"
    assert headings[1].text == "Storage Layer"
    assert headings[2].text == "Ingestion Subsystem"
    assert headings[2].section == "Architecture Overview > Storage Layer > Ingestion Subsystem"

    # Check code block
    code_blocks = [e for e in res.elements if e.element_type == "code_block"]
    assert len(code_blocks) == 1
    assert "def example():" in code_blocks[0].text


def test_docx_parser():
    """DocxParser parses paragraphs, headings, and table cells."""
    doc = docx.Document()
    doc.add_heading("Section 1: Introduction", level=1)
    doc.add_paragraph("First paragraph of docx.")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "H1"
    table.cell(0, 1).text = "H2"
    table.cell(1, 0).text = "V1"
    table.cell(1, 1).text = "V2"

    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    parser = DocxParser()
    res = parser.extract(Path("sample.docx"), docx_bytes, "sample.docx")

    assert "Section 1: Introduction" in res.text
    assert "First paragraph of docx." in res.text
    assert len(res.elements) >= 3

    # Heading check
    headings = [e for e in res.elements if e.element_type == "heading"]
    assert len(headings) >= 1
    assert headings[0].text == "Section 1: Introduction"

    # Table row check
    table_elements = [e for e in res.elements if e.element_type == "table_row"]
    assert len(table_elements) == 2


def test_docx_parser_corrupted():
    """Corrupted DOCX raises ValidationError."""
    parser = DocxParser()
    with pytest.raises(ValidationError) as exc:
        parser.extract(Path("corrupt.docx"), b"not a real docx zip archive", "corrupt.docx")
    assert "Invalid or corrupted DOCX" in str(exc.value)


def _get_sample_pdf_bytes() -> bytes:
    """Generate minimal valid PDF bytes containing text."""
    return b"""%PDF-1.4
1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj
2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj
3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>> endobj
4 0 obj <</Length 50>> stream
BT
/F1 12 Tf
72 712 Td
(E.D.I.T.H. Brain Core PDF Spec) Tj
ET
endstream endobj
5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000344 00000 n 
trailer <</Size 6 /Root 1 0 R>>
startxref
423
%%EOF"""


def test_pdf_parser_valid():
    """PDFParser extracts text and reports page provenance."""
    parser = PDFParser()
    pdf_bytes = _get_sample_pdf_bytes()
    res = parser.extract(Path("doc.pdf"), pdf_bytes, "doc.pdf")
    assert "E.D.I.T.H. Brain Core PDF Spec" in res.text
    assert res.metadata["page_count"] == 1
    assert len(res.elements) >= 1
    assert res.elements[0].page_number == 1
    assert "page 1" in res.elements[0].source_location


def test_pdf_parser_corrupted():
    """Corrupted PDF raises ValidationError."""
    parser = PDFParser()
    with pytest.raises(ValidationError) as exc:
        parser.extract(Path("corrupt.pdf"), b"%PDF-1.4 corrupted binary junk", "corrupt.pdf")
    assert "Corrupted or invalid PDF" in str(exc.value)


def test_unsupported_format_raises_validation_error():
    """Unsupported extension raises ValidationError."""
    with pytest.raises(ValidationError) as exc:
        get_parser_for_file("data.xyz")
    assert "Unsupported document format" in str(exc.value)
